"""K6 tests for independent prompts and unified Critic sample labeling."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from src.training.data.schemas import RetrievalCandidate, RetrievalSnapshot, TrainingSample
from src.training.data.synthetic_query_generator import QueryKind, SyntheticQuery
from src.training.teacher.base_teacher import BaseTeacherLLM, TeacherResult, TeacherUsage
from src.training.teacher.fake_teacher import FakeTeacherLLM
from src.training.teacher.labeler import PROMPT_VERSION, ReflectionLabeler

REPO_ROOT = Path(__file__).resolve().parents[3]


def make_query() -> SyntheticQuery:
    return SyntheticQuery(
        instruction="腾讯2024年的研发开支是多少？",
        source_group_id="doc_sha256:tencent-2024",
        source_seed_id="sha256:" + "a" * 64,
        query_kind=QueryKind.FACTUAL,
        task_type=QueryKind.FACTUAL.task_type,
        language="zh",
        requires_retrieval=True,
        prompt_version="query-generation-v1",
    )


def make_snapshot() -> RetrievalSnapshot:
    return RetrievalSnapshot(
        index_version="chroma:selfrag_tencent@v1",
        query=make_query().instruction,
        candidates=[
            RetrievalCandidate(
                chunk_id="chunk_001",
                text="二零二四年，本集团研发开支为人民币706亿元。",
                source="tencent-2024.pdf",
            ),
            RetrievalCandidate(
                chunk_id="chunk_002",
                text="本公司注册办事处位于开曼群岛。",
                source="tencent-2024.pdf",
            ),
        ],
    )


GOOD_RESPONSES = [
    {"retrieve": "retrieve", "confidence": 0.99, "concise_reason": "需查年报数据"},
    {
        "evidence": [
            {"chunk_id": "chunk_001", "relevance": "relevant", "concise_reason": "含研发金额"},
            {"chunk_id": "chunk_002", "relevance": "irrelevant", "concise_reason": "仅含注册地址"},
        ],
        "confidence": 0.98,
    },
    {
        "final_answer": "腾讯2024年研发开支为人民币706亿元。",
        "segments": [
            {
                "text": "腾讯2024年研发开支为人民币706亿元。",
                "evidence_ids": ["chunk_001"],
            }
        ],
        "confidence": 0.97,
    },
    {
        "segments": [
            {
                "segment_index": 0,
                "support": "fully_supported",
                "concise_reason": "金额与证据一致",
            }
        ],
        "confidence": 0.96,
    },
    {
        "segments": [
            {"segment_index": 0, "utility": 5, "concise_reason": "直接完整回答问题"}
        ],
        "confidence": 0.95,
    },
]


class SequenceTeacher(BaseTeacherLLM):
    provider_name = "fake-sequence"
    model = "fake-sequence-v1"

    def __init__(self, responses: list[Mapping[str, Any]]) -> None:
        self.responses = list(responses)
        self.prompts: list[str] = []

    def generate_structured(
        self, prompt, schema, *, system_prompt=None, schema_name="teacher_output"
    ):
        del schema, system_prompt, schema_name
        self.prompts.append(prompt)
        data = self.responses.pop(0)
        raw = json.dumps(data, ensure_ascii=False, sort_keys=True)
        import hashlib

        return TeacherResult(
            data=data,
            provider=self.provider_name,
            model=self.model,
            usage=TeacherUsage(10, 5, 15),
            raw_response_hash="sha256:" + hashlib.sha256(raw.encode()).hexdigest(),
            cost_usd=0.0,
        )

    def probe_model(self) -> None:
        return None


def test_labeler_builds_round_trippable_unified_critic_sample() -> None:
    teacher = SequenceTeacher(GOOD_RESPONSES)
    labeler = ReflectionLabeler(teacher, dataset_version="selfrag-v0.1.0")

    outcome = labeler.label(make_query(), make_snapshot())

    assert outcome.quarantine is None
    assert outcome.sample is not None
    sample = outcome.sample
    assert len(teacher.prompts) == 5
    assert sample.labels.retrieve.value == "retrieve"
    assert [item.relevance.value for item in sample.labels.evidence] == [
        "relevant",
        "irrelevant",
    ]
    assert sample.labels.segments[0].support.value == "fully_supported"
    assert sample.labels.segments[0].utility == 5
    assert sample.labels.segments[0].support_reason == "金额与证据一致"
    assert sample.teacher.prompt_version == PROMPT_VERSION
    assert sample.teacher.prompt_hash == labeler.prompt_hash
    assert sample.teacher.label_confidence == 0.95
    assert TrainingSample.from_json(sample.to_json()).to_dict() == sample.to_dict()


def test_each_judgment_uses_a_separate_versioned_prompt() -> None:
    teacher = SequenceTeacher(GOOD_RESPONSES)
    labeler = ReflectionLabeler(teacher, dataset_version="v1")
    labeler.label(make_query(), make_snapshot())

    headings = [prompt.splitlines()[0] for prompt in teacher.prompts]
    assert len(set(headings)) == 5
    assert all("INPUT_JSON" in prompt for prompt in teacher.prompts)
    assert labeler.prompt_hash.startswith("sha256:")


def test_teacher_failure_goes_to_quarantine_without_raw_payload() -> None:
    teacher = FakeTeacherLLM(failure=RuntimeError("offline"))
    labeler = ReflectionLabeler(teacher, dataset_version="v1")

    outcome = labeler.label(make_query(), make_snapshot())

    assert outcome.sample is None
    assert outcome.quarantine is not None
    assert outcome.quarantine.error_type == "TeacherError"
    assert set(outcome.quarantine.to_dict()) == {
        "query_id",
        "source_group_id",
        "reason",
        "error_type",
    }


def test_unknown_enum_is_quarantined_before_sample_acceptance() -> None:
    responses = [dict(item) for item in GOOD_RESPONSES]
    responses[0] = {"retrieve": "retry", "confidence": 0.9, "concise_reason": "bad"}
    labeler = ReflectionLabeler(SequenceTeacher(responses), dataset_version="v1")

    outcome = labeler.label(make_query(), make_snapshot())

    assert outcome.sample is None
    assert outcome.quarantine is not None
    assert "valid RetrieveDecision" in outcome.quarantine.reason


def test_missing_or_duplicate_candidate_labels_are_quarantined() -> None:
    responses = [dict(item) for item in GOOD_RESPONSES]
    responses[1] = {
        "evidence": [
            {"chunk_id": "chunk_001", "relevance": "relevant", "concise_reason": "one"},
            {"chunk_id": "chunk_001", "relevance": "irrelevant", "concise_reason": "two"},
        ],
        "confidence": 0.9,
    }
    outcome = ReflectionLabeler(SequenceTeacher(responses), dataset_version="v1").label(
        make_query(), make_snapshot()
    )

    assert outcome.quarantine is not None
    assert "every candidate exactly once" in outcome.quarantine.reason


def test_unknown_evidence_id_is_quarantined() -> None:
    responses = [dict(item) for item in GOOD_RESPONSES]
    responses[2] = {
        "final_answer": "错误引用",
        "segments": [{"text": "错误引用", "evidence_ids": ["chunk_404"]}],
        "confidence": 0.8,
    }
    outcome = ReflectionLabeler(SequenceTeacher(responses), dataset_version="v1").label(
        make_query(), make_snapshot()
    )

    assert outcome.quarantine is not None
    assert "unknown chunk_id" in outcome.quarantine.reason


def test_prompt_and_serialized_labels_contain_no_retry_or_abstain_tokens() -> None:
    prompt_dir = REPO_ROOT / "config" / "prompts" / "self_rag" / "teacher"
    raw = "\n".join(path.read_text("utf-8") for path in prompt_dir.glob("*_v1.md"))
    outcome = ReflectionLabeler(
        SequenceTeacher(GOOD_RESPONSES), dataset_version="v1"
    ).label(make_query(), make_snapshot())
    serialized = outcome.sample.to_json().lower()

    assert "<retry" not in raw.lower()
    assert "<abstain" not in raw.lower()
    assert '"retry"' not in serialized
    assert '"abstain"' not in serialized
