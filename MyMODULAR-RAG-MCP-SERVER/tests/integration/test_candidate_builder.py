"""K4 integration tests for retrieval snapshots and hard negatives."""

from __future__ import annotations

from dataclasses import replace

import pytest

from src.core.query_engine.hybrid_search import HybridSearchResult
from src.core.query_engine.reranker import RerankResult
from src.core.types import RetrievalResult
from src.training.data.candidate_builder import CandidateBuilder, CandidateBuilderConfig
from src.training.data.schemas import CandidateRole, SchemaValidationError, Split, TaskType
from src.training.data.synthetic_query_generator import QueryKind, SyntheticQuery


def result(
    chunk_id: str,
    score: float,
    *,
    group: str = "doc-train",
    collection: str = "selfrag_tencent",
) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=chunk_id,
        score=score,
        text=f"evidence text for {chunk_id}",
        metadata={
            "source_path": f"{group}.pdf",
            "source_group_id": group,
            "collection": collection,
        },
    )


class FixedHybrid:
    def __init__(self, details: HybridSearchResult) -> None:
        self.details = details
        self.calls: list[dict] = []

    def search(self, query: str, **kwargs) -> HybridSearchResult:
        self.calls.append({"query": query, **kwargs})
        return self.details


class FixedReranker:
    def __init__(self, scores: dict[str, float], *, fallback: bool = False) -> None:
        self.scores = scores
        self.fallback = fallback

    def rerank(self, query: str, results: list[RetrievalResult], **kwargs) -> RerankResult:
        reranked = [
            RetrievalResult(
                chunk_id=item.chunk_id,
                score=self.scores.get(item.chunk_id, item.score),
                text=item.text,
                metadata={
                    **item.metadata,
                    "original_score": item.score,
                    "rerank_score": self.scores.get(item.chunk_id, item.score),
                    "reranked": not self.fallback,
                },
            )
            for item in results
        ]
        return RerankResult(
            results=list(reversed(reranked)),
            used_fallback=self.fallback,
            reranker_type="cross_encoder",
            original_order=results,
        )


def query(group: str = "doc-train") -> SyntheticQuery:
    return SyntheticQuery(
        instruction="腾讯研发开支是多少？",
        source_group_id=group,
        source_seed_id="sha256:" + "a" * 64,
        query_kind=QueryKind.FACTUAL,
        task_type=TaskType.GROUNDED_GENERATION,
        language="zh",
        requires_retrieval=True,
        prompt_version="query-generation-v1",
    )


def details(*items: RetrievalResult) -> HybridSearchResult:
    return HybridSearchResult(
        results=list(items),
        dense_results=[replace(item, score=item.score + 0.1) for item in items],
        sparse_results=[replace(item, score=item.score + 1.0) for item in reversed(items)],
    )


def builder(
    *items: RetrievalResult,
    rerank_scores: dict[str, float] | None = None,
    hard_negatives: int = 2,
) -> tuple[CandidateBuilder, FixedHybrid]:
    hybrid = FixedHybrid(details(*items))
    instance = CandidateBuilder(
        hybrid,
        FixedReranker(rerank_scores or {}),
        CandidateBuilderConfig(
            collection="selfrag_tencent",
            index_version="chroma:selfrag_tencent@fixed-v1",
            hard_negatives_per_sample=hard_negatives,
            hard_negative_min_rerank_score=0.3,
        ),
    )
    return instance, hybrid


def test_snapshot_preserves_all_scores_roles_and_chunk_traceability() -> None:
    instance, hybrid = builder(
        result("positive", 0.8),
        result("hard", 0.7),
        result("conflict", 0.6),
        rerank_scores={"positive": 0.95, "hard": 0.85, "conflict": 0.75},
        hard_negatives=1,
    )

    built = instance.build(
        query(),
        split=Split.TRAIN,
        positive_chunk_ids=["positive"],
        conflicting_chunk_ids=["conflict"],
    )

    assert hybrid.calls[0]["filters"] == {"collection": "selfrag_tencent"}
    assert hybrid.calls[0]["return_details"] is True
    candidates = {item.chunk_id: item for item in built.snapshot.candidates}
    assert candidates["positive"].role is CandidateRole.POSITIVE
    assert candidates["hard"].role is CandidateRole.HARD_NEGATIVE
    assert candidates["conflict"].role is CandidateRole.CONFLICTING
    for item in candidates.values():
        assert item.text and item.source and item.source_group_id
        assert item.collection == "selfrag_tencent"
        assert item.dense_score is not None
        assert item.sparse_score is not None
        assert item.fusion_score is not None
        assert item.rerank_score is not None


def test_test_source_candidates_never_leak_into_train() -> None:
    instance, _ = builder(
        result("train", 0.8, group="doc-train"),
        result("held-out", 0.9, group="doc-test"),
        rerank_scores={"train": 0.8, "held-out": 0.99},
    )

    built = instance.build(
        query(), split="train", test_source_group_ids=["doc-test"]
    )

    assert [item.chunk_id for item in built.snapshot.candidates] == ["train"]
    assert built.excluded_test_ids == ["held-out"]


def test_query_from_test_source_cannot_enter_enter_train() -> None:
    instance, _ = builder(result("held-out", 0.9, group="doc-test"))

    with pytest.raises(SchemaValidationError, match="test source"):
        instance.build(
            query("doc-test"), split="train", test_source_group_ids=["doc-test"]
        )


def test_cross_collection_candidate_is_rejected() -> None:
    instance, _ = builder(result("foreign", 0.8, collection="other"))

    with pytest.raises(SchemaValidationError, match="leaked from collection"):
        instance.build(query(), split="train")


def test_fixed_scores_have_deterministic_tie_break_by_chunk_id() -> None:
    scores = {"a": 0.5, "b": 0.5, "c": 0.5}
    first, _ = builder(
        result("c", 0.4), result("a", 0.4), result("b", 0.4), rerank_scores=scores
    )
    second, _ = builder(
        result("b", 0.4), result("c", 0.4), result("a", 0.4), rerank_scores=scores
    )

    first_ids = [item.chunk_id for item in first.build(query(), split="train").snapshot.candidates]
    second_ids = [item.chunk_id for item in second.build(query(), split="train").snapshot.candidates]

    assert first_ids == second_ids == ["a", "b", "c"]


def test_missing_positive_and_insufficient_negatives_are_explicit() -> None:
    instance, _ = builder(
        result("only", 0.2), rerank_scores={"only": 0.2}, hard_negatives=3
    )

    built = instance.build(
        query(), split="train", positive_chunk_ids=["not-retrieved"]
    )

    assert built.missing_positive_ids == ["not-retrieved"]
    assert built.hard_negative_ids == []
    assert built.insufficient_hard_negatives is True


def test_positive_and_conflicting_roles_cannot_overlap() -> None:
    instance, _ = builder(result("same", 0.8))

    with pytest.raises(ValueError, match="positive and conflicting"):
        instance.build(
            query(),
            split="train",
            positive_chunk_ids=["same"],
            conflicting_chunk_ids=["same"],
        )
