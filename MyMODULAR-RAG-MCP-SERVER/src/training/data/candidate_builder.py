"""Build auditable retrieval snapshots and hard negatives for training queries."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from src.core.query_engine.hybrid_search import HybridSearchResult
from src.core.query_engine.reranker import RerankResult
from src.core.types import RetrievalResult
from src.training.data.schemas import (
    CandidateRole,
    RetrievalCandidate,
    RetrievalSnapshot,
    SchemaValidationError,
    Split,
)
from src.training.data.synthetic_query_generator import SyntheticQuery


class HybridRetriever(Protocol):
    def search(self, query: str, **kwargs: Any) -> HybridSearchResult: ...


class CandidateReranker(Protocol):
    def rerank(
        self,
        query: str,
        results: list[RetrievalResult],
        **kwargs: Any,
    ) -> RerankResult: ...


@dataclass(frozen=True)
class CandidateBuilderConfig:
    collection: str
    index_version: str
    fusion_top_k: int = 10
    rerank_top_k: int = 8
    hard_negatives_per_sample: int = 3
    hard_negative_min_rerank_score: float = 0.3

    def __post_init__(self) -> None:
        if not self.collection.strip() or not self.index_version.strip():
            raise ValueError("collection and index_version must be non-empty")
        for name in ("fusion_top_k", "rerank_top_k", "hard_negatives_per_sample"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")


@dataclass
class CandidateBuildResult:
    query_id: str
    source_group_id: str
    snapshot: RetrievalSnapshot
    positive_ids: list[str] = field(default_factory=list)
    hard_negative_ids: list[str] = field(default_factory=list)
    conflicting_ids: list[str] = field(default_factory=list)
    excluded_test_ids: list[str] = field(default_factory=list)
    missing_positive_ids: list[str] = field(default_factory=list)
    insufficient_hard_negatives: bool = False
    used_rerank_fallback: bool = False


class CandidateBuilder:
    """Reuse online HybridSearch/Rerank while enforcing dataset boundaries."""

    def __init__(
        self,
        retriever: HybridRetriever,
        reranker: CandidateReranker,
        config: CandidateBuilderConfig,
    ) -> None:
        self._retriever = retriever
        self._reranker = reranker
        self._config = config

    def build(
        self,
        query: SyntheticQuery,
        *,
        split: Split | str,
        test_source_group_ids: Sequence[str] = (),
        positive_chunk_ids: Sequence[str] = (),
        conflicting_chunk_ids: Sequence[str] = (),
    ) -> CandidateBuildResult:
        split = Split(split)
        test_groups = set(test_source_group_ids)
        if split is not Split.TEST and query.source_group_id in test_groups:
            raise SchemaValidationError(
                "a query bound to a test source cannot enter train/dev candidates"
            )

        details = self._retriever.search(
            query.instruction,
            top_k=self._config.fusion_top_k,
            filters={"collection": self._config.collection},
            return_details=True,
        )
        if not isinstance(details, HybridSearchResult):
            raise TypeError("hybrid retriever must return HybridSearchResult details")

        dense_scores = self._score_map(details.dense_results)
        sparse_scores = self._score_map(details.sparse_results)
        fusion_scores = self._score_map(details.results)
        eligible: list[RetrievalResult] = []
        excluded_test_ids: list[str] = []
        for item in details.results:
            collection = item.metadata.get("collection")
            if collection is not None and collection != self._config.collection:
                raise SchemaValidationError(
                    f"candidate {item.chunk_id!r} leaked from collection {collection!r}"
                )
            group_id = self._source_group(item)
            if split is not Split.TEST and group_id in test_groups:
                excluded_test_ids.append(item.chunk_id)
                continue
            self._validate_traceability(item, group_id)
            eligible.append(item)

        reranked = self._reranker.rerank(
            query.instruction,
            eligible,
            top_k=self._config.rerank_top_k,
        )
        if not isinstance(reranked, RerankResult):
            raise TypeError("reranker must return RerankResult")

        positives = set(positive_chunk_ids)
        conflicts = set(conflicting_chunk_ids)
        overlap = positives & conflicts
        if overlap:
            raise ValueError(f"candidate IDs cannot be positive and conflicting: {sorted(overlap)}")

        ordered = sorted(
            reranked.results,
            key=lambda item: (
                -self._rerank_score(item, reranked),
                -fusion_scores.get(item.chunk_id, item.score),
                item.chunk_id,
            ),
        )
        negative_ids = [
            item.chunk_id
            for item in ordered
            if item.chunk_id not in positives
            and item.chunk_id not in conflicts
            and self._rerank_score(item, reranked)
            >= self._config.hard_negative_min_rerank_score
        ][: self._config.hard_negatives_per_sample]
        hard_negatives = set(negative_ids)

        candidates: list[RetrievalCandidate] = []
        for item in ordered:
            group_id = self._source_group(item)
            role = CandidateRole.RETRIEVED
            if item.chunk_id in positives:
                role = CandidateRole.POSITIVE
            elif item.chunk_id in conflicts:
                role = CandidateRole.CONFLICTING
            elif item.chunk_id in hard_negatives:
                role = CandidateRole.HARD_NEGATIVE
            candidates.append(
                RetrievalCandidate(
                    chunk_id=item.chunk_id,
                    text=item.text,
                    source=str(
                        item.metadata.get("source_path")
                        or item.metadata.get("source")
                    ),
                    dense_score=dense_scores.get(item.chunk_id),
                    sparse_score=sparse_scores.get(item.chunk_id),
                    fusion_score=fusion_scores.get(item.chunk_id),
                    rerank_score=self._rerank_score(item, reranked),
                    source_group_id=group_id,
                    collection=self._config.collection,
                    role=role,
                )
            )

        present_ids = {item.chunk_id for item in candidates}
        found_positive = sorted(positives & present_ids)
        return CandidateBuildResult(
            query_id=query.query_id,
            source_group_id=query.source_group_id,
            snapshot=RetrievalSnapshot(
                index_version=self._config.index_version,
                query=query.instruction,
                candidates=candidates,
            ),
            positive_ids=found_positive,
            hard_negative_ids=negative_ids,
            conflicting_ids=sorted(conflicts & present_ids),
            excluded_test_ids=sorted(excluded_test_ids),
            missing_positive_ids=sorted(positives - present_ids),
            insufficient_hard_negatives=(
                len(negative_ids) < self._config.hard_negatives_per_sample
            ),
            used_rerank_fallback=reranked.used_fallback,
        )

    @staticmethod
    def _score_map(
        results: Sequence[RetrievalResult] | None,
    ) -> dict[str, float]:
        return {item.chunk_id: float(item.score) for item in results or []}

    @staticmethod
    def _source_group(result: RetrievalResult) -> str:
        value = (
            result.metadata.get("source_group_id")
            or result.metadata.get("doc_hash")
            or result.metadata.get("source_hash")
        )
        return str(value or "")

    @staticmethod
    def _validate_traceability(result: RetrievalResult, group_id: str) -> None:
        source = result.metadata.get("source_path") or result.metadata.get("source")
        if not result.chunk_id or not result.text or not source or not group_id:
            raise SchemaValidationError(
                "every candidate requires chunk_id, text, source, and source_group_id"
            )

    @staticmethod
    def _rerank_score(result: RetrievalResult, reranked: RerankResult) -> float:
        value = result.metadata.get("rerank_score")
        if value is not None:
            return float(value)
        if reranked.reranker_type != "none" and not reranked.used_fallback:
            return float(result.score)
        return float(result.metadata.get("original_score", result.score))


__all__ = [
    "CandidateBuildResult",
    "CandidateBuilder",
    "CandidateBuilderConfig",
    "CandidateReranker",
    "HybridRetriever",
]
