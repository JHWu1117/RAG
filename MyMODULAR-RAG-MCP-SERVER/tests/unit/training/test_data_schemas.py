"""K1 tests for training-sample schemas, provenance, and manifest."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from src.core.self_rag_types import RelevanceLabel, RetrieveDecision, SupportLabel
from src.training.data.manifest import (
    CostReport,
    DatasetManifest,
    SourceDocument,
    summarize,
)
from src.training.data.schemas import (
    ReviewStatus,
    SchemaValidationError,
    Split,
    TaskType,
    TrainingSample,
    read_jsonl,
    write_jsonl,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def make_sample(**overrides) -> TrainingSample:
    """A valid grounded-generation sample; overrides target one field at a time."""

    payload = {
        "dataset_version": "selfrag-v0.1.0",
        "task_type": "grounded_generation",
        "instruction": "腾讯2024年的研发开支是多少？",
        "source_group_id": "doc_sha256:tencent_ar2024",
        "retrieval_snapshot": {
            "index_version": "chroma:selfrag_tencent@v1",
            "query": "2024 研发开支",
            "candidates": [
                {
                    "chunk_id": "chunk_001",
                    "text": "二零二四年，本集团的研发开支为人民币706亿元。",
                    "source": "tencent_ar2024_cn.pdf",
                    "dense_score": 0.82,
                    "sparse_score": 7.1,
                    "rerank_score": 0.91,
                },
                {
                    "chunk_id": "chunk_002",
                    "text": "本公司注册办事处位于开曼群岛。",
                    "source": "tencent_ar2024_cn.pdf",
                    "dense_score": 0.31,
                    "sparse_score": 1.2,
                    "rerank_score": 0.05,
                },
            ],
        },
        "labels": {
            "retrieve": "retrieve",
            "evidence": [
                {"chunk_id": "chunk_001", "relevance": "relevant"},
                {"chunk_id": "chunk_002", "relevance": "irrelevant"},
            ],
            "segments": [
                {
                    "text": "腾讯2024年研发开支为人民币706亿元。",
                    "evidence_ids": ["chunk_001"],
                    "support": "fully_supported",
                    "utility": 5,
                }
            ],
            "final_answer": "腾讯2024年研发开支为人民币706亿元。",
        },
        "teacher": {
            "provider": "openai_compatible",
            "model": "qwen3.5-omni-plus",
            "prompt_version": "grounded-generation-v1",
            "request_id": "req_test_0001",
            "temperature": 0.0,
            "label_confidence": 0.94,
            "raw_response_hash": "sha256:" + "a" * 64,
        },
        "split": "train",
    }
    payload.update(overrides)
    return TrainingSample.from_dict(payload)


# --- happy path ---------------------------------------------------------


def test_valid_sample_round_trips_through_json() -> None:
    sample = make_sample()
    restored = TrainingSample.from_json(sample.to_json())

    assert restored.to_dict() == sample.to_dict()
    assert restored.labels.retrieve is RetrieveDecision.RETRIEVE
    assert restored.labels.evidence[1].relevance is RelevanceLabel.IRRELEVANT
    assert restored.labels.segments[0].support is SupportLabel.FULLY_SUPPORTED
    assert restored.is_accepted


def test_sample_id_is_content_addressed_and_stable() -> None:
    first = make_sample()
    second = make_sample()

    assert first.sample_id == second.sample_id
    assert first.sample_id.startswith("sha256:")

    different = make_sample(instruction="腾讯2023年的研发开支是多少？")
    assert different.sample_id != first.sample_id


def test_mismatched_sample_id_is_rejected() -> None:
    data = make_sample().to_dict()
    data["sample_id"] = "sha256:" + "b" * 64

    with pytest.raises(SchemaValidationError, match="does not match its content"):
        TrainingSample.from_dict(data)


# --- acceptance criterion: wrong evidence ids ---------------------------


def test_evidence_id_outside_snapshot_is_rejected() -> None:
    labels = make_sample().labels.to_dict()
    labels["evidence"].append({"chunk_id": "chunk_999", "relevance": "relevant"})

    with pytest.raises(SchemaValidationError, match="not in the retrieval snapshot"):
        make_sample(labels=labels)


def test_segment_citing_unknown_chunk_is_rejected() -> None:
    labels = make_sample().labels.to_dict()
    labels["segments"][0]["evidence_ids"] = ["chunk_404"]

    with pytest.raises(SchemaValidationError, match="cites unknown chunk_id"):
        make_sample(labels=labels)


def test_duplicate_chunk_ids_in_snapshot_are_rejected() -> None:
    snapshot = make_sample().retrieval_snapshot.to_dict()
    snapshot["candidates"][1]["chunk_id"] = "chunk_001"

    with pytest.raises(SchemaValidationError, match="duplicate chunk_id"):
        make_sample(retrieval_snapshot=snapshot)


# --- acceptance criterion: unknown labels -------------------------------


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("retrieve", "maybe", "Unknown retrieve"),
        ("evidence", [{"chunk_id": "chunk_001", "relevance": "sort_of"}], "Unknown relevance"),
    ],
)
def test_unknown_label_values_are_rejected(field, value, match) -> None:
    labels = make_sample().labels.to_dict()
    labels[field] = value

    with pytest.raises(SchemaValidationError, match=match):
        make_sample(labels=labels)


def test_unknown_support_and_utility_are_rejected() -> None:
    labels = make_sample().labels.to_dict()
    labels["segments"][0]["support"] = "mostly_supported"
    with pytest.raises(SchemaValidationError, match="Unknown support"):
        make_sample(labels=labels)

    labels = make_sample().labels.to_dict()
    labels["segments"][0]["utility"] = 9
    with pytest.raises(SchemaValidationError, match="Unknown utility|utility must be"):
        make_sample(labels=labels)


def test_unknown_task_type_and_unknown_field_are_rejected() -> None:
    with pytest.raises(SchemaValidationError, match="Unknown task_type"):
        make_sample(task_type="summarisation")

    data = make_sample().to_dict()
    data["extra_field"] = 1
    with pytest.raises(SchemaValidationError, match="unknown fields"):
        TrainingSample.from_dict(data)


# --- acceptance criterion: missing provenance ---------------------------


@pytest.mark.parametrize(
    "missing", ["provider", "model", "prompt_version", "request_id", "raw_response_hash"]
)
def test_missing_teacher_provenance_is_rejected(missing: str) -> None:
    teacher = make_sample().teacher.to_dict()
    teacher[missing] = ""

    with pytest.raises(SchemaValidationError, match="non-empty|raw_response_hash"):
        make_sample(teacher=teacher)


def test_absent_teacher_block_is_rejected() -> None:
    data = make_sample().to_dict()
    data.pop("teacher")

    with pytest.raises(SchemaValidationError, match="missing or unexpected fields"):
        TrainingSample.from_dict(data)


def test_malformed_response_hash_is_rejected() -> None:
    teacher = make_sample().teacher.to_dict()
    teacher["raw_response_hash"] = "not-a-hash"

    with pytest.raises(SchemaValidationError, match="sha256"):
        make_sample(teacher=teacher)


def test_label_confidence_must_be_a_probability() -> None:
    teacher = make_sample().teacher.to_dict()
    teacher["label_confidence"] = 1.7

    with pytest.raises(SchemaValidationError, match="label_confidence"):
        make_sample(teacher=teacher)


# --- task consistency rules ---------------------------------------------


def test_no_retrieve_sample_cannot_depend_on_evidence() -> None:
    labels = make_sample().labels.to_dict()
    labels["retrieve"] = "no_retrieve"

    with pytest.raises(SchemaValidationError, match="must not depend on retrieved evidence"):
        make_sample(labels=labels)


def test_no_retrieve_sample_without_evidence_is_valid() -> None:
    labels = {
        "retrieve": "no_retrieve",
        "evidence": [],
        "segments": [
            {
                "text": "你好，我可以帮你查询年报内容。",
                "evidence_ids": [],
                "support": "not_supported",
                "utility": 4,
            }
        ],
        "final_answer": "你好，我可以帮你查询年报内容。",
    }
    sample = make_sample(task_type="retrieval_decision", labels=labels)

    assert sample.labels.retrieve is RetrieveDecision.NO_RETRIEVE


def test_supported_segment_must_cite_evidence() -> None:
    labels = make_sample().labels.to_dict()
    labels["segments"][0]["evidence_ids"] = []

    with pytest.raises(SchemaValidationError, match="must cite at least one evidence"):
        make_sample(labels=labels)


def test_query_rewrite_requires_a_rewritten_query() -> None:
    with pytest.raises(SchemaValidationError, match="rewritten_query"):
        make_sample(task_type="query_rewrite")


def test_insufficient_evidence_cannot_be_fully_supported() -> None:
    with pytest.raises(SchemaValidationError, match="fully supported"):
        make_sample(task_type="insufficient_evidence")


def test_samples_carry_no_abstain_field() -> None:
    """Abstention is a policy decision, never a training label."""

    payload = json.loads(make_sample().to_json())

    assert "abstain" not in payload["labels"]
    assert not any("abstain" in key for key in payload["labels"])


# --- quality gating ------------------------------------------------------


def test_quarantined_sample_must_record_a_reason() -> None:
    with pytest.raises(SchemaValidationError, match="quarantine_reason"):
        make_sample(quality={"review_status": "quarantined"})


def test_quarantined_sample_is_not_accepted() -> None:
    sample = make_sample(
        quality={"review_status": "quarantined", "quarantine_reason": "low_confidence"}
    )

    assert not sample.is_accepted
    assert sample.quality.review_status is ReviewStatus.QUARANTINED


# --- JSONL round trip ----------------------------------------------------


def test_jsonl_write_and_read_revalidates(tmp_path: Path) -> None:
    samples = [make_sample(), make_sample(instruction="腾讯2023年收入是多少？")]
    path = tmp_path / "critic.jsonl"

    assert write_jsonl(path, samples) == 2
    restored = read_jsonl(path)

    assert [s.sample_id for s in restored] == [s.sample_id for s in samples]


def test_corrupt_jsonl_line_reports_its_line_number(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text(
        make_sample().to_json() + "\n" + json.dumps({"dataset_version": "x"}) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(SchemaValidationError, match="line 2"):
        read_jsonl(path)


# --- manifest -------------------------------------------------------------


def test_manifest_summarizes_distributions() -> None:
    samples = [
        make_sample(),
        # A different source group, because one group may never span two splits.
        make_sample(
            instruction="腾讯2023年收入是多少？",
            source_group_id="doc_sha256:tencent_ar2023",
            split="dev",
        ),
    ]
    manifest = summarize(
        samples,
        dataset_version="selfrag-v0.1.0",
        index_version="chroma:selfrag_tencent@v1",
        source_documents=[
            SourceDocument(
                source_group_id="doc_sha256:tencent_ar2024",
                filename="tencent_ar2024_cn.pdf",
                content_sha256="sha256:" + "c" * 64,
                pages=274,
            )
        ],
        split_ratios={"train": 0.8, "dev": 0.1, "test": 0.1},
        cost=CostReport(teacher_requests=2, prompt_tokens=1200, completion_tokens=200),
    )

    assert manifest.counts["total"] == 2
    assert manifest.task_distribution["grounded_generation"] == 2
    assert manifest.label_distribution["relevance"] == {"irrelevant": 2, "relevant": 2}
    assert manifest.label_distribution["support"]["fully_supported"] == 2
    assert manifest.teacher_models == ["openai_compatible:qwen3.5-omni-plus"]
    assert manifest.cost.teacher_requests == 2


def test_manifest_detects_source_group_leakage() -> None:
    manifest = DatasetManifest(
        dataset_version="v1",
        index_version="v1",
        split_group_hashes={"train": ["sha256:aa"], "test": ["sha256:aa"]},
    )

    with pytest.raises(SchemaValidationError, match="leaked across"):
        manifest.assert_no_group_leakage()


def test_manifest_rejects_split_ratios_that_do_not_sum_to_one() -> None:
    with pytest.raises(SchemaValidationError, match="must sum to 1"):
        DatasetManifest(
            dataset_version="v1",
            index_version="v1",
            split_ratios={"train": 0.8, "dev": 0.1, "test": 0.3},
        )


def test_manifest_save_and_load(tmp_path: Path) -> None:
    manifest = summarize(
        [make_sample()],
        dataset_version="selfrag-v0.1.0",
        index_version="chroma:selfrag_tencent@v1",
    )
    path = manifest.save(tmp_path / "manifest.json")

    assert DatasetManifest.load(path).to_dict() == manifest.to_dict()


# --- config wiring --------------------------------------------------------


def test_dataset_yaml_matches_the_schema_vocabulary() -> None:
    config = yaml.safe_load((REPO_ROOT / "config" / "dataset.yaml").read_text(encoding="utf-8"))

    known_tasks = {member.value for member in TaskType}
    assert set(config["target"]["task_ratios"]) <= known_tasks
    assert abs(sum(config["target"]["task_ratios"].values()) - 1.0) < 1e-9
    assert abs(sum(config["split"]["ratios"].values()) - 1.0) < 1e-9
    assert set(config["split"]["ratios"]) == {member.value for member in Split}
    # No abstain quota: abstention is a policy decision.
    assert not any("abstain" in task for task in config["target"]["task_ratios"])


def test_dataset_yaml_contains_no_inline_credentials() -> None:
    raw = (REPO_ROOT / "config" / "dataset.yaml").read_text(encoding="utf-8")

    assert "sk-" not in raw
    assert "api_key:" not in raw
    assert "api_key_env" in raw
