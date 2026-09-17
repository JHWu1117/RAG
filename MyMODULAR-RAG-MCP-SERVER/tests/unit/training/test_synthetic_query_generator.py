"""K3 tests for quota-driven synthetic query generation."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest
import yaml

from src.training.data.schemas import TaskType
from src.training.data.seed_collector import (
    CanonicalSeed,
    SeedProvenance,
    SeedSource,
)
from src.training.data.synthetic_query_generator import (
    QueryGenerationRequest,
    QueryKind,
    SyntheticQueryGenerator,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
RATIOS = {
    QueryKind.FACTUAL: 0.25,
    QueryKind.MULTI_HOP: 0.15,
    QueryKind.COMPARISON: 0.15,
    QueryKind.SUMMARY: 0.15,
    QueryKind.NO_RETRIEVAL: 0.15,
    QueryKind.UNANSWERABLE: 0.15,
}


def make_seed(index: int) -> CanonicalSeed:
    text = f"腾讯第 {index} 份年度报告：收入和研发开支数据。"
    return CanonicalSeed(
        source=SeedSource.DOCUMENT,
        source_group_id=f"doc_sha256:{index:064x}",
        content=text,
        provenance=SeedProvenance(
            source_uri=f"report-{index}.pdf",
            content_sha256=f"sha256:{index:064x}",
            license_name="public_disclosure",
            authorization_basis="public_company_filing",
        ),
    )


class FakeTeacher:
    def __init__(self) -> None:
        self.requests: list[QueryGenerationRequest] = []

    def generate_query(self, request: QueryGenerationRequest) -> dict:
        self.requests.append(request)
        query = f"{request.language}-{request.query_kind.value}-{request.seed_id[-8:]}-{len(self.requests)}"
        answer = None if request.query_kind is QueryKind.UNANSWERABLE else "示例答案"
        return {"instruction": query, "reference_answer": answer}


def test_plan_uses_largest_remainder_and_exact_total() -> None:
    plan = SyntheticQueryGenerator(FakeTeacher()).plan(
        17, RATIOS, {"zh": 0.7, "en": 0.3}
    )

    assert sum(plan.query_kind_quotas.values()) == 17
    assert sum(plan.language_quotas.values()) == 17
    assert plan.language_quotas == {"zh": 12, "en": 5}


def test_dry_run_computes_plan_without_teacher_calls() -> None:
    teacher = FakeTeacher()
    result = SyntheticQueryGenerator(teacher).generate(
        [],
        total=10,
        query_kind_ratios=RATIOS,
        language_ratios={"zh": 1.0},
        dry_run=True,
    )

    assert result.plan.total == 10
    assert not result.queries
    assert result.teacher_calls == 0
    assert not teacher.requests


def test_generated_queries_have_source_group_task_type_and_language() -> None:
    teacher = FakeTeacher()
    result = SyntheticQueryGenerator(teacher).generate(
        [make_seed(1), make_seed(2)],
        total=20,
        query_kind_ratios=RATIOS,
        language_ratios={"zh": 0.75, "en": 0.25},
    )

    assert len(result.queries) == 20
    assert result.teacher_calls == 20
    assert all(query.query_id.startswith("sha256:") for query in result.queries)
    assert all(query.source_group_id.startswith("doc_sha256:") for query in result.queries)
    assert all(query.source_seed_id.startswith("sha256:") for query in result.queries)
    assert Counter(query.language for query in result.queries) == {"zh": 15, "en": 5}


def test_no_retrieval_and_document_questions_are_unambiguous() -> None:
    result = SyntheticQueryGenerator(FakeTeacher()).generate(
        [make_seed(1)],
        total=20,
        query_kind_ratios=RATIOS,
        language_ratios={"zh": 1.0},
    )

    for query in result.queries:
        if query.query_kind is QueryKind.NO_RETRIEVAL:
            assert query.requires_retrieval is False
            assert query.task_type is TaskType.RETRIEVAL_DECISION
        elif query.query_kind is QueryKind.UNANSWERABLE:
            assert query.requires_retrieval is True
            assert query.task_type is TaskType.INSUFFICIENT_EVIDENCE
            assert query.reference_answer is None
        else:
            assert query.requires_retrieval is True
            assert query.task_type is TaskType.GROUNDED_GENERATION


class DuplicateThenUniqueTeacher:
    def __init__(self) -> None:
        self.calls = 0

    def generate_query(self, request: QueryGenerationRequest) -> dict:
        self.calls += 1
        if self.calls <= 2:
            return {"instruction": "同一个问题？" if self.calls == 1 else "同 一个 问题!"}
        return {"instruction": f"唯一问题 {self.calls}"}


def test_normalized_duplicates_are_retried() -> None:
    ratios = {kind: (1.0 if kind is QueryKind.FACTUAL else 0.0) for kind in QueryKind}
    result = SyntheticQueryGenerator(
        DuplicateThenUniqueTeacher(), max_attempts_per_query=3
    ).generate(
        [make_seed(1), make_seed(2)],
        total=2,
        query_kind_ratios=ratios,
        language_ratios={"zh": 1.0},
    )

    assert len(result.queries) == 2
    assert result.teacher_calls == 3
    assert result.duplicates_rejected == 1


def test_duplicate_exhaustion_is_explicit() -> None:
    class AlwaysSame:
        def generate_query(self, request: QueryGenerationRequest) -> dict:
            return {"instruction": "重复"}

    ratios = {kind: (1.0 if kind is QueryKind.FACTUAL else 0.0) for kind in QueryKind}
    with pytest.raises(RuntimeError, match="could not produce a unique"):
        SyntheticQueryGenerator(AlwaysSame(), max_attempts_per_query=2).generate(
            [make_seed(1)],
            total=2,
            query_kind_ratios=ratios,
            language_ratios={"zh": 1.0},
        )


@pytest.mark.parametrize(
    ("ratios", "match"),
    [
        ({QueryKind.FACTUAL: 1.0}, "must be complete"),
        ({kind: 0.5 for kind in QueryKind}, "sum to 1.0"),
        ({kind: (-0.1 if kind is QueryKind.FACTUAL else 0.22) for kind in QueryKind}, "non-negative"),
    ],
)
def test_invalid_query_kind_ratios_are_rejected(ratios, match) -> None:
    with pytest.raises(ValueError, match=match):
        SyntheticQueryGenerator(FakeTeacher()).plan(10, ratios, {"zh": 1.0})


def test_dataset_config_and_versioned_prompt_cover_all_query_kinds() -> None:
    config = yaml.safe_load((REPO_ROOT / "config" / "dataset.yaml").read_text(encoding="utf-8"))
    configured = config["synthetic_queries"]
    prompt = (
        REPO_ROOT / "config" / "prompts" / "self_rag" / "teacher" / "query_generation_v1.md"
    ).read_text(encoding="utf-8")

    assert set(configured["query_kind_ratios"]) == {kind.value for kind in QueryKind}
    assert sum(configured["query_kind_ratios"].values()) == pytest.approx(1.0)
    assert configured["prompt_version"] == "query-generation-v1"
    assert all(kind.value in prompt for kind in QueryKind)
    assert "JSON" in prompt
