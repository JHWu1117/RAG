"""Integrity checks for the supplied-document acceptance corpus and golden QA."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path


FIXTURES = Path(__file__).parents[1] / "fixtures"
DOCUMENTS = FIXTURES / "acceptance_documents"
GOLDEN_SET = FIXTURES / "acceptance_golden_test_set.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def test_acceptance_document_manifest_matches_supplied_files() -> None:
    payload = json.loads(GOLDEN_SET.read_text(encoding="utf-8"))

    assert len(payload["document_manifest"]) == 4
    for item in payload["document_manifest"]:
        source = DOCUMENTS / item["source"]
        assert source.is_file()
        assert _sha256(source) == item["sha256"]
        assert item["pages"] > 0


def test_acceptance_golden_set_has_balanced_traceable_cases() -> None:
    payload = json.loads(GOLDEN_SET.read_text(encoding="utf-8"))
    cases = payload["test_cases"]
    page_counts = {
        item["source"]: item["pages"]
        for item in payload["document_manifest"]
    }

    assert len(cases) == 20
    assert len({case["id"] for case in cases}) == 20
    assert Counter(case["expected_sources"][0] for case in cases) == {
        source: 5 for source in page_counts
    }

    for case in cases:
        assert case["query"].strip()
        assert case["reference_answer"].strip()
        assert case["expected_chunk_ids"] == []
        assert len(case["expected_sources"]) == 1
        assert case["expected_pages"]
        source = case["expected_sources"][0]
        assert source in page_counts
        assert all(1 <= page <= page_counts[source] for page in case["expected_pages"])
