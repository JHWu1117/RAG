"""J1 tests for Reflection Token and core Self-RAG data contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from src.core.response.citation_generator import Citation
from src.core.self_rag_types import (
    DEFAULT_REFLECTION_TOKEN_MAP,
    EvidenceAssessment,
    GeneratedSegment,
    ReflectionScores,
    ReflectionToken,
    RelevanceLabel,
    RetrieveDecision,
    SelfRAGResult,
    SupportLabel,
    UtilityLabel,
    validate_reflection_token_mapping,
)
from src.core.types import Chunk, Document, RetrievalResult


EXPECTED_TOKEN_TEXT = {
    "retrieve": "<RET_YES>",
    "no_retrieve": "<RET_NO>",
    "relevant": "<REL_YES>",
    "irrelevant": "<REL_NO>",
    "fully_supported": "<SUP_FULL>",
    "partially_supported": "<SUP_PARTIAL>",
    "not_supported": "<SUP_NONE>",
    "utility_1": "<UTIL_1>",
    "utility_2": "<UTIL_2>",
    "utility_3": "<UTIL_3>",
    "utility_4": "<UTIL_4>",
    "utility_5": "<UTIL_5>",
}


def _scores() -> ReflectionScores:
    return ReflectionScores(
        retrieval_probability=0.9,
        relevance_probability=0.8,
        support_probability=0.7,
        utility_distribution=[0.0, 0.0, 0.1, 0.2, 0.7],
    )


def _result() -> SelfRAGResult:
    return SelfRAGResult(
        answer="The answer is supported. [1]",
        citations=[
            Citation(
                index=1,
                chunk_id="chunk-1",
                source="docs/source.pdf",
                score=0.95,
                text_snippet="Supporting evidence.",
                page=3,
            )
        ],
        retrieve_decision=RetrieveDecision.RETRIEVE,
        segments=[
            GeneratedSegment(
                text="The answer is supported. [1]",
                evidence_ids=["chunk-1"],
                support=SupportLabel.FULLY_SUPPORTED,
                utility=5,
                scores=_scores(),
            )
        ],
        retrieval_rounds=1,
        termination_reason="accepted",
    )


def test_default_reflection_token_values_match_dev_spec_and_config() -> None:
    default_mapping = {
        semantic.value: token_text
        for semantic, token_text in DEFAULT_REFLECTION_TOKEN_MAP.items()
    }
    config_path = Path(__file__).parents[3] / "config" / "self_rag.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    assert default_mapping == EXPECTED_TOKEN_TEXT
    assert config == {
        "schema_version": 1,
        "reflection_tokens": EXPECTED_TOKEN_TEXT,
    }
    assert validate_reflection_token_mapping(config["reflection_tokens"]) == dict(
        DEFAULT_REFLECTION_TOKEN_MAP
    )
    assert len(set(default_mapping.values())) == len(ReflectionToken) == 12


@pytest.mark.parametrize("semantic,token_text", list(DEFAULT_REFLECTION_TOKEN_MAP.items()))
def test_reflection_token_text_round_trip(
    semantic: ReflectionToken,
    token_text: str,
) -> None:
    assert semantic.to_token_text() == token_text
    assert ReflectionToken.from_token_text(token_text) is semantic


def test_semantic_enums_convert_from_serialized_values() -> None:
    assert RetrieveDecision("retrieve") is RetrieveDecision.RETRIEVE
    assert RelevanceLabel("irrelevant") is RelevanceLabel.IRRELEVANT
    assert SupportLabel("partially_supported") is SupportLabel.PARTIALLY_SUPPORTED
    assert UtilityLabel(5) is UtilityLabel.UTILITY_5
    assert ReflectionToken(json.loads(json.dumps(ReflectionToken.RETRIEVE))) is (
        ReflectionToken.RETRIEVE
    )


def test_semantic_enum_is_decoupled_from_configurable_token_text() -> None:
    custom_mapping = dict(DEFAULT_REFLECTION_TOKEN_MAP)
    custom_mapping[ReflectionToken.RETRIEVE] = "<CUSTOM_RETRIEVE>"

    assert ReflectionToken.RETRIEVE.value == "retrieve"
    assert ReflectionToken.RETRIEVE.to_token_text(custom_mapping) == "<CUSTOM_RETRIEVE>"
    assert ReflectionToken.from_token_text("<CUSTOM_RETRIEVE>", custom_mapping) is (
        ReflectionToken.RETRIEVE
    )


def test_invalid_token_text_and_mapping_are_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown Reflection Token"):
        ReflectionToken.from_token_text("<RET_MAYBE>")

    missing = dict(DEFAULT_REFLECTION_TOKEN_MAP)
    missing.pop(ReflectionToken.UTILITY_5)
    with pytest.raises(ValueError, match="must be complete"):
        validate_reflection_token_mapping(missing)

    duplicate = dict(DEFAULT_REFLECTION_TOKEN_MAP)
    duplicate[ReflectionToken.UTILITY_5] = duplicate[ReflectionToken.UTILITY_4]
    with pytest.raises(ValueError, match="must be unique"):
        validate_reflection_token_mapping(duplicate)


@pytest.mark.parametrize("invalid", [-0.01, 1.01, float("nan"), float("inf"), True, "0.5"])
def test_invalid_probabilities_are_rejected(invalid: object) -> None:
    with pytest.raises(ValueError, match="retrieval_probability"):
        ReflectionScores(retrieval_probability=invalid)  # type: ignore[arg-type]


def test_invalid_utility_distribution_and_level_are_rejected() -> None:
    with pytest.raises(ValueError, match="contain 5"):
        ReflectionScores(0.5, utility_distribution=[0.5, 0.5])
    with pytest.raises(ValueError, match="sum to 1"):
        ReflectionScores(0.5, utility_distribution=[0.1] * 5)
    with pytest.raises(ValueError, match="integer from 1 to 5"):
        GeneratedSegment(
            text="segment",
            evidence_ids=[],
            support=SupportLabel.NOT_SUPPORTED,
            utility=0,
            scores=ReflectionScores(0.5),
        )


def test_no_implicit_supported_default_exists() -> None:
    with pytest.raises(TypeError):
        GeneratedSegment(  # type: ignore[call-arg]
            text="segment",
            evidence_ids=[],
            utility=3,
            scores=ReflectionScores(0.5),
        )


def test_structured_objects_serialize_and_deserialize_as_json() -> None:
    assessment = EvidenceAssessment.from_json(
        '{"chunk_id":"chunk-1","relevance":"relevant",'
        '"confidence":0.8,"concise_reason":"direct match"}'
    )
    assert assessment.relevance is RelevanceLabel.RELEVANT
    assert json.loads(assessment.to_json())["relevance"] == "relevant"

    original = _result()
    payload = original.to_json()
    restored = SelfRAGResult.from_json(payload)

    assert restored == original
    serialized = json.loads(payload)
    assert serialized["retrieve_decision"] == "retrieve"
    assert serialized["segments"][0]["support"] == "fully_supported"
    assert serialized["segments"][0]["utility"] == 5
    assert serialized["citations"][0]["page"] == 3


def test_invalid_serialized_enums_are_rejected() -> None:
    data = _result().to_dict()
    data["retrieve_decision"] = "maybe"
    with pytest.raises(ValueError, match="retrieve_decision"):
        SelfRAGResult.from_dict(data)

    segment = _result().segments[0].to_dict()
    segment["support"] = "assumed_supported"
    with pytest.raises(ValueError, match="support"):
        GeneratedSegment.from_dict(segment)


def test_traditional_rag_types_remain_compatible() -> None:
    document_data = {
        "id": "doc-1",
        "text": "traditional document",
        "metadata": {"source_path": "docs/source.pdf"},
    }
    chunk_data = {
        "id": "chunk-1",
        "text": "traditional chunk",
        "metadata": {"source_path": "docs/source.pdf"},
    }
    result_data = {
        "chunk_id": "chunk-1",
        "score": 0.75,
        "text": "traditional result",
        "metadata": {"source_path": "docs/source.pdf"},
    }

    assert Document.from_dict(document_data).to_dict() == document_data
    assert Chunk.from_dict(chunk_data).to_dict() == {
        **chunk_data,
        "start_offset": None,
        "end_offset": None,
        "source_ref": None,
    }
    assert RetrievalResult.from_dict(result_data).to_dict() == result_data
