"""Core Self-RAG labels, Reflection Tokens, and serializable results.

The contracts in this module are intentionally separate from ``src.core.types``
so the traditional RAG ``Document``, ``Chunk``, and ``RetrievalResult`` types
remain unchanged. Semantic enum values are stable; tokenizer-specific strings
are supplied by a validated mapping and may be replaced by a future tokenizer
manifest.

Reflection Tokens carry judgements only. Control actions -- rewriting the query,
running another retrieval round, or abstaining -- are decided by
``SelfRAGPolicy`` from those judgements plus thresholds and budget, so this
module deliberately defines no retry/abstain token.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from types import MappingProxyType
from typing import Any, Mapping, Type, TypeVar

from src.core.response.citation_generator import Citation


class RetrieveDecision(str, Enum):
    """Whether the current query or segment needs external knowledge."""

    RETRIEVE = "retrieve"
    NO_RETRIEVE = "no_retrieve"


class RelevanceLabel(str, Enum):
    """Whether a retrieved evidence chunk is relevant."""

    RELEVANT = "relevant"
    IRRELEVANT = "irrelevant"


class SupportLabel(str, Enum):
    """How completely evidence supports a generated segment."""

    FULLY_SUPPORTED = "fully_supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    NOT_SUPPORTED = "not_supported"


class UtilityLabel(IntEnum):
    """Five-level answer utility label, from harmful/unhelpful to complete."""

    UTILITY_1 = 1
    UTILITY_2 = 2
    UTILITY_3 = 3
    UTILITY_4 = 4
    UTILITY_5 = 5


class ReflectionToken(str, Enum):
    """Stable semantic identifiers for configurable Reflection Token text."""

    RETRIEVE = "retrieve"
    NO_RETRIEVE = "no_retrieve"
    RELEVANT = "relevant"
    IRRELEVANT = "irrelevant"
    FULLY_SUPPORTED = "fully_supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    NOT_SUPPORTED = "not_supported"
    UTILITY_1 = "utility_1"
    UTILITY_2 = "utility_2"
    UTILITY_3 = "utility_3"
    UTILITY_4 = "utility_4"
    UTILITY_5 = "utility_5"

    def to_token_text(
        self,
        mapping: Mapping["ReflectionToken | str", str] | None = None,
    ) -> str:
        """Return this semantic token's configured tokenizer text."""

        normalized = validate_reflection_token_mapping(
            DEFAULT_REFLECTION_TOKEN_MAP if mapping is None else mapping
        )
        return normalized[self]

    @classmethod
    def from_token_text(
        cls,
        token_text: str,
        mapping: Mapping["ReflectionToken | str", str] | None = None,
    ) -> "ReflectionToken":
        """Resolve configured token text to its stable semantic identifier."""

        if not isinstance(token_text, str) or not token_text:
            raise ValueError("token_text must be a non-empty string")
        normalized = validate_reflection_token_mapping(
            DEFAULT_REFLECTION_TOKEN_MAP if mapping is None else mapping
        )
        for semantic, configured_text in normalized.items():
            if token_text == configured_text:
                return semantic
        raise ValueError(f"Unknown Reflection Token text: {token_text!r}")


DEFAULT_REFLECTION_TOKEN_MAP: Mapping[ReflectionToken, str] = MappingProxyType(
    {
        ReflectionToken.RETRIEVE: "<RET_YES>",
        ReflectionToken.NO_RETRIEVE: "<RET_NO>",
        ReflectionToken.RELEVANT: "<REL_YES>",
        ReflectionToken.IRRELEVANT: "<REL_NO>",
        ReflectionToken.FULLY_SUPPORTED: "<SUP_FULL>",
        ReflectionToken.PARTIALLY_SUPPORTED: "<SUP_PARTIAL>",
        ReflectionToken.NOT_SUPPORTED: "<SUP_NONE>",
        ReflectionToken.UTILITY_1: "<UTIL_1>",
        ReflectionToken.UTILITY_2: "<UTIL_2>",
        ReflectionToken.UTILITY_3: "<UTIL_3>",
        ReflectionToken.UTILITY_4: "<UTIL_4>",
        ReflectionToken.UTILITY_5: "<UTIL_5>",
    }
)


def validate_reflection_token_mapping(
    mapping: Mapping[ReflectionToken | str, str],
) -> dict[ReflectionToken, str]:
    """Validate and normalize a complete, one-to-one token text mapping."""

    if not isinstance(mapping, Mapping):
        raise ValueError("Reflection Token mapping must be a mapping")

    normalized: dict[ReflectionToken, str] = {}
    for raw_semantic, token_text in mapping.items():
        try:
            semantic = (
                raw_semantic
                if isinstance(raw_semantic, ReflectionToken)
                else ReflectionToken(raw_semantic)
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Unknown Reflection Token semantic: {raw_semantic!r}"
            ) from exc
        if not isinstance(token_text, str) or not token_text or token_text.strip() != token_text:
            raise ValueError(
                f"Token text for {semantic.value!r} must be a non-empty, trimmed string"
            )
        if any(character.isspace() for character in token_text):
            raise ValueError(
                f"Token text for {semantic.value!r} must not contain whitespace"
            )
        normalized[semantic] = token_text

    expected = set(ReflectionToken)
    actual = set(normalized)
    if actual != expected:
        missing = sorted(token.value for token in expected - actual)
        extra = sorted(token.value for token in actual - expected)
        raise ValueError(
            f"Reflection Token mapping must be complete; missing={missing}, extra={extra}"
        )
    if len(set(normalized.values())) != len(normalized):
        raise ValueError("Reflection Token text values must be unique")
    return normalized


EnumType = TypeVar("EnumType", bound=Enum)


def _coerce_enum(value: Any, enum_type: Type[EnumType], field_name: str) -> EnumType:
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {field_name}: {value!r}") from exc


def _probability(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a finite number in [0, 1]")
    normalized = float(value)
    if not math.isfinite(normalized) or not 0.0 <= normalized <= 1.0:
        raise ValueError(f"{field_name} must be a finite number in [0, 1]")
    return normalized


def _optional_probability(value: Any, field_name: str) -> float | None:
    return None if value is None else _probability(value, field_name)


def _json_object(payload: str) -> dict[str, Any]:
    try:
        data = json.loads(payload)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Expected a valid JSON object") from exc
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object")
    return data


@dataclass
class ReflectionScores:
    """Probabilities associated with Self-RAG reflection decisions."""

    retrieval_probability: float
    relevance_probability: float | None = None
    support_probability: float | None = None
    utility_distribution: list[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.retrieval_probability = _probability(
            self.retrieval_probability, "retrieval_probability"
        )
        self.relevance_probability = _optional_probability(
            self.relevance_probability, "relevance_probability"
        )
        self.support_probability = _optional_probability(
            self.support_probability, "support_probability"
        )
        if not isinstance(self.utility_distribution, list):
            raise ValueError("utility_distribution must be a list")
        if self.utility_distribution and len(self.utility_distribution) != 5:
            raise ValueError("utility_distribution must be empty or contain 5 probabilities")
        self.utility_distribution = [
            _probability(value, f"utility_distribution[{index}]")
            for index, value in enumerate(self.utility_distribution)
        ]
        if self.utility_distribution and not math.isclose(
            sum(self.utility_distribution), 1.0, rel_tol=1e-9, abs_tol=1e-9
        ):
            raise ValueError("utility_distribution probabilities must sum to 1")

    def to_dict(self) -> dict[str, Any]:
        return {
            "retrieval_probability": self.retrieval_probability,
            "relevance_probability": self.relevance_probability,
            "support_probability": self.support_probability,
            "utility_distribution": list(self.utility_distribution),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ReflectionScores":
        if not isinstance(data, Mapping):
            raise ValueError("ReflectionScores data must be a mapping")
        return cls(**dict(data))

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, payload: str) -> "ReflectionScores":
        return cls.from_dict(_json_object(payload))


@dataclass
class EvidenceAssessment:
    """A relevance decision for one retrieved chunk."""

    chunk_id: str
    relevance: RelevanceLabel
    confidence: float
    concise_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.chunk_id, str) or not self.chunk_id.strip():
            raise ValueError("chunk_id must be a non-empty string")
        self.relevance = _coerce_enum(
            self.relevance, RelevanceLabel, "relevance"
        )
        self.confidence = _probability(self.confidence, "confidence")
        if self.concise_reason is not None and not isinstance(self.concise_reason, str):
            raise ValueError("concise_reason must be a string or None")

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "relevance": self.relevance.value,
            "confidence": self.confidence,
            "concise_reason": self.concise_reason,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvidenceAssessment":
        if not isinstance(data, Mapping):
            raise ValueError("EvidenceAssessment data must be a mapping")
        return cls(**dict(data))

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, payload: str) -> "EvidenceAssessment":
        return cls.from_dict(_json_object(payload))


@dataclass
class GeneratedSegment:
    """A generated answer segment with explicit evidence and critique labels."""

    text: str
    evidence_ids: list[str]
    support: SupportLabel
    utility: int
    scores: ReflectionScores

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("text must be a non-empty string")
        if not isinstance(self.evidence_ids, list):
            raise ValueError("evidence_ids must be a list")
        if any(not isinstance(item, str) or not item.strip() for item in self.evidence_ids):
            raise ValueError("evidence_ids must contain non-empty strings")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("evidence_ids must not contain duplicates")
        self.support = _coerce_enum(self.support, SupportLabel, "support")
        if isinstance(self.utility, bool) or not isinstance(self.utility, int):
            raise ValueError("utility must be an integer from 1 to 5")
        try:
            UtilityLabel(self.utility)
        except ValueError as exc:
            raise ValueError("utility must be an integer from 1 to 5") from exc
        if isinstance(self.scores, Mapping):
            self.scores = ReflectionScores.from_dict(self.scores)
        elif not isinstance(self.scores, ReflectionScores):
            raise ValueError("scores must be ReflectionScores or a mapping")

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "evidence_ids": list(self.evidence_ids),
            "support": self.support.value,
            "utility": self.utility,
            "scores": self.scores.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "GeneratedSegment":
        if not isinstance(data, Mapping):
            raise ValueError("GeneratedSegment data must be a mapping")
        return cls(**dict(data))

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, payload: str) -> "GeneratedSegment":
        return cls.from_dict(_json_object(payload))


@dataclass
class SelfRAGResult:
    """Final Self-RAG result without changing the traditional MCP response type."""

    answer: str
    citations: list[Citation]
    retrieve_decision: RetrieveDecision
    segments: list[GeneratedSegment]
    retrieval_rounds: int
    termination_reason: str
    fallback_used: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.answer, str):
            raise ValueError("answer must be a string")
        if not isinstance(self.citations, list):
            raise ValueError("citations must be a list")
        normalized_citations: list[Citation] = []
        for citation in self.citations:
            if isinstance(citation, Citation):
                normalized_citations.append(citation)
            elif isinstance(citation, Mapping):
                normalized_citations.append(Citation(**dict(citation)))
            else:
                raise ValueError("citations must contain Citation objects or mappings")
        self.citations = normalized_citations
        self.retrieve_decision = _coerce_enum(
            self.retrieve_decision, RetrieveDecision, "retrieve_decision"
        )
        if not isinstance(self.segments, list):
            raise ValueError("segments must be a list")
        self.segments = [
            segment
            if isinstance(segment, GeneratedSegment)
            else GeneratedSegment.from_dict(segment)
            if isinstance(segment, Mapping)
            else _invalid_segment()
            for segment in self.segments
        ]
        if (
            isinstance(self.retrieval_rounds, bool)
            or not isinstance(self.retrieval_rounds, int)
            or self.retrieval_rounds < 0
        ):
            raise ValueError("retrieval_rounds must be a non-negative integer")
        if not isinstance(self.termination_reason, str) or not self.termination_reason.strip():
            raise ValueError("termination_reason must be a non-empty string")
        if not isinstance(self.fallback_used, bool):
            raise ValueError("fallback_used must be a boolean")

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "citations": [citation.to_dict() for citation in self.citations],
            "retrieve_decision": self.retrieve_decision.value,
            "segments": [segment.to_dict() for segment in self.segments],
            "retrieval_rounds": self.retrieval_rounds,
            "termination_reason": self.termination_reason,
            "fallback_used": self.fallback_used,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SelfRAGResult":
        if not isinstance(data, Mapping):
            raise ValueError("SelfRAGResult data must be a mapping")
        return cls(**dict(data))

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, payload: str) -> "SelfRAGResult":
        return cls.from_dict(_json_object(payload))


def _invalid_segment() -> GeneratedSegment:
    raise ValueError("segments must contain GeneratedSegment objects or mappings")


__all__ = [
    "DEFAULT_REFLECTION_TOKEN_MAP",
    "EvidenceAssessment",
    "GeneratedSegment",
    "ReflectionScores",
    "ReflectionToken",
    "RelevanceLabel",
    "RetrieveDecision",
    "SelfRAGResult",
    "SupportLabel",
    "UtilityLabel",
    "validate_reflection_token_mapping",
]
