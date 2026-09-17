"""K2 tests for privacy filtering and canonical seed collection."""

from __future__ import annotations

import copy
import json

from src.core.types import Document
from src.training.data.privacy_filter import FindingKind, PrivacyFilter
from src.training.data.seed_collector import SeedCollector, SeedSource


def test_privacy_filter_redacts_required_fixture_types_without_mutation() -> None:
    original = {
        "secret": "sk-ws-example_token_1234567890",
        "nested": {
            "email": "reviewer@example.com",
            "message": "call 13812345678 then use Bearer abcdefghijklmnop",
        },
    }
    before = copy.deepcopy(original)

    result = PrivacyFilter().screen(original)

    assert original == before
    assert {finding.kind for finding in result.findings} == {
        FindingKind.API_SECRET,
        FindingKind.EMAIL,
        FindingKind.PHONE,
    }
    serialized = json.dumps(result.value)
    assert "example_token" not in serialized
    assert "reviewer@example.com" not in serialized
    assert "13812345678" not in serialized


def test_sensitive_mapping_key_is_redacted_for_unusual_token_format() -> None:
    result = PrivacyFilter().screen({"api_key": "vendor-specific-value"})

    assert not result.is_safe
    assert result.value == {"api_key": "[REDACTED]"}
    assert result.findings[0].kind is FindingKind.API_SECRET


def test_document_snapshot_becomes_content_addressed_seed_without_mutation() -> None:
    document = Document(
        id="doc-1",
        text="腾讯年度收入与研发投入摘要。",
        metadata={"source_path": "reports/tencent.pdf", "page": 3},
    )
    before = document.to_dict()

    collection = SeedCollector().collect_documents(
        [document],
        license_name="public_disclosure",
        authorization_basis="public_company_filing",
    )

    assert document.to_dict() == before
    assert len(collection.accepted) == 1
    assert not collection.quarantined
    seed = collection.accepted[0]
    assert seed.source is SeedSource.DOCUMENT
    assert seed.seed_id.startswith("sha256:")
    assert seed.source_group_id.startswith("doc_sha256:")
    assert seed.provenance.license_name == "public_disclosure"
    assert seed.metadata["page"] == 3


def test_document_with_email_or_phone_is_quarantined_and_safe() -> None:
    raw = {
        "id": "doc-sensitive",
        "text": "联系人 test@example.com，电话 13912345678。",
        "metadata": {"source_path": "sensitive.pdf"},
    }
    before = copy.deepcopy(raw)

    collection = SeedCollector().collect_documents(
        [raw], license_name="private", authorization_basis="owner_supplied"
    )

    assert raw == before
    assert not collection.accepted
    assert collection.quarantined[0].reason_codes == (
        "privacy:email",
        "privacy:phone",
    )
    serialized = json.dumps(collection.quarantined[0].sanitized_record)
    assert "test@example.com" not in serialized
    assert "13912345678" not in serialized


def test_golden_qa_is_read_only_and_preserves_expected_evidence(tmp_path) -> None:
    payload = {
        "version": "1",
        "test_cases": [
            {
                "query": "2024 年研发投入是多少？",
                "reference_answer": "研发投入为 706 亿元。",
                "expected_chunk_ids": ["c1"],
                "expected_sources": ["tencent-2024.pdf"],
                "expected_pages": [16],
            }
        ],
    }
    path = tmp_path / "golden.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    before = path.read_bytes()

    collection = SeedCollector().collect_golden_qa(path)

    assert path.read_bytes() == before
    seed = collection.accepted[0]
    assert seed.instruction == payload["test_cases"][0]["query"]
    assert seed.reference_answer == payload["test_cases"][0]["reference_answer"]
    assert seed.metadata["expected_chunk_ids"] == ["c1"]
    assert seed.source_group_id.startswith("golden_sha256:")


def _trace(*, opted_in: bool = True, query: str = "腾讯收入是多少？") -> dict:
    return {
        "trace_id": "trace-1",
        "trace_type": "query",
        "started_at": "2026-09-08T00:00:00Z",
        "stages": [],
        "metadata": {
            "query": query,
            "answer": "收入见年度报告。",
            "training_opt_in": opted_in,
        },
    }


def test_trace_collection_is_opt_in_by_default() -> None:
    raw = _trace(opted_in=True)
    before = copy.deepcopy(raw)

    collection = SeedCollector().collect_traces([raw])

    assert raw == before
    assert not collection.accepted
    assert collection.quarantined[0].reason_codes == ("trace_not_authorized",)


def test_global_opt_in_does_not_override_missing_per_trace_consent() -> None:
    collection = SeedCollector().collect_traces([_trace(opted_in=False)], opt_in=True)

    assert not collection.accepted
    assert collection.quarantined[0].reason_codes == ("trace_not_authorized",)


def test_truthy_string_is_not_valid_trace_consent() -> None:
    raw = _trace()
    raw["metadata"]["training_opt_in"] = "true"

    collection = SeedCollector().collect_traces([raw], opt_in=True)

    assert not collection.accepted
    assert collection.quarantined[0].reason_codes == ("trace_not_authorized",)


def test_explicitly_authorized_trace_becomes_seed_without_full_trace_copy() -> None:
    raw = _trace()
    before = copy.deepcopy(raw)

    collection = SeedCollector().collect_traces([raw], opt_in=True)

    assert raw == before
    seed = collection.accepted[0]
    assert seed.source is SeedSource.TRACE
    assert seed.instruction == "腾讯收入是多少？"
    assert seed.provenance.trace_opt_in is True
    assert seed.metadata == {"trace_id": "trace-1", "started_at": raw["started_at"]}


def test_authorized_trace_with_secret_is_quarantined_without_leak() -> None:
    raw = _trace(query="用 sk-ws-secret_123456789012345 调接口")

    collection = SeedCollector().collect_traces([raw], opt_in=True)

    assert not collection.accepted
    quarantine = collection.quarantined[0]
    assert "privacy:api_secret" in quarantine.reason_codes
    assert "secret_123456" not in json.dumps(quarantine.sanitized_record)


def test_query_can_be_recovered_from_query_stage() -> None:
    raw = _trace()
    raw["metadata"].pop("query")
    raw["stages"] = [
        {"stage": "query_processing", "data": {"original_query": "跨年比较"}}
    ]

    collection = SeedCollector().collect_traces([raw], opt_in=True)

    assert collection.accepted[0].instruction == "跨年比较"


def test_jsonl_trace_source_is_read_only(tmp_path) -> None:
    path = tmp_path / "traces.jsonl"
    path.write_text(json.dumps(_trace(), ensure_ascii=False) + "\n", encoding="utf-8")
    before = path.read_bytes()

    collection = SeedCollector().collect_traces(path, opt_in=True)

    assert path.read_bytes() == before
    assert len(collection.accepted) == 1
    assert collection.accepted[0].provenance.source_uri == str(path)
