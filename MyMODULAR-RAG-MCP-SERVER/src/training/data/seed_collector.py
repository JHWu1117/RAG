"""Collect canonical, privacy-screened seeds from approved read-only inputs."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from src.core.types import Document
from src.training.data.privacy_filter import PrivacyFilter, PrivacyFinding
from src.training.data.schemas import SchemaValidationError, TaskType


class SeedSource(str, Enum):
    DOCUMENT = "document"
    GOLDEN_QA = "golden_qa"
    TRACE = "trace"


def _required_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SchemaValidationError(f"{name} must be a non-empty string")
    return value


def _hash_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_payload(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return _hash_text(encoded)


@dataclass
class SeedProvenance:
    """Auditable origin and authorization attached to every accepted seed."""

    source_uri: str
    content_sha256: str
    license_name: str
    authorization_basis: str
    trace_opt_in: bool | None = None

    def __post_init__(self) -> None:
        self.source_uri = _required_text(self.source_uri, "source_uri")
        self.content_sha256 = _required_text(
            self.content_sha256, "content_sha256"
        )
        if not self.content_sha256.startswith("sha256:"):
            raise SchemaValidationError("content_sha256 must start with 'sha256:'")
        self.license_name = _required_text(self.license_name, "license_name")
        self.authorization_basis = _required_text(
            self.authorization_basis, "authorization_basis"
        )
        if self.trace_opt_in is not None and not isinstance(self.trace_opt_in, bool):
            raise SchemaValidationError("trace_opt_in must be a boolean or null")

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_uri": self.source_uri,
            "content_sha256": self.content_sha256,
            "license_name": self.license_name,
            "authorization_basis": self.authorization_basis,
            "trace_opt_in": self.trace_opt_in,
        }


@dataclass
class CanonicalSeed:
    """A normalized pre-labeling input consumed by K3 and K4."""

    source: SeedSource
    source_group_id: str
    content: str
    provenance: SeedProvenance
    instruction: str | None = None
    reference_answer: str | None = None
    task_type: TaskType | None = None
    history: list[dict[str, str]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    seed_id: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.source, SeedSource):
            try:
                self.source = SeedSource(self.source)
            except (TypeError, ValueError) as exc:
                raise SchemaValidationError(f"unknown seed source: {self.source!r}") from exc
        self.source_group_id = _required_text(
            self.source_group_id, "source_group_id"
        )
        self.content = _required_text(self.content, "content")
        if not isinstance(self.provenance, SeedProvenance):
            self.provenance = SeedProvenance(**dict(self.provenance))
        if self.instruction is not None:
            self.instruction = _required_text(self.instruction, "instruction")
        if self.reference_answer is not None and not isinstance(
            self.reference_answer, str
        ):
            raise SchemaValidationError("reference_answer must be a string or null")
        if self.task_type is not None and not isinstance(self.task_type, TaskType):
            try:
                self.task_type = TaskType(self.task_type)
            except (TypeError, ValueError) as exc:
                raise SchemaValidationError(
                    f"unknown seed task_type: {self.task_type!r}"
                ) from exc
        self.history = copy.deepcopy(self.history)
        self.metadata = copy.deepcopy(self.metadata)
        computed = _hash_payload(self._identity_payload())
        if self.seed_id and self.seed_id != computed:
            raise SchemaValidationError("seed_id does not match canonical content")
        self.seed_id = computed

    def _identity_payload(self) -> dict[str, Any]:
        return {
            "source": self.source.value,
            "source_group_id": self.source_group_id,
            "content": self.content,
            "instruction": self.instruction,
            "reference_answer": self.reference_answer,
            "task_type": self.task_type.value if self.task_type else None,
            "history": self.history,
            "metadata": self.metadata,
            "provenance": self.provenance.to_dict(),
        }

    def to_dict(self) -> dict[str, Any]:
        return {"seed_id": self.seed_id, **self._identity_payload()}


@dataclass(frozen=True)
class QuarantinedSeed:
    """A safe audit record for an input excluded from canonical seeds."""

    source: SeedSource
    reason_codes: tuple[str, ...]
    sanitized_record: Any
    findings: tuple[PrivacyFinding, ...] = ()


@dataclass
class SeedCollection:
    accepted: list[CanonicalSeed] = field(default_factory=list)
    quarantined: list[QuarantinedSeed] = field(default_factory=list)

    def extend(self, other: SeedCollection) -> None:
        self.accepted.extend(other.accepted)
        self.quarantined.extend(other.quarantined)


class SeedCollector:
    """Read sources without modifying them and emit accepted/quarantined seeds."""

    def __init__(self, privacy_filter: PrivacyFilter | None = None) -> None:
        self._privacy = privacy_filter or PrivacyFilter()

    def collect_documents(
        self,
        documents: Iterable[Document | Mapping[str, Any]],
        *,
        license_name: str,
        authorization_basis: str,
    ) -> SeedCollection:
        result = SeedCollection()
        for document in documents:
            raw = (
                document.to_dict()
                if isinstance(document, Document)
                else copy.deepcopy(dict(document))
            )
            screened = self._privacy.screen(raw)
            if screened.findings:
                result.quarantined.append(
                    self._quarantine(SeedSource.DOCUMENT, screened.value, screened.findings)
                )
                continue
            try:
                text = _required_text(screened.value.get("text"), "document.text")
                metadata = copy.deepcopy(screened.value.get("metadata") or {})
                source_uri = str(
                    metadata.get("source_path") or screened.value.get("id") or "document"
                )
                content_hash = _hash_text(text)
                result.accepted.append(
                    CanonicalSeed(
                        source=SeedSource.DOCUMENT,
                        source_group_id=f"doc_{content_hash}",
                        content=text,
                        provenance=SeedProvenance(
                            source_uri=source_uri,
                            content_sha256=content_hash,
                            license_name=license_name,
                            authorization_basis=authorization_basis,
                        ),
                        metadata=metadata,
                    )
                )
            except (SchemaValidationError, TypeError, ValueError) as exc:
                result.quarantined.append(
                    QuarantinedSeed(
                        SeedSource.DOCUMENT,
                        (f"invalid_document:{type(exc).__name__}",),
                        screened.value,
                    )
                )
        return result

    def collect_golden_qa(
        self,
        source: str | Path | Mapping[str, Any],
        *,
        license_name: str = "project_fixture",
        authorization_basis: str = "project_owned",
    ) -> SeedCollection:
        payload, source_uri = self._load_json_object(source)
        cases = payload.get("test_cases")
        if not isinstance(cases, list):
            raise SchemaValidationError("golden QA must contain a test_cases list")
        result = SeedCollection()
        source_hash = _hash_payload(payload)
        for case in cases:
            raw = copy.deepcopy(case)
            screened = self._privacy.screen(raw)
            if screened.findings:
                result.quarantined.append(
                    self._quarantine(SeedSource.GOLDEN_QA, screened.value, screened.findings)
                )
                continue
            try:
                item = screened.value
                query = _required_text(item.get("query"), "golden query")
                answer = item.get("reference_answer")
                expected_sources = list(item.get("expected_sources") or [])
                group_basis = expected_sources or [source_hash]
                result.accepted.append(
                    CanonicalSeed(
                        source=SeedSource.GOLDEN_QA,
                        source_group_id=f"golden_{_hash_payload(group_basis)}",
                        content=answer or query,
                        instruction=query,
                        reference_answer=answer,
                        task_type=TaskType.GROUNDED_GENERATION,
                        provenance=SeedProvenance(
                            source_uri=source_uri,
                            content_sha256=_hash_payload(item),
                            license_name=license_name,
                            authorization_basis=authorization_basis,
                        ),
                        metadata={
                            "expected_chunk_ids": list(item.get("expected_chunk_ids") or []),
                            "expected_sources": expected_sources,
                            "expected_pages": list(item.get("expected_pages") or []),
                        },
                    )
                )
            except (SchemaValidationError, TypeError, ValueError) as exc:
                result.quarantined.append(
                    QuarantinedSeed(
                        SeedSource.GOLDEN_QA,
                        (f"invalid_golden_qa:{type(exc).__name__}",),
                        screened.value,
                    )
                )
        return result

    def collect_traces(
        self,
        source: str | Path | Sequence[Mapping[str, Any]],
        *,
        opt_in: bool = False,
        license_name: str = "authorized_trace",
        authorization_basis: str = "explicit_training_opt_in",
    ) -> SeedCollection:
        records, source_uri = self._load_jsonl_or_records(source)
        result = SeedCollection()
        for trace in records:
            raw = copy.deepcopy(dict(trace))
            screened = self._privacy.screen(raw)
            metadata = raw.get("metadata")
            metadata = metadata if isinstance(metadata, Mapping) else {}
            per_trace_opt_in = (
                raw.get("training_opt_in") is True
                or metadata.get("training_opt_in") is True
            )
            if not (opt_in and per_trace_opt_in):
                result.quarantined.append(
                    QuarantinedSeed(
                        SeedSource.TRACE,
                        ("trace_not_authorized",),
                        screened.value,
                        screened.findings,
                    )
                )
                continue
            if screened.findings:
                result.quarantined.append(
                    self._quarantine(SeedSource.TRACE, screened.value, screened.findings)
                )
                continue
            try:
                query = self._trace_query(screened.value)
                metadata = copy.deepcopy(screened.value.get("metadata") or {})
                answer = metadata.get("answer") or metadata.get("response")
                trace_id = str(screened.value.get("trace_id") or _hash_payload(screened.value))
                content_hash = _hash_payload(screened.value)
                result.accepted.append(
                    CanonicalSeed(
                        source=SeedSource.TRACE,
                        source_group_id=str(
                            metadata.get("source_group_id")
                            or f"trace_{_hash_text(trace_id)}"
                        ),
                        content=answer or query,
                        instruction=query,
                        reference_answer=answer,
                        task_type=TaskType.GROUNDED_GENERATION,
                        provenance=SeedProvenance(
                            source_uri=source_uri,
                            content_sha256=content_hash,
                            license_name=license_name,
                            authorization_basis=authorization_basis,
                            trace_opt_in=True,
                        ),
                        metadata={
                            "trace_id": trace_id,
                            "started_at": screened.value.get("started_at"),
                        },
                    )
                )
            except (SchemaValidationError, TypeError, ValueError) as exc:
                result.quarantined.append(
                    QuarantinedSeed(
                        SeedSource.TRACE,
                        (f"invalid_trace:{type(exc).__name__}",),
                        screened.value,
                    )
                )
        return result

    @staticmethod
    def _quarantine(
        source: SeedSource,
        sanitized: Any,
        findings: tuple[PrivacyFinding, ...],
    ) -> QuarantinedSeed:
        reasons = tuple(sorted({f"privacy:{item.kind.value}" for item in findings}))
        return QuarantinedSeed(source, reasons, sanitized, findings)

    @staticmethod
    def _trace_query(trace: Mapping[str, Any]) -> str:
        metadata = trace.get("metadata") or {}
        for name in ("query", "user_query", "instruction"):
            value = metadata.get(name)
            if isinstance(value, str) and value.strip():
                return value
        for stage in trace.get("stages") or []:
            data = stage.get("data") or {}
            for name in ("query", "original_query"):
                value = data.get(name)
                if isinstance(value, str) and value.strip():
                    return value
        raise SchemaValidationError("authorized query trace has no query")

    @staticmethod
    def _load_json_object(
        source: str | Path | Mapping[str, Any],
    ) -> tuple[dict[str, Any], str]:
        if isinstance(source, Mapping):
            return copy.deepcopy(dict(source)), "memory://golden-qa"
        path = Path(source)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise SchemaValidationError("JSON source must contain an object")
        return payload, str(path)

    @staticmethod
    def _load_jsonl_or_records(
        source: str | Path | Sequence[Mapping[str, Any]],
    ) -> tuple[list[dict[str, Any]], str]:
        if isinstance(source, (str, Path)):
            path = Path(source)
            records: list[dict[str, Any]] = []
            for line_number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), 1
            ):
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise SchemaValidationError(
                        f"trace JSONL line {line_number} must be an object"
                    )
                records.append(value)
            return records, str(path)
        return [copy.deepcopy(dict(item)) for item in source], "memory://traces"


__all__ = [
    "CanonicalSeed",
    "QuarantinedSeed",
    "SeedCollection",
    "SeedCollector",
    "SeedProvenance",
    "SeedSource",
]
