"""Offline integration coverage for the complete ingestion pipeline."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, List, Optional

import pytest

from src.core.settings import load_settings
from src.core.trace.trace_context import TraceContext
from src.ingestion.pipeline import IngestionPipeline
from src.libs.embedding.base_embedding import BaseEmbedding
from src.libs.embedding.embedding_factory import EmbeddingFactory


pytestmark = pytest.mark.integration


class DeterministicEmbedding(BaseEmbedding):
    """Small local embedding used to exercise storage without a provider call."""

    def __init__(self, settings: Any, **kwargs: Any) -> None:
        self.dimension = settings.embedding.dimensions

    def embed(
        self,
        texts: List[str],
        trace: Optional[Any] = None,
        **kwargs: Any,
    ) -> List[List[float]]:
        self.validate_texts(texts)
        return [
            [float((sum(text.encode("utf-8")) + offset) % 997) / 997.0
             for offset in range(self.dimension)]
            for text in texts
        ]

    def get_dimension(self) -> int:
        return self.dimension


@pytest.fixture()
def offline_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import src.ingestion.pipeline as pipeline_module

    settings = load_settings("config/settings.yaml")
    settings = replace(
        settings,
        embedding=replace(
            settings.embedding,
            provider="offline_test",
            model="deterministic",
            dimensions=4,
            api_key=None,
            azure_endpoint=None,
        ),
        vector_store=replace(
            settings.vector_store,
            persist_directory=str(tmp_path / "chroma"),
            collection_name="offline_default",
        ),
        ingestion=replace(
            settings.ingestion,
            chunk_refiner={"use_llm": False},
            metadata_enricher={"use_llm": False},
        ),
        vision_llm=replace(settings.vision_llm, enabled=False),
    )

    monkeypatch.setitem(
        EmbeddingFactory._PROVIDERS,
        "offline_test",
        DeterministicEmbedding,
    )
    monkeypatch.setattr(
        pipeline_module,
        "resolve_path",
        lambda value: tmp_path / Path(value),
    )
    return settings


def test_full_pipeline_roundtrip_and_incremental_skip(
    offline_settings: Any,
) -> None:
    source = Path("tests/fixtures/sample_documents/simple.pdf")
    trace = TraceContext(trace_type="ingestion")
    progress = []

    pipeline = IngestionPipeline(
        offline_settings,
        collection="offline_roundtrip",
        force=True,
    )
    try:
        first = pipeline.run(
            str(source),
            trace=trace,
            on_progress=lambda stage, current, total: progress.append(
                (stage, current, total)
            ),
        )
    finally:
        pipeline.close()

    assert first.success, first.error
    assert first.chunk_count > 0
    assert len(first.vector_ids) == first.chunk_count
    assert {entry["stage"] for entry in trace.stages} >= {
        "load", "split", "transform", "embed", "upsert",
    }
    assert {stage for stage, _, _ in progress} >= {
        "integrity", "load", "split", "transform", "embed", "upsert",
    }

    second_pipeline = IngestionPipeline(
        offline_settings,
        collection="offline_roundtrip",
        force=False,
    )
    try:
        second = second_pipeline.run(str(source))
    finally:
        second_pipeline.close()

    assert second.success
    assert second.stages["integrity"]["skipped"] is True
