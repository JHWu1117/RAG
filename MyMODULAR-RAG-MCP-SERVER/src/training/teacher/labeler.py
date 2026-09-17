"""Versioned multi-pass Teacher labeling for unified Critic samples."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.core.self_rag_types import RelevanceLabel, RetrieveDecision, SupportLabel
from src.training.data.schemas import (
    EvidenceLabel,
    QualityReport,
    RetrievalSnapshot,
    ReviewStatus,
    SampleLabels,
    SchemaValidationError,
    SegmentLabel,
    Split,
    TeacherProvenance,
    TrainingSample,
)
from src.training.data.synthetic_query_generator import SyntheticQuery
from src.training.teacher.base_teacher import BaseTeacherLLM, TeacherError, TeacherResult

PROMPT_VERSION = "reflection-labels-v1"
_PROMPT_FILES = {
    "retrieval": "retrieval_v1.md",
    "relevance": "relevance_v1.md",
    "grounded_answer": "grounded_answer_v1.md",
    "support": "support_v1.md",
    "utility": "utility_v1.md",
}


@dataclass(frozen=True)
class QuarantinedLabeling:
    query_id: str
    source_group_id: str
    reason: str
    error_type: str

    def to_dict(self) -> dict[str, str]:
        return {
            "query_id": self.query_id,
            "source_group_id": self.source_group_id,
            "reason": self.reason,
            "error_type": self.error_type,
        }


@dataclass(frozen=True)
class LabelingOutcome:
    sample: TrainingSample | None = None
    quarantine: QuarantinedLabeling | None = None

    def __post_init__(self) -> None:
        if (self.sample is None) == (self.quarantine is None):
            raise ValueError("LabelingOutcome requires exactly one result")


class ReflectionLabeler:
    """Run independent judgment prompts and merge only validated outputs."""

    def __init__(
        self,
        teacher: BaseTeacherLLM,
        *,
        dataset_version: str,
        prompt_dir: str | Path | None = None,
        temperature: float = 0.0,
    ) -> None:
        self._teacher = teacher
        self._dataset_version = dataset_version
        self._temperature = temperature
        root = Path(__file__).resolve().parents[3]
        self._prompt_dir = Path(prompt_dir) if prompt_dir else (
            root / "config" / "prompts" / "self_rag" / "teacher"
        )
        self._prompts = {
            name: (self._prompt_dir / filename).read_text(encoding="utf-8")
            for name, filename in _PROMPT_FILES.items()
        }
        canonical_prompts = json.dumps(
            self._prompts, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        self.prompt_hash = "sha256:" + hashlib.sha256(
            canonical_prompts.encode("utf-8")
        ).hexdigest()

    def label(
        self,
        query: SyntheticQuery,
        snapshot: RetrievalSnapshot,
        *,
        split: Split = Split.TRAIN,
    ) -> LabelingOutcome:
        try:
            if snapshot.query != query.instruction:
                raise SchemaValidationError("retrieval snapshot query does not match instruction")
            retrieval = self._ask(
                "retrieval",
                {"instruction": query.instruction, "task_type": query.task_type.value},
                self._retrieval_schema(),
            )
            relevance = self._ask(
                "relevance",
                self._context_payload(query, snapshot),
                self._relevance_schema(),
            )
            answer = self._ask(
                "grounded_answer",
                self._context_payload(query, snapshot),
                self._answer_schema(),
            )
            support = self._ask(
                "support",
                {
                    **self._context_payload(query, snapshot),
                    "segments": answer.data["segments"],
                },
                self._support_schema(),
            )
            utility = self._ask(
                "utility",
                {
                    "instruction": query.instruction,
                    "final_answer": answer.data["final_answer"],
                    "segments": answer.data["segments"],
                },
                self._utility_schema(),
            )
            sample = self._merge(
                query, snapshot, split, retrieval, relevance, answer, support, utility
            )
            return LabelingOutcome(sample=sample)
        except (TeacherError, SchemaValidationError, KeyError, TypeError, ValueError) as exc:
            return LabelingOutcome(
                quarantine=QuarantinedLabeling(
                    query_id=query.query_id,
                    source_group_id=query.source_group_id,
                    reason=str(exc)[:300] or type(exc).__name__,
                    error_type=type(exc).__name__,
                )
            )

    def _ask(
        self, name: str, payload: Mapping[str, Any], schema: Mapping[str, Any]
    ) -> TeacherResult:
        prompt = self._prompts[name] + "\n\nINPUT_JSON:\n" + json.dumps(
            payload, ensure_ascii=False, sort_keys=True
        )
        try:
            return self._teacher.generate_structured(
                prompt,
                schema,
                system_prompt="你是严格、保守的企业知识数据标注器。只输出符合 Schema 的 JSON。",
                schema_name=f"selfrag_{name}_v1",
            )
        except TeacherError as exc:
            raise TeacherError(f"{name}: {exc}") from exc

    @staticmethod
    def _context_payload(
        query: SyntheticQuery, snapshot: RetrievalSnapshot
    ) -> dict[str, Any]:
        return {
            "instruction": query.instruction,
            "task_type": query.task_type.value,
            "candidates": [
                {"chunk_id": item.chunk_id, "text": item.text, "source": item.source}
                for item in snapshot.candidates
            ],
        }

    def _merge(
        self,
        query: SyntheticQuery,
        snapshot: RetrievalSnapshot,
        split: Split,
        *results: TeacherResult,
    ) -> TrainingSample:
        retrieval, relevance, answer, support, utility = results
        expected_ids = snapshot.chunk_ids
        evidence_data = relevance.data["evidence"]
        labelled_ids = [item["chunk_id"] for item in evidence_data]
        if len(labelled_ids) != len(set(labelled_ids)) or set(labelled_ids) != expected_ids:
            raise SchemaValidationError(
                "relevance output must label every candidate exactly once"
            )
        segments_data = answer.data["segments"]
        support_by_index = self._index_judgments(
            support.data["segments"], len(segments_data), "support"
        )
        utility_by_index = self._index_judgments(
            utility.data["segments"], len(segments_data), "utility"
        )
        segments = []
        for index, segment in enumerate(segments_data):
            support_item = support_by_index[index]
            utility_item = utility_by_index[index]
            segments.append(
                SegmentLabel(
                    text=segment["text"],
                    evidence_ids=list(segment["evidence_ids"]),
                    support=support_item["support"],
                    utility=utility_item["utility"],
                    support_reason=support_item["concise_reason"],
                    utility_reason=utility_item["concise_reason"],
                )
            )
        confidences = [float(result.data["confidence"]) for result in results]
        response_hash = "sha256:" + hashlib.sha256(
            "|".join(result.raw_response_hash for result in results).encode("utf-8")
        ).hexdigest()
        request_id = "label:" + hashlib.sha256(
            f"{query.query_id}|{response_hash}".encode()
        ).hexdigest()[:24]
        providers = "+".join(dict.fromkeys(result.provider for result in results))
        models = "+".join(dict.fromkeys(result.model for result in results))
        return TrainingSample(
            dataset_version=self._dataset_version,
            task_type=query.task_type,
            instruction=query.instruction,
            source_group_id=query.source_group_id,
            retrieval_snapshot=snapshot,
            labels=SampleLabels(
                retrieve=RetrieveDecision(retrieval.data["retrieve"]),
                evidence=[
                    EvidenceLabel(
                        chunk_id=item["chunk_id"],
                        relevance=RelevanceLabel(item["relevance"]),
                        concise_reason=item["concise_reason"],
                    )
                    for item in evidence_data
                ],
                segments=segments,
                final_answer=answer.data["final_answer"],
            ),
            teacher=TeacherProvenance(
                provider=providers,
                model=models,
                prompt_version=PROMPT_VERSION,
                prompt_hash=self.prompt_hash,
                request_id=request_id,
                temperature=self._temperature,
                raw_response_hash=response_hash,
                label_confidence=min(confidences),
            ),
            quality=QualityReport(
                schema_valid=True,
                rule_checks=["evidence_ids_exist", "known_label_enums"],
                agreement="single_teacher",
                review_status=ReviewStatus.ACCEPTED,
            ),
            split=split,
        )

    @staticmethod
    def _index_judgments(
        values: Sequence[Mapping[str, Any]], expected: int, label: str
    ) -> dict[int, Mapping[str, Any]]:
        indexed = {int(item["segment_index"]): item for item in values}
        if len(indexed) != len(values) or set(indexed) != set(range(expected)):
            raise SchemaValidationError(
                f"{label} output must label every segment exactly once"
            )
        return indexed

    @staticmethod
    def _retrieval_schema() -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "retrieve": {"type": "string", "enum": [item.value for item in RetrieveDecision]},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "concise_reason": {"type": "string", "minLength": 1, "maxLength": 160},
            },
            "required": ["retrieve", "confidence", "concise_reason"],
            "additionalProperties": False,
        }

    @staticmethod
    def _relevance_schema() -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "evidence": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "chunk_id": {"type": "string", "minLength": 1},
                            "relevance": {"type": "string", "enum": [item.value for item in RelevanceLabel]},
                            "concise_reason": {"type": "string", "minLength": 1, "maxLength": 160},
                        },
                        "required": ["chunk_id", "relevance", "concise_reason"],
                        "additionalProperties": False,
                    },
                },
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["evidence", "confidence"],
            "additionalProperties": False,
        }

    @staticmethod
    def _answer_schema() -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "final_answer": {"type": "string"},
                "segments": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string", "minLength": 1},
                            "evidence_ids": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
                        },
                        "required": ["text", "evidence_ids"],
                        "additionalProperties": False,
                    },
                },
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["final_answer", "segments", "confidence"],
            "additionalProperties": False,
        }

    @staticmethod
    def _support_schema() -> dict[str, Any]:
        return ReflectionLabeler._segment_judgment_schema(
            "support", {"type": "string", "enum": [item.value for item in SupportLabel]}
        )

    @staticmethod
    def _utility_schema() -> dict[str, Any]:
        return ReflectionLabeler._segment_judgment_schema(
            "utility", {"type": "integer", "minimum": 1, "maximum": 5}
        )

    @staticmethod
    def _segment_judgment_schema(name: str, value_schema: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "segments": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "segment_index": {"type": "integer", "minimum": 0},
                            name: dict(value_schema),
                            "concise_reason": {"type": "string", "minLength": 1, "maxLength": 160},
                        },
                        "required": ["segment_index", name, "concise_reason"],
                        "additionalProperties": False,
                    },
                },
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["segments", "confidence"],
            "additionalProperties": False,
        }


__all__ = [
    "LabelingOutcome",
    "PROMPT_VERSION",
    "QuarantinedLabeling",
    "ReflectionLabeler",
]
