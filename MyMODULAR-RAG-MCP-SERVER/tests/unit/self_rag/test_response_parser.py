"""J2 tests for the Self-RAG response parser."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from src.core.self_rag.response_parser import (
    ParseError,
    ParseStage,
    ParsedReflection,
    RawModelResponse,
    SelfRAGResponseParser,
)
from src.core.self_rag_types import (
    RelevanceLabel,
    RetrieveDecision,
    SupportLabel,
)


FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "self_rag" / "raw_responses"


def load_fixture(name: str) -> dict:
    with (FIXTURE_DIR / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def raw_from_fixture(name: str) -> RawModelResponse:
    return RawModelResponse(**load_fixture(name))


@pytest.fixture
def parser() -> SelfRAGResponseParser:
    return SelfRAGResponseParser()


# --- strategy 1: native structured JSON ---------------------------------


def test_parses_valid_structured_json(parser: SelfRAGResponseParser) -> None:
    result = parser.parse(raw_from_fixture("structured_valid.json"))

    assert result.source is ParseStage.STRUCTURED_JSON
    assert result.retrieve_decision is RetrieveDecision.RETRIEVE
    assert result.relevance is RelevanceLabel.RELEVANT
    assert result.support is SupportLabel.FULLY_SUPPORTED
    assert result.utility == 5
    assert result.evidence_ids == ["chunk_001", "chunk_002"]
    assert result.answer == "向量检索使用 HNSW 索引。"
    assert result.scores is not None
    assert result.scores.retrieval_probability == pytest.approx(0.93)


def test_confidence_derived_from_logprobs(parser: SelfRAGResponseParser) -> None:
    result = parser.parse(raw_from_fixture("structured_valid.json"))

    assert result.confidence == pytest.approx(math.exp(-0.07257069283))


def test_explicit_confidence_overrides_logprobs(parser: SelfRAGResponseParser) -> None:
    raw = RawModelResponse(
        text=json.dumps(
            {"answer": "a", "retrieve_decision": "retrieve", "confidence": 0.5}
        ),
        logprobs={"<RET_YES>": -0.01},
    )

    assert parser.parse(raw).confidence == 0.5


def test_out_of_range_confidence_is_rejected(parser: SelfRAGResponseParser) -> None:
    raw = json.dumps({"answer": "a", "retrieve_decision": "retrieve", "confidence": 1.4})

    with pytest.raises(ParseError, match="confidence"):
        parser.parse(raw)


def test_invalid_scores_are_rejected(parser: SelfRAGResponseParser) -> None:
    raw = json.dumps(
        {
            "answer": "a",
            "retrieve_decision": "retrieve",
            "scores": {"retrieval_probability": 1.9},
        }
    )

    with pytest.raises(ParseError, match="scores"):
        parser.parse(raw)


# --- missing fields and invalid enums -----------------------------------


def test_missing_required_field_raises(parser: SelfRAGResponseParser) -> None:
    raw = raw_from_fixture("missing_field.json")

    with pytest.raises(ParseError, match="Missing required field: answer"):
        parser.parse(raw, required_fields=("answer",))


def test_missing_optional_field_is_tolerated(parser: SelfRAGResponseParser) -> None:
    result = parser.parse(raw_from_fixture("missing_field.json"))

    assert result.answer == ""
    assert result.retrieve_decision is RetrieveDecision.RETRIEVE


def test_invalid_enum_raises(parser: SelfRAGResponseParser) -> None:
    with pytest.raises(ParseError, match="retrieve_decision"):
        parser.parse(raw_from_fixture("invalid_enum.json"))


def test_invalid_utility_raises(parser: SelfRAGResponseParser) -> None:
    with pytest.raises(ParseError, match="utility"):
        parser.parse(json.dumps({"answer": "a", "utility": 9}))


def test_duplicate_evidence_ids_rejected(parser: SelfRAGResponseParser) -> None:
    raw = json.dumps({"answer": "a", "evidence_ids": ["chunk_1", "chunk_1"]})

    with pytest.raises(ParseError, match="duplicates"):
        parser.parse(raw)


def test_unknown_required_field_name_is_a_programming_error(
    parser: SelfRAGResponseParser,
) -> None:
    with pytest.raises(ValueError, match="Unknown required fields"):
        parser.parse("{}", required_fields=("not_a_field",))


# --- strategy 2: control token state machine ----------------------------


def test_streamed_control_tokens_split_across_chunks(
    parser: SelfRAGResponseParser,
) -> None:
    fixture = load_fixture("control_tokens_streamed.json")

    result = parser.parse_stream(fixture["chunks"], logprobs=fixture["logprobs"])

    assert result.source is ParseStage.CONTROL_TOKENS
    assert result.retrieve_decision is RetrieveDecision.RETRIEVE
    assert result.relevance is RelevanceLabel.RELEVANT
    assert result.support is SupportLabel.FULLY_SUPPORTED
    assert result.utility == 4
    assert result.answer == fixture["expected_answer"]
    assert result.confidence == pytest.approx(math.exp(fixture["logprobs"]["<RET_YES>"]))


def test_repeated_identical_token_is_tolerated(parser: SelfRAGResponseParser) -> None:
    result = parser.parse("<RET_YES>answer text<RET_YES>")

    assert result.retrieve_decision is RetrieveDecision.RETRIEVE
    assert result.answer == "answer text"


def test_conflicting_tokens_raise(parser: SelfRAGResponseParser) -> None:
    with pytest.raises(ParseError, match="Conflicting retrieval decision"):
        parser.parse(raw_from_fixture("conflicting_tokens.json"))


def test_conflicting_support_tokens_raise(parser: SelfRAGResponseParser) -> None:
    with pytest.raises(ParseError, match="Conflicting support"):
        parser.parse("<SUP_FULL>text<SUP_NONE>")


def test_control_tokens_are_not_part_of_the_vocabulary(
    parser: SelfRAGResponseParser,
) -> None:
    """Retry/abstain are SelfRAGPolicy decisions, never model-emitted tokens."""

    assert not hasattr(ParsedReflection("a", ParseStage.CONTROL_TOKENS), "control_action")
    # Unregistered, so they are ordinary text and cannot drive control flow.
    with pytest.raises(ParseError, match="no structured JSON object"):
        parser.parse("<ABSTAIN>")
    assert parser.parse("<RET_YES><RETRY>text").answer == "<RETRY>text"


def test_token_order_does_not_change_result(parser: SelfRAGResponseParser) -> None:
    forward = parser.parse("<RET_YES><SUP_FULL>text")
    reversed_order = parser.parse("text<SUP_FULL><RET_YES>")

    assert forward.retrieve_decision is reversed_order.retrieve_decision
    assert forward.support is reversed_order.support


def test_unregistered_angle_bracket_text_is_kept(parser: SelfRAGResponseParser) -> None:
    result = parser.parse("<RET_YES>use the <html> tag")

    assert result.answer == "use the <html> tag"


def test_no_logprobs_yields_null_confidence(parser: SelfRAGResponseParser) -> None:
    result = parser.parse("<RET_YES>no probabilities available")

    assert result.confidence is None


def test_logprobs_without_matching_token_yield_null_confidence(
    parser: SelfRAGResponseParser,
) -> None:
    result = parser.parse(
        RawModelResponse(text="<RET_YES>hello", logprobs={"<UTIL_5>": -0.2})
    )

    assert result.confidence is None


# --- strategy 3: constrained JSON extraction ----------------------------


def test_mixed_text_with_fenced_json(parser: SelfRAGResponseParser) -> None:
    result = parser.parse(raw_from_fixture("mixed_text_fenced_json.json"))

    assert result.source is ParseStage.EXTRACTED_JSON
    assert result.support is SupportLabel.PARTIALLY_SUPPORTED
    assert result.utility == 3
    assert result.evidence_ids == ["chunk_042"]
    assert result.answer == "BM25 负责稀疏检索。"
    assert result.confidence is None


def test_single_unfenced_object_in_prose_is_extracted(
    parser: SelfRAGResponseParser,
) -> None:
    result = parser.parse('Here you go: {"answer": "ok", "utility": 2} — done.')

    assert result.source is ParseStage.EXTRACTED_JSON
    assert result.utility == 2


def test_multiple_objects_are_not_greedily_merged(
    parser: SelfRAGResponseParser,
) -> None:
    with pytest.raises(ParseError):
        parser.parse('{"answer": "one"} and then {"answer": "two"}')


def test_response_without_json_or_tokens_raises(parser: SelfRAGResponseParser) -> None:
    with pytest.raises(ParseError, match="no structured JSON object"):
        parser.parse("I am not going to answer in the requested format.")


def test_empty_response_raises(parser: SelfRAGResponseParser) -> None:
    with pytest.raises(ParseError, match="empty"):
        parser.parse("   ")


# --- strategy 4: single format repair -----------------------------------


def test_repair_recovers_a_broken_response() -> None:
    calls: list[tuple[str, str]] = []

    def repair(reason: str, original: str) -> str:
        calls.append((reason, original))
        return json.dumps({"answer": "repaired", "retrieve_decision": "no_retrieve"})

    parser = SelfRAGResponseParser(repair_fn=repair)
    result = parser.parse("this response has no usable structure")

    assert len(calls) == 1
    assert result.source is ParseStage.REPAIRED_JSON
    assert result.answer == "repaired"
    assert result.retrieve_decision is RetrieveDecision.NO_RETRIEVE


def test_repair_is_attempted_at_most_once() -> None:
    calls: list[str] = []

    def repair(reason: str, original: str) -> str:
        calls.append(reason)
        return "still unusable"

    parser = SelfRAGResponseParser(repair_fn=repair)
    with pytest.raises(ParseError):
        parser.parse("unusable response")

    assert len(calls) == 1


def test_repair_provider_failure_becomes_parse_error() -> None:
    def repair(reason: str, original: str) -> str:
        raise RuntimeError("provider unavailable")

    parser = SelfRAGResponseParser(repair_fn=repair)
    with pytest.raises(ParseError, match="Format repair failed"):
        parser.parse("unusable response")


def test_repair_receives_the_original_text() -> None:
    seen: list[str] = []

    def repair(reason: str, original: str) -> str:
        seen.append(original)
        return json.dumps({"answer": "ok"})

    parser = SelfRAGResponseParser(repair_fn=repair)
    parser.parse(RawModelResponse(text="broken payload", reasoning_text="secret"))

    assert seen == ["broken payload"]


# --- leakage and normalization guarantees -------------------------------


def test_reasoning_and_provider_metadata_never_leak(
    parser: SelfRAGResponseParser,
) -> None:
    raw = raw_from_fixture("structured_valid.json")

    serialized = json.dumps(parser.parse(raw).to_dict(), ensure_ascii=False)

    assert "INTERNAL-REASONING-PLACEHOLDER" not in serialized
    assert "PLACEHOLDER-NOT-A-REAL-KEY" not in serialized
    assert "req_placeholder_0001" not in serialized


def test_parse_error_message_excludes_hidden_reasoning() -> None:
    parser = SelfRAGResponseParser()
    raw = RawModelResponse(
        text="unusable response",
        reasoning_text="INTERNAL-REASONING-PLACEHOLDER",
        provider_metadata={"api_key": "PLACEHOLDER-NOT-A-REAL-KEY"},
    )

    with pytest.raises(ParseError) as excinfo:
        parser.parse(raw)

    assert "INTERNAL-REASONING-PLACEHOLDER" not in str(excinfo.value)
    assert "PLACEHOLDER-NOT-A-REAL-KEY" not in str(excinfo.value)


def test_answer_never_contains_control_tokens(parser: SelfRAGResponseParser) -> None:
    result = parser.parse("<RET_YES>visible answer<REL_YES><SUP_FULL><UTIL_5>")

    for token_text in ("<RET_YES>", "<REL_YES>", "<SUP_FULL>", "<UTIL_5>"):
        assert token_text not in result.answer
    assert result.answer == "visible answer"


def test_control_tokens_inside_json_answer_are_stripped(
    parser: SelfRAGResponseParser,
) -> None:
    raw = json.dumps({"answer": "<RET_YES>text from a leaky provider"})

    assert parser.parse(raw).answer == "text from a leaky provider"


def test_custom_token_map_is_honored() -> None:
    custom = {
        "retrieve": "[R+]",
        "no_retrieve": "[R-]",
        "relevant": "[REL+]",
        "irrelevant": "[REL-]",
        "fully_supported": "[SUP+]",
        "partially_supported": "[SUP~]",
        "not_supported": "[SUP-]",
        "utility_1": "[U1]",
        "utility_2": "[U2]",
        "utility_3": "[U3]",
        "utility_4": "[U4]",
        "utility_5": "[U5]",
    }
    parser = SelfRAGResponseParser(token_map=custom)

    result = parser.parse("[R+]custom mapping answer[U5]")

    assert result.retrieve_decision is RetrieveDecision.RETRIEVE
    assert result.utility == 5
    assert result.answer == "custom mapping answer"


def test_stream_rejects_non_string_chunks(parser: SelfRAGResponseParser) -> None:
    with pytest.raises(ParseError, match="index 1"):
        parser.parse_stream(["<RET_YES>", 42])


def test_invalid_raw_response_type_raises(parser: SelfRAGResponseParser) -> None:
    with pytest.raises(ParseError, match="must be a string, mapping"):
        parser.parse(42)


def test_parsed_reflection_to_dict_is_json_serializable(
    parser: SelfRAGResponseParser,
) -> None:
    result = parser.parse(raw_from_fixture("structured_valid.json"))

    payload = json.loads(json.dumps(result.to_dict(), ensure_ascii=False))

    assert payload["retrieve_decision"] == "retrieve"
    assert payload["support"] == "fully_supported"
    assert payload["source"] == "structured_json"
    assert isinstance(result, ParsedReflection)
