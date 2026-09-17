"""Evaluate page-grounded hybrid retrieval against the acceptance PDF corpus.

This runner calls embeddings only. It never invokes a chat or vision model.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path, PureWindowsPath

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.query import _build_components
from src.core.settings import load_settings


def _source_name(value: object) -> str:
    text = str(value or "")
    # Stored paths may originate from either Windows or POSIX runs.
    return PureWindowsPath(text).name if "\\" in text else Path(text).name


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--golden",
        default="tests/fixtures/acceptance_golden_test_set.json",
    )
    parser.add_argument("--config", default="config/settings.dashscope.bulk.yaml")
    parser.add_argument("--top-k", type=int, default=10)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    golden = json.loads(Path(args.golden).read_text(encoding="utf-8"))
    settings = load_settings(args.config)
    collection = golden["collection"]
    hybrid, _ = _build_components(settings, collection)

    # Verify that every labelled source/page pair has at least one indexed chunk.
    stored = hybrid.dense_retriever.vector_store.collection.get(
        include=["metadatas"]
    )
    indexed_pairs = {
        (_source_name(meta.get("source_path")), meta.get("page_num"))
        for meta in stored.get("metadatas", [])
    }

    cases = []
    reciprocal_rank_sum = 0.0
    hits = 0
    for case in golden["test_cases"]:
        expected_pairs = {
            (source, page)
            for source in case["expected_sources"]
            for page in case["expected_pages"]
        }
        missing_pairs = sorted(expected_pairs - indexed_pairs)
        results = hybrid.search(case["query"], top_k=args.top_k)
        rank = next(
            (
                index
                for index, result in enumerate(results, start=1)
                if (
                    _source_name(result.metadata.get("source_path")),
                    result.metadata.get("page_num"),
                )
                in expected_pairs
            ),
            None,
        )
        if rank is not None:
            hits += 1
            reciprocal_rank_sum += 1.0 / rank
        cases.append(
            {
                "id": case["id"],
                "rank": rank,
                "hit": rank is not None,
                "missing_indexed_pairs": missing_pairs,
                "top": [
                    {
                        "chunk_id": result.chunk_id,
                        "source": _source_name(result.metadata.get("source_path")),
                        "page": result.metadata.get("page_num"),
                    }
                    for result in results[:3]
                ],
            }
        )

    total = len(cases)
    report = {
        "collection": collection,
        "indexed_chunks": len(stored.get("ids", [])),
        "cases": total,
        "top_k": args.top_k,
        "hit_rate": hits / total if total else 0.0,
        "mrr": reciprocal_rank_sum / total if total else 0.0,
        "results": cases,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if hits == total and all(not c["missing_indexed_pairs"] for c in cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
