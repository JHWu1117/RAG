"""Quota-driven, deterministic synthetic-query generation for Self-RAG data."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from src.training.data.schemas import SchemaValidationError, TaskType
from src.training.data.seed_collector import CanonicalSeed


class QueryKind(str, Enum):
    FACTUAL = "factual"
    MULTI_HOP = "multi_hop"
    COMPARISON = "comparison"
    SUMMARY = "summary"
    NO_RETRIEVAL = "no_retrieval"
    UNANSWERABLE = "unanswerable"

    @property
    def requires_retrieval(self) -> bool:
        return self is not QueryKind.NO_RETRIEVAL

    @property
    def task_type(self) -> TaskType:
        if self is QueryKind.NO_RETRIEVAL:
            return TaskType.RETRIEVAL_DECISION
        if self is QueryKind.UNANSWERABLE:
            return TaskType.INSUFFICIENT_EVIDENCE
        return TaskType.GROUNDED_GENERATION


@dataclass(frozen=True)
class QueryGenerationRequest:
    seed_id: str
    source_group_id: str
    source_text: str
    query_kind: QueryKind
    language: str
    prompt_version: str


class QueryTeacher(Protocol):
    """Small K3 interface implemented by FakeTeacher now and K5 providers later."""

    def generate_query(self, request: QueryGenerationRequest) -> Mapping[str, Any]: ...


@dataclass
class SyntheticQuery:
    instruction: str
    source_group_id: str
    source_seed_id: str
    query_kind: QueryKind
    task_type: TaskType
    language: str
    requires_retrieval: bool
    prompt_version: str
    reference_answer: str | None = None
    query_id: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.instruction, str) or not self.instruction.strip():
            raise SchemaValidationError("synthetic instruction must be non-empty")
        if not isinstance(self.query_kind, QueryKind):
            self.query_kind = QueryKind(self.query_kind)
        if not isinstance(self.task_type, TaskType):
            self.task_type = TaskType(self.task_type)
        if self.task_type is not self.query_kind.task_type:
            raise SchemaValidationError("task_type does not match query_kind")
        if self.requires_retrieval is not self.query_kind.requires_retrieval:
            raise SchemaValidationError("requires_retrieval does not match query_kind")
        for name, value in (
            ("source_group_id", self.source_group_id),
            ("source_seed_id", self.source_seed_id),
            ("language", self.language),
            ("prompt_version", self.prompt_version),
        ):
            if not isinstance(value, str) or not value.strip():
                raise SchemaValidationError(f"{name} must be non-empty")
        payload = self._identity_payload()
        computed = "sha256:" + hashlib.sha256(
            json.dumps(
                payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()
        if self.query_id and self.query_id != computed:
            raise SchemaValidationError("query_id does not match query content")
        self.query_id = computed

    def _identity_payload(self) -> dict[str, Any]:
        return {
            "instruction": self.instruction,
            "source_group_id": self.source_group_id,
            "source_seed_id": self.source_seed_id,
            "query_kind": self.query_kind.value,
            "task_type": self.task_type.value,
            "language": self.language,
            "requires_retrieval": self.requires_retrieval,
            "prompt_version": self.prompt_version,
            "reference_answer": self.reference_answer,
        }

    def to_dict(self) -> dict[str, Any]:
        return {"query_id": self.query_id, **self._identity_payload()}


@dataclass(frozen=True)
class GenerationPlan:
    total: int
    query_kind_quotas: dict[QueryKind, int]
    language_quotas: dict[str, int]


@dataclass
class GenerationResult:
    plan: GenerationPlan
    queries: list[SyntheticQuery] = field(default_factory=list)
    teacher_calls: int = 0
    duplicates_rejected: int = 0


class SyntheticQueryGenerator:
    """Generate exact configured quotas while preserving source provenance."""

    def __init__(
        self,
        teacher: QueryTeacher,
        *,
        prompt_version: str = "query-generation-v1",
        max_attempts_per_query: int = 3,
    ) -> None:
        if max_attempts_per_query < 1:
            raise ValueError("max_attempts_per_query must be >= 1")
        self._teacher = teacher
        self._prompt_version = prompt_version
        self._max_attempts = max_attempts_per_query

    def plan(
        self,
        total: int,
        query_kind_ratios: Mapping[QueryKind | str, float],
        language_ratios: Mapping[str, float],
    ) -> GenerationPlan:
        if isinstance(total, bool) or not isinstance(total, int) or total < 1:
            raise ValueError("total must be a positive integer")
        kinds = {QueryKind(key): value for key, value in query_kind_ratios.items()}
        if set(kinds) != set(QueryKind):
            missing = sorted(kind.value for kind in set(QueryKind) - set(kinds))
            extra = sorted(str(key) for key in set(kinds) - set(QueryKind))
            raise ValueError(f"query kind ratios must be complete; missing={missing}, extra={extra}")
        languages = {
            str(key): value for key, value in language_ratios.items() if str(key).strip()
        }
        if not languages:
            raise ValueError("at least one language ratio is required")
        return GenerationPlan(
            total=total,
            query_kind_quotas=self._allocate(total, kinds, "query kind"),
            language_quotas=self._allocate(total, languages, "language"),
        )

    def generate(
        self,
        seeds: Sequence[CanonicalSeed],
        *,
        total: int,
        query_kind_ratios: Mapping[QueryKind | str, float],
        language_ratios: Mapping[str, float],
        dry_run: bool = False,
    ) -> GenerationResult:
        plan = self.plan(total, query_kind_ratios, language_ratios)
        result = GenerationResult(plan=plan)
        if dry_run:
            return result
        if not seeds:
            raise ValueError("at least one canonical seed is required")
        ordered_seeds = sorted(seeds, key=lambda item: item.seed_id)
        kind_slots = self._slots(plan.query_kind_quotas, key=lambda item: item.value)
        language_slots = self._slots(plan.language_quotas, key=str)
        seen: set[str] = set()

        for slot, (kind, language) in enumerate(zip(kind_slots, language_slots)):
            for attempt in range(self._max_attempts):
                seed = ordered_seeds[(slot + attempt) % len(ordered_seeds)]
                request = QueryGenerationRequest(
                    seed_id=seed.seed_id,
                    source_group_id=seed.source_group_id,
                    source_text=seed.content,
                    query_kind=kind,
                    language=language,
                    prompt_version=self._prompt_version,
                )
                draft = self._teacher.generate_query(request)
                result.teacher_calls += 1
                if not isinstance(draft, Mapping):
                    raise SchemaValidationError("query teacher output must be an object")
                instruction = draft.get("instruction") or draft.get("query")
                if not isinstance(instruction, str) or not instruction.strip():
                    raise SchemaValidationError(
                        "query teacher output requires a non-empty instruction"
                    )
                normalized = self._normalize(instruction)
                if normalized in seen:
                    result.duplicates_rejected += 1
                    continue
                seen.add(normalized)
                answer = draft.get("reference_answer")
                if answer is not None and not isinstance(answer, str):
                    raise SchemaValidationError("reference_answer must be a string or null")
                result.queries.append(
                    SyntheticQuery(
                        instruction=instruction.strip(),
                        source_group_id=seed.source_group_id,
                        source_seed_id=seed.seed_id,
                        query_kind=kind,
                        task_type=kind.task_type,
                        language=language,
                        requires_retrieval=kind.requires_retrieval,
                        prompt_version=self._prompt_version,
                        reference_answer=answer,
                    )
                )
                break
            else:
                raise RuntimeError(
                    f"teacher could not produce a unique {kind.value} query "
                    f"after {self._max_attempts} attempts"
                )

        return result

    @staticmethod
    def _allocate(total: int, ratios: Mapping[Any, float], label: str) -> dict[Any, int]:
        if any(
            isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0
            for value in ratios.values()
        ):
            raise ValueError(f"{label} ratios must be non-negative numbers")
        ratio_sum = float(sum(ratios.values()))
        if abs(ratio_sum - 1.0) > 1e-9:
            raise ValueError(f"{label} ratios must sum to 1.0")
        exact = {key: total * float(value) for key, value in ratios.items()}
        allocated = {key: int(value) for key, value in exact.items()}
        remainder = total - sum(allocated.values())
        ranked = sorted(
            ratios,
            key=lambda key: (-(exact[key] - allocated[key]), str(key)),
        )
        for key in ranked[:remainder]:
            allocated[key] += 1
        return allocated

    @staticmethod
    def _slots(quotas: Mapping[Any, int], *, key: Any) -> list[Any]:
        slots: list[Any] = []
        for value in sorted(quotas, key=key):
            slots.extend([value] * quotas[value])
        return slots

    @staticmethod
    def _normalize(instruction: str) -> str:
        return re.sub(r"[^\w\u4e00-\u9fff]+", "", instruction.casefold())


def query_kind_distribution(queries: Sequence[SyntheticQuery]) -> dict[str, int]:
    return dict(Counter(query.query_kind.value for query in queries))


__all__ = [
    "GenerationPlan",
    "GenerationResult",
    "QueryGenerationRequest",
    "QueryKind",
    "QueryTeacher",
    "SyntheticQuery",
    "SyntheticQueryGenerator",
    "query_kind_distribution",
]
