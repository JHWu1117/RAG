"""K1 training-sample data contracts for Critic, Generator, and Preference sets.

One unified record type (:class:`TrainingSample`) is stored as JSONL and
projected into task-specific views at training time. Label enums are imported
from ``src.core.self_rag_types`` so the offline data plane and the online
inference plane can never drift apart.

Three invariants are enforced here rather than downstream, because a violation
means the record must not reach an accepted dataset at all:

1. every ``evidence_ids`` entry must exist in this sample's retrieval snapshot;
2. labels must be known enum members (no free-form strings);
3. teacher provenance must be complete, so any label can be traced back to the
   model, prompt version, and raw response that produced it.

Retry and abstention are ``SelfRAGPolicy`` decisions, not labels, so no sample
carries an abstain flag. "The evidence does not support an answer" is expressed
as ``NOT_SUPPORTED`` plus low utility.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from src.core.self_rag_types import (
    RelevanceLabel,
    RetrieveDecision,
    SupportLabel,
    UtilityLabel,
)

SCHEMA_VERSION = 1
SAMPLE_ID_PREFIX = "sha256:"
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class TaskType(str, Enum):
    """Training tasks that the Critic and Generator must cover."""

    RETRIEVAL_DECISION = "retrieval_decision"
    EVIDENCE_RELEVANCE = "evidence_relevance"
    SUPPORT_JUDGMENT = "support_judgment"
    UTILITY_JUDGMENT = "utility_judgment"
    QUERY_REWRITE = "query_rewrite"
    GROUNDED_GENERATION = "grounded_generation"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class ReviewStatus(str, Enum):
    """Where a sample may go once quality gates have run."""

    ACCEPTED = "accepted"
    QUARANTINED = "quarantined"
    REJECTED = "rejected"


class Split(str, Enum):
    TRAIN = "train"
    DEV = "dev"
    TEST = "test"


class CandidateRole(str, Enum):
    """How a retrieved chunk is used before Teacher adjudication."""

    RETRIEVED = "retrieved"
    POSITIVE = "positive"
    HARD_NEGATIVE = "hard_negative"
    CONFLICTING = "conflicting"


class SchemaValidationError(ValueError):
    """Raised when a record violates the training-sample contract."""


# --- small validators ---------------------------------------------------


def _non_empty_str(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SchemaValidationError(f"{field_name} must be a non-empty string")
    return value


def _optional_str(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SchemaValidationError(f"{field_name} must be a string or null")
    return value


def _score(value: Any, field_name: str) -> float | None:
    """Retrieval scores are unbounded but must be finite and real."""

    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SchemaValidationError(f"{field_name} must be a finite number or null")
    number = float(value)
    if not math.isfinite(number):
        raise SchemaValidationError(f"{field_name} must be a finite number or null")
    return number


def _probability(value: Any, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SchemaValidationError(f"{field_name} must be a number in [0, 1] or null")
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise SchemaValidationError(f"{field_name} must be a number in [0, 1] or null")
    return number


def _enum(value: Any, enum_type: type[Enum], field_name: str) -> Any:
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        allowed = [member.value for member in enum_type]
        raise SchemaValidationError(
            f"Unknown {field_name}: {value!r}; allowed={allowed}"
        ) from exc


def _construct(cls: type, data: Mapping[str, Any], what: str) -> Any:
    """Build a dataclass from a mapping, reporting missing fields as schema errors."""

    if not isinstance(data, Mapping):
        raise SchemaValidationError(f"{what} must be an object")
    try:
        return cls(**dict(data))
    except TypeError as exc:
        raise SchemaValidationError(f"{what} has missing or unexpected fields: {exc}") from exc


def _content_hash(payload: Any) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return SAMPLE_ID_PREFIX + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --- retrieval snapshot -------------------------------------------------


@dataclass
class RetrievalCandidate:
    """One retrieved chunk with the scores that produced its ranking."""

    chunk_id: str
    text: str
    source: str
    dense_score: float | None = None
    sparse_score: float | None = None
    fusion_score: float | None = None
    rerank_score: float | None = None
    source_group_id: str | None = None
    collection: str | None = None
    role: CandidateRole = CandidateRole.RETRIEVED

    def __post_init__(self) -> None:
        self.chunk_id = _non_empty_str(self.chunk_id, "chunk_id")
        self.text = _non_empty_str(self.text, "text")
        self.source = _non_empty_str(self.source, "source")
        self.dense_score = _score(self.dense_score, "dense_score")
        self.sparse_score = _score(self.sparse_score, "sparse_score")
        self.fusion_score = _score(self.fusion_score, "fusion_score")
        self.rerank_score = _score(self.rerank_score, "rerank_score")
        self.source_group_id = _optional_str(self.source_group_id, "source_group_id")
        self.collection = _optional_str(self.collection, "collection")
        self.role = _enum(self.role, CandidateRole, "candidate role")

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "text": self.text,
            "source": self.source,
            "dense_score": self.dense_score,
            "sparse_score": self.sparse_score,
            "fusion_score": self.fusion_score,
            "rerank_score": self.rerank_score,
            "source_group_id": self.source_group_id,
            "collection": self.collection,
            "role": self.role.value,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RetrievalCandidate:
        return _construct(cls, data, "candidate")


@dataclass
class RetrievalSnapshot:
    """The exact candidate set a label was produced against."""

    index_version: str
    query: str
    candidates: list[RetrievalCandidate] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.index_version = _non_empty_str(self.index_version, "index_version")
        self.query = _non_empty_str(self.query, "query")
        if not isinstance(self.candidates, list):
            raise SchemaValidationError("candidates must be a list")
        self.candidates = [
            item if isinstance(item, RetrievalCandidate) else RetrievalCandidate.from_dict(item)
            for item in self.candidates
        ]
        ids = [candidate.chunk_id for candidate in self.candidates]
        if len(set(ids)) != len(ids):
            raise SchemaValidationError("retrieval snapshot has duplicate chunk_id values")

    @property
    def chunk_ids(self) -> set[str]:
        return {candidate.chunk_id for candidate in self.candidates}

    def to_dict(self) -> dict[str, Any]:
        return {
            "index_version": self.index_version,
            "query": self.query,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RetrievalSnapshot:
        return _construct(cls, data, "retrieval_snapshot")


# --- labels -------------------------------------------------------------


@dataclass
class EvidenceLabel:
    """Per-chunk relevance judgement."""

    chunk_id: str
    relevance: RelevanceLabel
    concise_reason: str | None = None

    def __post_init__(self) -> None:
        self.chunk_id = _non_empty_str(self.chunk_id, "chunk_id")
        self.relevance = _enum(self.relevance, RelevanceLabel, "relevance")
        self.concise_reason = _optional_str(self.concise_reason, "concise_reason")

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "relevance": self.relevance.value,
            "concise_reason": self.concise_reason,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> EvidenceLabel:
        return _construct(cls, data, "evidence entry")


@dataclass
class SegmentLabel:
    """One answer segment bound to the evidence that supports it."""

    text: str
    evidence_ids: list[str]
    support: SupportLabel
    utility: int
    support_reason: str | None = None
    utility_reason: str | None = None

    def __post_init__(self) -> None:
        self.text = _non_empty_str(self.text, "segment text")
        if not isinstance(self.evidence_ids, list):
            raise SchemaValidationError("evidence_ids must be a list")
        for item in self.evidence_ids:
            _non_empty_str(item, "evidence_ids entry")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise SchemaValidationError("evidence_ids must not contain duplicates")
        self.support = _enum(self.support, SupportLabel, "support")
        if isinstance(self.utility, bool) or not isinstance(self.utility, int):
            raise SchemaValidationError("utility must be an integer from 1 to 5")
        self.utility = int(_enum(self.utility, UtilityLabel, "utility"))
        self.support_reason = _optional_str(self.support_reason, "support_reason")
        self.utility_reason = _optional_str(self.utility_reason, "utility_reason")
        if self.support is not SupportLabel.NOT_SUPPORTED and not self.evidence_ids:
            raise SchemaValidationError(
                "a supported segment must cite at least one evidence id"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "evidence_ids": list(self.evidence_ids),
            "support": self.support.value,
            "utility": self.utility,
            "support_reason": self.support_reason,
            "utility_reason": self.utility_reason,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SegmentLabel:
        return _construct(cls, data, "segment")


@dataclass
class SampleLabels:
    """Teacher judgements for one sample. No abstain flag: that is policy."""

    retrieve: RetrieveDecision
    evidence: list[EvidenceLabel] = field(default_factory=list)
    segments: list[SegmentLabel] = field(default_factory=list)
    final_answer: str = ""
    rewritten_query: str | None = None

    def __post_init__(self) -> None:
        self.retrieve = _enum(self.retrieve, RetrieveDecision, "retrieve")
        if not isinstance(self.evidence, list):
            raise SchemaValidationError("evidence must be a list")
        self.evidence = [
            item if isinstance(item, EvidenceLabel) else EvidenceLabel.from_dict(item)
            for item in self.evidence
        ]
        labelled = [item.chunk_id for item in self.evidence]
        if len(set(labelled)) != len(labelled):
            raise SchemaValidationError("evidence must not label the same chunk twice")
        if not isinstance(self.segments, list):
            raise SchemaValidationError("segments must be a list")
        self.segments = [
            item if isinstance(item, SegmentLabel) else SegmentLabel.from_dict(item)
            for item in self.segments
        ]
        if not isinstance(self.final_answer, str):
            raise SchemaValidationError("final_answer must be a string")
        self.rewritten_query = _optional_str(self.rewritten_query, "rewritten_query")

    def to_dict(self) -> dict[str, Any]:
        return {
            "retrieve": self.retrieve.value,
            "evidence": [item.to_dict() for item in self.evidence],
            "segments": [item.to_dict() for item in self.segments],
            "final_answer": self.final_answer,
            "rewritten_query": self.rewritten_query,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SampleLabels:
        return _construct(cls, data, "labels")


# --- provenance and quality --------------------------------------------


@dataclass
class TeacherProvenance:
    """Which model, prompt, and response produced these labels.

    Every field except ``label_confidence`` is mandatory: a sample whose origin
    cannot be reconstructed must never be trained on.
    """

    provider: str
    model: str
    prompt_version: str
    request_id: str
    temperature: float
    raw_response_hash: str
    label_confidence: float | None = None
    prompt_hash: str | None = None

    def __post_init__(self) -> None:
        self.provider = _non_empty_str(self.provider, "teacher.provider")
        self.model = _non_empty_str(self.model, "teacher.model")
        self.prompt_version = _non_empty_str(self.prompt_version, "teacher.prompt_version")
        self.request_id = _non_empty_str(self.request_id, "teacher.request_id")
        temperature = _score(self.temperature, "teacher.temperature")
        if temperature is None or temperature < 0:
            raise SchemaValidationError("teacher.temperature must be a non-negative number")
        self.temperature = temperature
        self.raw_response_hash = _non_empty_str(
            self.raw_response_hash, "teacher.raw_response_hash"
        )
        if not _HASH_RE.match(self.raw_response_hash):
            raise SchemaValidationError(
                "teacher.raw_response_hash must look like 'sha256:<64 hex chars>'"
            )
        self.label_confidence = _probability(
            self.label_confidence, "teacher.label_confidence"
        )
        self.prompt_hash = _optional_str(self.prompt_hash, "teacher.prompt_hash")
        if self.prompt_hash is not None and not _HASH_RE.match(self.prompt_hash):
            raise SchemaValidationError(
                "teacher.prompt_hash must look like 'sha256:<64 hex chars>'"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "request_id": self.request_id,
            "temperature": self.temperature,
            "label_confidence": self.label_confidence,
            "raw_response_hash": self.raw_response_hash,
            "prompt_hash": self.prompt_hash,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TeacherProvenance:
        return _construct(cls, data, "teacher provenance")


@dataclass
class QualityReport:
    """Outcome of the quality gates for one sample."""

    schema_valid: bool = True
    rule_checks: list[str] = field(default_factory=list)
    agreement: str | None = None
    review_status: ReviewStatus = ReviewStatus.ACCEPTED
    quarantine_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.schema_valid, bool):
            raise SchemaValidationError("quality.schema_valid must be a boolean")
        if not isinstance(self.rule_checks, list) or any(
            not isinstance(item, str) for item in self.rule_checks
        ):
            raise SchemaValidationError("quality.rule_checks must be a list of strings")
        self.agreement = _optional_str(self.agreement, "quality.agreement")
        self.review_status = _enum(self.review_status, ReviewStatus, "quality.review_status")
        self.quarantine_reason = _optional_str(
            self.quarantine_reason, "quality.quarantine_reason"
        )
        if self.review_status is not ReviewStatus.ACCEPTED and not self.quarantine_reason:
            raise SchemaValidationError(
                "a non-accepted sample must record a quarantine_reason"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_valid": self.schema_valid,
            "rule_checks": list(self.rule_checks),
            "agreement": self.agreement,
            "review_status": self.review_status.value,
            "quarantine_reason": self.quarantine_reason,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> QualityReport:
        return _construct(cls, data, "quality")


# --- the unified sample -------------------------------------------------


@dataclass
class TrainingSample:
    """One content-addressed training record."""

    dataset_version: str
    task_type: TaskType
    instruction: str
    source_group_id: str
    retrieval_snapshot: RetrievalSnapshot
    labels: SampleLabels
    teacher: TeacherProvenance
    quality: QualityReport = field(default_factory=QualityReport)
    split: Split = Split.TRAIN
    history: list[dict[str, str]] = field(default_factory=list)
    created_at: str = ""
    sample_id: str = ""
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.dataset_version = _non_empty_str(self.dataset_version, "dataset_version")
        self.task_type = _enum(self.task_type, TaskType, "task_type")
        self.instruction = _non_empty_str(self.instruction, "instruction")
        self.source_group_id = _non_empty_str(self.source_group_id, "source_group_id")

        if not isinstance(self.retrieval_snapshot, RetrievalSnapshot):
            self.retrieval_snapshot = RetrievalSnapshot.from_dict(self.retrieval_snapshot)
        if not isinstance(self.labels, SampleLabels):
            self.labels = SampleLabels.from_dict(self.labels)
        if not isinstance(self.teacher, TeacherProvenance):
            self.teacher = TeacherProvenance.from_dict(self.teacher)
        if not isinstance(self.quality, QualityReport):
            self.quality = QualityReport.from_dict(self.quality)
        self.split = _enum(self.split, Split, "split")

        if not isinstance(self.history, list) or any(
            not isinstance(turn, Mapping) for turn in self.history
        ):
            raise SchemaValidationError("history must be a list of objects")
        self.history = [dict(turn) for turn in self.history]

        if not isinstance(self.schema_version, int) or isinstance(self.schema_version, bool):
            raise SchemaValidationError("schema_version must be an integer")

        self._validate_evidence_ids()
        self._validate_task_consistency()

        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        computed = self.compute_sample_id()
        if self.sample_id and self.sample_id != computed:
            raise SchemaValidationError(
                "sample_id does not match its content; refusing a mislabelled record"
            )
        self.sample_id = computed

    def _validate_evidence_ids(self) -> None:
        """Every cited chunk must exist in this sample's own snapshot."""

        known = self.retrieval_snapshot.chunk_ids
        for label in self.labels.evidence:
            if label.chunk_id not in known:
                raise SchemaValidationError(
                    f"evidence chunk_id {label.chunk_id!r} is not in the retrieval snapshot"
                )
        for index, segment in enumerate(self.labels.segments):
            for chunk_id in segment.evidence_ids:
                if chunk_id not in known:
                    raise SchemaValidationError(
                        f"segments[{index}] cites unknown chunk_id {chunk_id!r}"
                    )

    def _validate_task_consistency(self) -> None:
        """Rules that make a label set meaningful for its declared task."""

        if self.labels.retrieve is RetrieveDecision.NO_RETRIEVE:
            if any(
                segment.evidence_ids for segment in self.labels.segments
            ):
                raise SchemaValidationError(
                    "a no_retrieve sample must not depend on retrieved evidence"
                )
        if self.task_type is TaskType.QUERY_REWRITE and not self.labels.rewritten_query:
            raise SchemaValidationError(
                "query_rewrite samples must provide labels.rewritten_query"
            )
        if self.task_type is TaskType.INSUFFICIENT_EVIDENCE:
            if any(
                segment.support is SupportLabel.FULLY_SUPPORTED
                for segment in self.labels.segments
            ):
                raise SchemaValidationError(
                    "insufficient_evidence samples cannot contain fully supported segments"
                )

    def compute_sample_id(self) -> str:
        """Content address: identical content always yields the same id."""

        return _content_hash(
            {
                "schema_version": self.schema_version,
                "task_type": self.task_type.value,
                "instruction": self.instruction,
                "history": self.history,
                "source_group_id": self.source_group_id,
                "query": self.retrieval_snapshot.query,
                "candidates": sorted(self.retrieval_snapshot.chunk_ids),
                "labels": self.labels.to_dict(),
            }
        )

    @property
    def is_accepted(self) -> bool:
        return self.quality.review_status is ReviewStatus.ACCEPTED

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "schema_version": self.schema_version,
            "dataset_version": self.dataset_version,
            "task_type": self.task_type.value,
            "instruction": self.instruction,
            "history": list(self.history),
            "source_group_id": self.source_group_id,
            "retrieval_snapshot": self.retrieval_snapshot.to_dict(),
            "labels": self.labels.to_dict(),
            "teacher": self.teacher.to_dict(),
            "quality": self.quality.to_dict(),
            "split": self.split.value,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TrainingSample:
        if not isinstance(data, Mapping):
            raise SchemaValidationError("sample must be an object")
        known = {
            "sample_id", "schema_version", "dataset_version", "task_type", "instruction",
            "history", "source_group_id", "retrieval_snapshot", "labels", "teacher",
            "quality", "split", "created_at",
        }
        unknown = sorted(set(data) - known)
        if unknown:
            raise SchemaValidationError(f"unknown fields in sample: {unknown}")
        return _construct(cls, data, "sample")

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, payload: str) -> TrainingSample:
        try:
            data = json.loads(payload)
        except (TypeError, json.JSONDecodeError) as exc:
            raise SchemaValidationError("sample must be valid JSON") from exc
        return cls.from_dict(data)


def write_jsonl(path: Any, samples: Sequence[TrainingSample]) -> int:
    """Write samples as JSONL, one record per line. Returns the count."""

    from pathlib import Path

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for sample in samples:
            handle.write(sample.to_json() + "\n")
    return len(samples)


def read_jsonl(path: Any) -> list[TrainingSample]:
    """Read and re-validate a JSONL dataset."""

    from pathlib import Path

    samples: list[TrainingSample] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                samples.append(TrainingSample.from_json(line))
            except SchemaValidationError as exc:
                raise SchemaValidationError(f"line {line_number}: {exc}") from exc
    return samples


__all__ = [
    "CandidateRole",
    "EvidenceLabel",
    "QualityReport",
    "RetrievalCandidate",
    "RetrievalSnapshot",
    "ReviewStatus",
    "SCHEMA_VERSION",
    "SampleLabels",
    "SchemaValidationError",
    "SegmentLabel",
    "Split",
    "TaskType",
    "TeacherProvenance",
    "TrainingSample",
    "read_jsonl",
    "write_jsonl",
]
