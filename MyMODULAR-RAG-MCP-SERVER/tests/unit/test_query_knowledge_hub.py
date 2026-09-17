"""Offline contract tests for the traditional query_knowledge_hub path."""

from __future__ import annotations

import json

import pytest

from src.core.response.response_builder import ResponseBuilder
from src.core.types import RetrievalResult
from src.mcp_server.tools import query_knowledge_hub as query_tool_module
from src.mcp_server.tools.query_knowledge_hub import (
    QueryKnowledgeHubConfig,
    QueryKnowledgeHubTool,
    query_knowledge_hub_handler,
)


class FakeHybridSearch:
    """Deterministic traditional retriever used without external services."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def search(self, **kwargs):
        self.calls.append(kwargs)
        return [
            RetrievalResult(
                chunk_id="offline-doc:0001",
                score=0.91,
                text="Hybrid retrieval combines dense and sparse evidence.",
                metadata={
                    "source_path": "docs/offline.md",
                    "page": 3,
                    "collection": "offline",
                },
            )
        ]


@pytest.fixture
def offline_tool(monkeypatch):
    search = FakeHybridSearch()
    collected_traces = []
    monkeypatch.setattr(
        query_tool_module.TraceCollector,
        "collect",
        lambda _collector, trace: collected_traces.append(trace),
    )
    tool = QueryKnowledgeHubTool(
        config=QueryKnowledgeHubConfig(enable_rerank=False),
        hybrid_search=search,
        response_builder=ResponseBuilder(enable_multimodal=False),
    )
    return tool, search, collected_traces


@pytest.mark.asyncio
async def test_execute_uses_injected_traditional_pipeline(offline_tool):
    tool, search, traces = offline_tool

    response = await tool.execute(
        "How does hybrid retrieval work?",
        top_k=2,
        collection="offline",
    )

    assert response.is_empty is False
    assert "[1]" in response.content
    assert response.metadata["collection"] == "offline"
    assert len(response.citations) == 1
    assert response.citations[0].chunk_id == "offline-doc:0001"
    assert response.citations[0].source == "docs/offline.md"
    assert response.citations[0].page == 3
    assert search.calls[0]["query"] == "How does hybrid retrieval work?"
    assert search.calls[0]["top_k"] == 2
    assert search.calls[0]["return_details"] is False
    assert traces[0].metadata["collection"] == "offline"


@pytest.mark.asyncio
async def test_mcp_handler_preserves_text_and_structured_citations(
    monkeypatch,
    offline_tool,
):
    tool, _, _ = offline_tool
    monkeypatch.setattr(query_tool_module, "_tool_instance", tool)

    result = await query_knowledge_hub_handler(
        query="offline query",
        top_k=1,
        collection="offline",
    )

    assert result.is_error is False
    assert "[1]" in result.content[0].text
    structured_text = result.content[1].text
    payload = json.loads(structured_text.split("```json\n", 1)[1].split("\n```", 1)[0])
    assert payload["citations"][0]["chunk_id"] == "offline-doc:0001"
    assert payload["metadata"]["collection"] == "offline"


@pytest.mark.asyncio
async def test_empty_query_is_rejected_before_provider_initialization(offline_tool):
    tool, search, _ = offline_tool

    with pytest.raises(ValueError, match="Query cannot be empty"):
        await tool.execute("   ")

    assert search.calls == []
