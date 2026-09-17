#!/usr/bin/env python
"""Build a small real Chinese Critic JSONL preview from the local RAG index."""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import chromadb
import yaml
from chromadb.config import Settings as ChromaSettings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.query import _build_components  # noqa: E402
from src.core.settings import load_settings  # noqa: E402
from src.training.data.candidate_builder import (  # noqa: E402
    CandidateBuilder,
    CandidateBuilderConfig,
)
from src.training.data.privacy_filter import PrivacyFilter  # noqa: E402
from src.training.data.schemas import Split, write_jsonl  # noqa: E402
from src.training.data.seed_collector import (  # noqa: E402
    CanonicalSeed,
    SeedProvenance,
    SeedSource,
)
from src.training.data.synthetic_query_generator import SyntheticQueryGenerator  # noqa: E402
from src.training.teacher.labeler import ReflectionLabeler  # noqa: E402
from src.training.teacher.query_teacher import StructuredQueryTeacher  # noqa: E402
from src.training.teacher.teacher_factory import TeacherFactory  # noqa: E402


class CollectionBoundHybrid:
    """The selected Chroma collection is already the isolation boundary."""

    def __init__(self, hybrid) -> None:
        self._hybrid = hybrid

    def search(self, query: str, **kwargs):
        kwargs["filters"] = None
        return self._hybrid.search(query, **kwargs)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=30)
    parser.add_argument("--config", default="config/settings.selfrag.ingest.yaml")
    parser.add_argument("--dataset-config", default="config/dataset.yaml")
    parser.add_argument("--output", default="data/training/preview/critic.jsonl")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def select_seeds(settings, collection: str, count: int) -> tuple[list[CanonicalSeed], dict[str, str]]:
    client = chromadb.PersistentClient(
        path=str(ROOT / "data" / "selfrag" / "chroma"),
        settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True),
    )
    store = client.get_collection(collection)
    records = store.get(include=["documents", "metadatas"])
    privacy = PrivacyFilter()
    candidates = sorted(
        zip(records["ids"], records["documents"], records["metadatas"]),
        key=lambda item: (str(item[2].get("doc_hash", "")), int(item[2].get("chunk_index", 0))),
    )
    seeds: list[CanonicalSeed] = []
    seed_chunks: dict[str, str] = {}
    seen_groups: dict[str, int] = {}
    max_per_group = max(2, (count + 1) // 2)
    for chunk_id, text, metadata in candidates:
        if len(text.strip()) < 220 or text.lstrip().startswith("[IMAGE:"):
            continue
        screened = privacy.screen({"text": text, "metadata": metadata})
        if screened.findings:
            continue
        doc_hash = str(metadata.get("doc_hash", ""))
        if not doc_hash or seen_groups.get(doc_hash, 0) >= max_per_group:
            continue
        seed = CanonicalSeed(
            source=SeedSource.DOCUMENT,
            source_group_id=f"doc_sha256:{doc_hash}",
            content=text,
            provenance=SeedProvenance(
                source_uri=str(metadata.get("source_path", "local-index")),
                content_sha256="sha256:" + __import__("hashlib").sha256(text.encode()).hexdigest(),
                license_name="public_disclosure",
                authorization_basis="public_company_filing",
            ),
            metadata={"chunk_id": chunk_id, "page": metadata.get("page_num")},
        )
        seeds.append(seed)
        seed_chunks[seed.seed_id] = chunk_id
        seen_groups[doc_hash] = seen_groups.get(doc_hash, 0) + 1
        if len(seeds) >= count:
            break
    if len(seeds) < count:
        raise RuntimeError(f"only {len(seeds)} privacy-safe text seeds available for {count}")
    return seeds, seed_chunks


def main() -> int:
    args = parse_args()
    if args.count < 1 or args.count > 50:
        raise ValueError("preview count must be between 1 and 50")
    settings = load_settings(args.config)
    dataset = yaml.safe_load(Path(args.dataset_config).read_text(encoding="utf-8"))
    # A preview must fail cheaply and surface the bad sample; full retry policy
    # belongs to the resumable production exporter.
    dataset["teacher"]["labeling"]["max_retries"] = 0
    collection = dataset["corpus"]["collection"]
    seeds, seed_chunks = select_seeds(settings, collection, args.count)
    if args.dry_run:
        print(json.dumps({"planned": args.count, "safe_seeds": len(seeds), "teacher_calls": 0}))
        return 0

    teacher = TeacherFactory.create(dataset["teacher"])
    query_generator = SyntheticQueryGenerator(
        StructuredQueryTeacher(teacher),
        prompt_version=dataset["synthetic_queries"]["prompt_version"],
        max_attempts_per_query=dataset["synthetic_queries"]["max_attempts_per_query"],
    )
    generated = query_generator.generate(
        seeds,
        total=args.count,
        query_kind_ratios=dataset["synthetic_queries"]["query_kind_ratios"],
        language_ratios=dataset["target"]["language_ratios"],
    )
    hybrid, reranker = _build_components(settings, collection)
    builder = CandidateBuilder(
        CollectionBoundHybrid(hybrid),
        reranker,
        CandidateBuilderConfig(
            collection=collection,
            index_version=f"chroma:{collection}@count-{len(seeds)}",
            fusion_top_k=dataset["retrieval"]["fusion_top_k"],
            rerank_top_k=dataset["retrieval"]["rerank_top_k"],
            hard_negatives_per_sample=dataset["retrieval"]["hard_negatives_per_sample"],
            hard_negative_min_rerank_score=dataset["retrieval"]["hard_negative_min_rerank_score"],
        ),
    )
    labeler = ReflectionLabeler(
        teacher,
        dataset_version=dataset["dataset_version"],
        temperature=dataset["teacher"]["labeling"]["temperature"],
    )
    prepared = []
    for query in generated.queries:
        built = builder.build(
            query,
            split=Split.TRAIN,
            positive_chunk_ids=[seed_chunks[query.source_seed_id]],
        )
        prepared.append((query, built.snapshot))

    accepted_by_index = {}
    quarantined_by_index = {}
    concurrency = max(
        1,
        min(args.count, int(dataset["teacher"]["labeling"].get("concurrency", 1))),
    )
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {
            executor.submit(labeler.label, query, snapshot): index
            for index, (query, snapshot) in enumerate(prepared)
        }
        for completed, future in enumerate(as_completed(futures), 1):
            index = futures[future]
            outcome = future.result()
            if outcome.sample is not None:
                accepted_by_index[index] = outcome.sample
            else:
                quarantined_by_index[index] = outcome.quarantine.to_dict()
            print(
                f"[{completed}/{args.count}] accepted={len(accepted_by_index)} "
                f"quarantine={len(quarantined_by_index)}"
            )

    accepted = [accepted_by_index[index] for index in sorted(accepted_by_index)]
    quarantined = [
        quarantined_by_index[index] for index in sorted(quarantined_by_index)
    ]

    output = ROOT / args.output
    write_jsonl(output, accepted)
    quarantine_path = output.with_name("quarantine.jsonl")
    quarantine_path.parent.mkdir(parents=True, exist_ok=True)
    quarantine_path.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in quarantined),
        encoding="utf-8",
    )
    print(json.dumps({"accepted": len(accepted), "quarantined": len(quarantined), "output": str(output)}))
    return 0 if accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
