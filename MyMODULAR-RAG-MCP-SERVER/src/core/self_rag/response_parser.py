"""J2 Self-RAG response parsing and normalization.

Provider output reaches this module as native structured JSON, as free text
carrying Reflection Tokens, or as JSON embedded in prose. The parser resolves
all three into one validated domain object using a fixed strategy order:
native structured JSON, Reflection Token state machine, constrained JSON
extraction, a single format-repair retry, then a deterministic ``ParseError``.

Unparsed text is never returned as a validated result, hidden reasoning and
provider metadata are never propagated, and confidence stays ``None`` when the
provider supplied no logprobs.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable, Mapping, Sequence

from src.core.self_rag_types import (
    DEFAULT_REFLECTION_TOKEN_MAP,
    ReflectionScores,
    ReflectionToken,
    RelevanceLabel,
    RetrieveDecision,
    SupportLabel,
    UtilityLabel,
    validate_reflection_token_mapping,
)


class ParseStage(str, Enum):
    """Which strategy produced a parsed result."""

    STRUCTURED_JSON = "structured_json"
    CONTROL_TOKENS = "control_tokens"
    EXTRACTED_JSON = "extracted_json"
    REPAIRED_JSON = "repaired_json"


class ParseError(ValueError):
    """Raised when a provider response cannot be parsed into a valid result.

    The message describes the structural failure only. Raw response text,
    hidden reasoning, and provider metadata are deliberately excluded so that
    parse failures cannot leak them into logs, traces, or MCP responses.
    """

    def __init__(self, message: str, *, stage: ParseStage | None = None) -> None:
        super().__init__(message)
        self.stage = stage


@dataclass
class RawModelResponse:
    """Structured provider response consumed by the parser.

    ``reasoning_text`` and ``provider_metadata`` stay in memory only; the
    parser never copies them into a parsed result.
    """

    text: str
    finish_reason: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    logprobs: Mapping[str, float] | None = None
    reasoning_text: str | None = None
    provider_metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise ValueError("text must be a string")
        if self.logprobs is not None and not isinstance(self.logprobs, Mapping):
            raise ValueError("logprobs must be a mapping or None")


@dataclass
class ParsedReflection:
    """Normalized reflection signals extracted from one provider response."""

    answer: str
    source: ParseStage
    retrieve_decision: RetrieveDecision | None = None
    relevance: RelevanceLabel | None = None
    support: SupportLabel | None = None
    utility: int | None = None
    evidence_ids: list[str] = field(default_factory=list)
    confidence: float | None = None
    scores: ReflectionScores | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "source": self.source.value,
            "retrieve_decision": (
                self.retrieve_decision.value if self.retrieve_decision else None
            ),
            "relevance": self.relevance.value if self.relevance else None,
            "support": self.support.value if self.support else None,
            "utility": self.utility,
            "evidence_ids": list(self.evidence_ids),
            "confidence": self.confidence,
            "scores": self.scores.to_dict() if self.scores else None,
        }


RepairFn = Callable[[str, str], "str | Mapping[str, Any] | RawModelResponse"]

REQUIREABLE_FIELDS = frozenset(
    {
        "answer",
        "retrieve_decision",
        "relevance",
        "support",
        "utility",
        "evidence_ids",
        "confidence",
        "scores",
    }
)

_RETRIEVE_TOKENS = {
    ReflectionToken.RETRIEVE: RetrieveDecision.RETRIEVE,
    ReflectionToken.NO_RETRIEVE: RetrieveDecision.NO_RETRIEVE,
}
_RELEVANCE_TOKENS = {
    ReflectionToken.RELEVANT: RelevanceLabel.RELEVANT,
    ReflectionToken.IRRELEVANT: RelevanceLabel.IRRELEVANT,
}
_SUPPORT_TOKENS = {
    ReflectionToken.FULLY_SUPPORTED: SupportLabel.FULLY_SUPPORTED,
    ReflectionToken.PARTIALLY_SUPPORTED: SupportLabel.PARTIALLY_SUPPORTED,
    ReflectionToken.NOT_SUPPORTED: SupportLabel.NOT_SUPPORTED,
}
_UTILITY_TOKENS = {
    ReflectionToken.UTILITY_1: 1,
    ReflectionToken.UTILITY_2: 2,
    ReflectionToken.UTILITY_3: 3,
    ReflectionToken.UTILITY_4: 4,
    ReflectionToken.UTILITY_5: 5,
}
_FENCED_BLOCK_RE = re.compile(r"```[a-zA-Z0-9_-]*\s*\n?(.*?)```", re.DOTALL)


class SelfRAGResponseParser:
    """Parse provider responses into validated Self-RAG reflection signals."""

    def __init__(
        self,
        token_map: Mapping[ReflectionToken | str, str] | None = None,
        repair_fn: RepairFn | None = None,
    ) -> None:
        self._token_map = validate_reflection_token_mapping(
            DEFAULT_REFLECTION_TOKEN_MAP if token_map is None else token_map
        )
        self._text_to_token = {text: token for token, text in self._token_map.items()}
        # Longest-first so no token text is shadowed by a shorter prefix match.
        self._token_texts = sorted(self._text_to_token, key=len, reverse=True)
        self._repair_fn = repair_fn

    def parse(
        self,
        raw: str | Mapping[str, Any] | RawModelResponse,
        *,
        required_fields: Sequence[str] = (),
    ) -> ParsedReflection:
        """Parse one provider response, applying the fixed strategy order."""

        required = self._validate_required_fields(required_fields)
        response = self._coerce_response(raw)
        result = self._parse_response(response, required, allow_repair=True)
        return result

    def parse_stream(
        self,
        chunks: Iterable[str],
        *,
        logprobs: Mapping[str, float] | None = None,
        required_fields: Sequence[str] = (),
    ) -> ParsedReflection:
        """Parse streamed chunks, joining them before any token scanning.

        Joining first is what makes control tokens split across chunk
        boundaries safe to detect.
        """

        parts: list[str] = []
        for index, chunk in enumerate(chunks):
            if not isinstance(chunk, str):
                raise ParseError(f"Stream chunk at index {index} is not a string")
            parts.append(chunk)
        response = RawModelResponse(text="".join(parts), logprobs=logprobs)
        return self.parse(response, required_fields=required_fields)

    # -- strategy dispatch -------------------------------------------------

    def _parse_response(
        self,
        response: RawModelResponse,
        required: tuple[str, ...],
        *,
        allow_repair: bool,
    ) -> ParsedReflection:
        text = response.text.strip()
        if not text:
            return self._repair_or_fail(
                response, required, "Provider response is empty", allow_repair
            )

        payload = _whole_json_object(text)
        if payload is not None:
            try:
                return self._from_payload(
                    payload, response, ParseStage.STRUCTURED_JSON, required
                )
            except ParseError as error:
                return self._repair_or_fail(
                    response, required, str(error), allow_repair
                )

        if any(token_text in text for token_text in self._token_texts):
            try:
                return self._from_control_tokens(response, required)
            except ParseError as error:
                return self._repair_or_fail(
                    response, required, str(error), allow_repair
                )

        extracted = self._extract_json_object(text)
        if extracted is not None:
            try:
                return self._from_payload(
                    extracted, response, ParseStage.EXTRACTED_JSON, required
                )
            except ParseError as error:
                return self._repair_or_fail(
                    response, required, str(error), allow_repair
                )

        return self._repair_or_fail(
            response,
            required,
            "Response contains no structured JSON object and no Reflection Token",
            allow_repair,
        )

    def _repair_or_fail(
        self,
        response: RawModelResponse,
        required: tuple[str, ...],
        reason: str,
        allow_repair: bool,
    ) -> ParsedReflection:
        if not (allow_repair and self._repair_fn is not None):
            raise ParseError(reason)

        try:
            repaired_raw = self._repair_fn(reason, response.text)
        except Exception as exc:  # noqa: BLE001 - provider failures are reported, not raised
            raise ParseError(
                f"Format repair failed after: {reason}"
            ) from exc

        repaired = self._coerce_response(repaired_raw)
        # A single repair attempt only; the retry never repairs again.
        result = self._parse_response(repaired, required, allow_repair=False)
        return ParsedReflection(
            answer=result.answer,
            source=ParseStage.REPAIRED_JSON,
            retrieve_decision=result.retrieve_decision,
            relevance=result.relevance,
            support=result.support,
            utility=result.utility,
            evidence_ids=result.evidence_ids,
            confidence=result.confidence,
            scores=result.scores,
        )

    # -- strategy 1 & 3: JSON payloads -------------------------------------

    def _from_payload(
        self,
        payload: Mapping[str, Any],
        response: RawModelResponse,
        stage: ParseStage,
        required: tuple[str, ...],
    ) -> ParsedReflection:
        answer = payload.get("answer", "")
        if answer is None:
            answer = ""
        if not isinstance(answer, str):
            raise ParseError("Field 'answer' must be a string", stage=stage)

        retrieve_decision = _optional_enum(
            payload.get("retrieve_decision"), RetrieveDecision, "retrieve_decision", stage
        )
        relevance = _optional_enum(
            payload.get("relevance"), RelevanceLabel, "relevance", stage
        )
        support = _optional_enum(payload.get("support"), SupportLabel, "support", stage)
        utility = _optional_utility(payload.get("utility"), stage)
        evidence_ids = _evidence_ids(payload.get("evidence_ids"), stage)

        scores: ReflectionScores | None = None
        raw_scores = payload.get("scores")
        if raw_scores is not None:
            if not isinstance(raw_scores, Mapping):
                raise ParseError("Field 'scores' must be an object", stage=stage)
            try:
                scores = ReflectionScores.from_dict(raw_scores)
            except (TypeError, ValueError) as exc:
                raise ParseError(f"Invalid 'scores': {exc}", stage=stage) from exc

        confidence = payload.get("confidence")
        if confidence is None:
            confidence = self._confidence_from_logprobs(response, retrieve_decision)
        else:
            confidence = _probability(confidence, "confidence", stage)

        result = ParsedReflection(
            answer=self._clean_answer(answer),
            source=stage,
            retrieve_decision=retrieve_decision,
            relevance=relevance,
            support=support,
            utility=utility,
            evidence_ids=evidence_ids,
            confidence=confidence,
            scores=scores,
        )
        self._check_required(result, required, stage)
        return result

    # -- strategy 2: Reflection Token state machine ------------------------

    def _from_control_tokens(
        self, response: RawModelResponse, required: tuple[str, ...]
    ) -> ParsedReflection:
        stage = ParseStage.CONTROL_TOKENS
        tokens = self._scan_tokens(response.text)
        if not tokens:
            raise ParseError("No complete Reflection Token found", stage=stage)

        retrieve_decision = _reduce_category(
            tokens, _RETRIEVE_TOKENS, "retrieval decision", stage
        )
        relevance = _reduce_category(tokens, _RELEVANCE_TOKENS, "relevance", stage)
        support = _reduce_category(tokens, _SUPPORT_TOKENS, "support", stage)
        utility = _reduce_category(tokens, _UTILITY_TOKENS, "utility", stage)

        result = ParsedReflection(
            answer=self._clean_answer(response.text),
            source=stage,
            retrieve_decision=retrieve_decision,
            relevance=relevance,
            support=support,
            utility=utility,
            confidence=self._confidence_from_logprobs(response, retrieve_decision),
        )
        self._check_required(result, required, stage)
        return result

    def _scan_tokens(self, text: str) -> list[ReflectionToken]:
        """Scan for whole registered token texts, longest match first."""

        found: list[ReflectionToken] = []
        index = 0
        length = len(text)
        while index < length:
            for token_text in self._token_texts:
                if text.startswith(token_text, index):
                    found.append(self._text_to_token[token_text])
                    index += len(token_text)
                    break
            else:
                index += 1
        return found

    def _remove_tokens(self, text: str) -> str:
        cleaned: list[str] = []
        index = 0
        length = len(text)
        while index < length:
            for token_text in self._token_texts:
                if text.startswith(token_text, index):
                    index += len(token_text)
                    break
            else:
                cleaned.append(text[index])
                index += 1
        return "".join(cleaned)

    def _clean_answer(self, text: str) -> str:
        cleaned = self._remove_tokens(text)
        cleaned = re.sub(r"[ \t]+", " ", cleaned)
        cleaned = re.sub(r" *\n *", "\n", cleaned)
        return cleaned.strip()

    # -- shared helpers ----------------------------------------------------

    def _confidence_from_logprobs(
        self, response: RawModelResponse, decision: RetrieveDecision | None
    ) -> float | None:
        """Derive confidence from logprobs, or return None. Never fabricated."""

        if response.logprobs is None or decision is None:
            return None
        token = (
            ReflectionToken.RETRIEVE
            if decision is RetrieveDecision.RETRIEVE
            else ReflectionToken.NO_RETRIEVE
        )
        logprob = response.logprobs.get(self._token_map[token])
        if logprob is None or isinstance(logprob, bool) or not isinstance(logprob, (int, float)):
            return None
        if not math.isfinite(float(logprob)) or logprob > 0:
            return None
        return min(1.0, max(0.0, math.exp(float(logprob))))

    def _extract_json_object(self, text: str) -> dict[str, Any] | None:
        """Recover JSON from a single fenced block or one balanced object."""

        candidates = [
            block.strip()
            for block in _FENCED_BLOCK_RE.findall(text)
            if block.strip().startswith("{")
        ]
        if not candidates:
            candidates = _balanced_json_objects(text)
        if len(candidates) != 1:
            return None
        return _whole_json_object(candidates[0])

    @staticmethod
    def _coerce_response(
        raw: str | Mapping[str, Any] | RawModelResponse,
    ) -> RawModelResponse:
        if isinstance(raw, RawModelResponse):
            return raw
        if isinstance(raw, str):
            return RawModelResponse(text=raw)
        if isinstance(raw, Mapping):
            try:
                return RawModelResponse(**dict(raw))
            except (TypeError, ValueError) as exc:
                raise ParseError(f"Invalid provider response object: {exc}") from exc
        raise ParseError(
            "Provider response must be a string, mapping, or RawModelResponse"
        )

    def _validate_required_fields(self, required_fields: Sequence[str]) -> tuple[str, ...]:
        required = tuple(required_fields)
        unknown = sorted(set(required) - REQUIREABLE_FIELDS)
        if unknown:
            raise ValueError(f"Unknown required fields: {unknown}")
        return required

    def _check_required(
        self, result: ParsedReflection, required: tuple[str, ...], stage: ParseStage
    ) -> None:
        for name in required:
            value = getattr(result, name)
            missing = value is None or (isinstance(value, (str, list)) and not value)
            if missing:
                raise ParseError(f"Missing required field: {name}", stage=stage)


def _whole_json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped.startswith("{"):
        return None
    try:
        data = json.loads(stripped)
    except (TypeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _balanced_json_objects(text: str) -> list[str]:
    """Return every top-level balanced ``{...}`` span, string-literal aware."""

    objects: list[str] = []
    depth = 0
    start = -1
    in_string = False
    escaped = False
    for index, character in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character == "{":
            if depth == 0:
                start = index
            depth += 1
        elif character == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start >= 0:
                    objects.append(text[start : index + 1])
                    start = -1
    return objects


def _optional_enum(
    value: Any, enum_type: type[Enum], field_name: str, stage: ParseStage
) -> Any:
    if value is None:
        return None
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        raise ParseError(
            f"Invalid value for '{field_name}': {value!r}", stage=stage
        ) from exc


def _optional_utility(value: Any, stage: ParseStage) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ParseError(
            f"Invalid value for 'utility': {value!r}", stage=stage
        )
    try:
        return int(UtilityLabel(value))
    except ValueError as exc:
        raise ParseError(
            f"Invalid value for 'utility': {value!r}", stage=stage
        ) from exc


def _evidence_ids(value: Any, stage: ParseStage) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ParseError("Field 'evidence_ids' must be a list", stage=stage)
    ids: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ParseError(
                "Field 'evidence_ids' must contain non-empty strings", stage=stage
            )
        ids.append(item)
    if len(set(ids)) != len(ids):
        raise ParseError("Field 'evidence_ids' must not contain duplicates", stage=stage)
    return ids


def _probability(value: Any, field_name: str, stage: ParseStage) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ParseError(
            f"Field '{field_name}' must be a finite number in [0, 1]", stage=stage
        )
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise ParseError(
            f"Field '{field_name}' must be a finite number in [0, 1]", stage=stage
        )
    return number


def _reduce_category(
    tokens: Sequence[ReflectionToken],
    category: Mapping[ReflectionToken, Any],
    label: str,
    stage: ParseStage,
) -> Any:
    seen = [category[token] for token in tokens if token in category]
    if not seen:
        return None
    unique = {value for value in seen}
    if len(unique) > 1:
        raise ParseError(f"Conflicting {label} tokens in response", stage=stage)
    return seen[0]


__all__ = [
    "ParseError",
    "ParseStage",
    "ParsedReflection",
    "RawModelResponse",
    "REQUIREABLE_FIELDS",
    "SelfRAGResponseParser",
]
