"""Smoke tests for the public import paths required by the baseline spec."""

import importlib


def test_top_level_packages_are_importable() -> None:
    for package in ("mcp_server", "core", "ingestion", "libs", "observability"):
        assert importlib.import_module(package) is not None


def test_top_level_submodules_resolve_to_migrated_implementation() -> None:
    assert importlib.import_module("mcp_server.server") is not None
    assert importlib.import_module("core.settings") is not None
    assert importlib.import_module("ingestion.pipeline") is not None
    assert importlib.import_module("libs.vector_store.chroma_store") is not None
    assert importlib.import_module("observability.dashboard.app") is not None
