"""K1 dataset manifest: the reproducibility record for one built dataset.

A manifest answers, after the fact: which documents went in, which teacher and
prompt versions produced the labels, how the data was split, what the label
distribution looked like, and what it cost. Split assignment is recorded as
group-id hashes so a reviewer can verify that no source group leaked across
train/dev/test without needing the raw documents.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.training.data.schemas import (
    SchemaValidationError,
    Split,
    TrainingSample,
    _non_empty_str,
)

MANIFEST_VERSION = 1


def _group_hash(group_id: str) -> str:
    return "sha256:" + hashlib.sha256(group_id.encode("utf-8")).hexdigest()


@dataclass
class SourceDocument:
    """One input document, identified by content hash rather than path."""

    source_group_id: str
    filename: str
    content_sha256: str
    pages: int | None = None
    license: str | None = None

    def __post_init__(self) -> None:
        self.source_group_id = _non_empty_str(self.source_group_id, "source_group_id")
        self.filename = _non_empty_str(self.filename, "filename")
        self.content_sha256 = _non_empty_str(self.content_sha256, "content_sha256")
        if self.pages is not None and (
            isinstance(self.pages, bool) or not isinstance(self.pages, int) or self.pages < 0
        ):
            raise SchemaValidationError("pages must be a non-negative integer or null")

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_group_id": self.source_group_id,
            "filename": self.filename,
            "content_sha256": self.content_sha256,
            "pages": self.pages,
            "license": self.license,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SourceDocument:
        return cls(**dict(data))


@dataclass
class CostReport:
    """What building this dataset consumed."""

    teacher_requests: int = 0
    teacher_failures: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    estimated_usd: float = 0.0
    wall_time_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "teacher_requests": self.teacher_requests,
            "teacher_failures": self.teacher_failures,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "estimated_usd": round(self.estimated_usd, 6),
            "wall_time_seconds": round(self.wall_time_seconds, 3),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CostReport:
        return cls(**dict(data))


@dataclass
class DatasetManifest:
    """Full provenance for one dataset build."""

    dataset_version: str
    index_version: str
    teacher_models: list[str] = field(default_factory=list)
    prompt_versions: list[str] = field(default_factory=list)
    source_documents: list[SourceDocument] = field(default_factory=list)
    split_seed: int = 0
    split_ratios: dict[str, float] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    task_distribution: dict[str, int] = field(default_factory=dict)
    label_distribution: dict[str, dict[str, int]] = field(default_factory=dict)
    split_group_hashes: dict[str, list[str]] = field(default_factory=dict)
    cost: CostReport = field(default_factory=CostReport)
    created_at: str = ""
    manifest_version: int = MANIFEST_VERSION

    def __post_init__(self) -> None:
        self.dataset_version = _non_empty_str(self.dataset_version, "dataset_version")
        self.index_version = _non_empty_str(self.index_version, "index_version")
        self.source_documents = [
            item if isinstance(item, SourceDocument) else SourceDocument.from_dict(item)
            for item in self.source_documents
        ]
        if not isinstance(self.cost, CostReport):
            self.cost = CostReport.from_dict(self.cost)
        if self.split_ratios:
            total = sum(self.split_ratios.values())
            if abs(total - 1.0) > 1e-6:
                raise SchemaValidationError(
                    f"split_ratios must sum to 1, got {total}"
                )
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def assert_no_group_leakage(self) -> None:
        """Fail loudly if one source group appears in more than one split."""

        seen: dict[str, str] = {}
        for split_name, hashes in self.split_group_hashes.items():
            for group_hash in hashes:
                if group_hash in seen and seen[group_hash] != split_name:
                    raise SchemaValidationError(
                        f"source group {group_hash} leaked across "
                        f"{seen[group_hash]} and {split_name}"
                    )
                seen[group_hash] = split_name

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_version": self.manifest_version,
            "dataset_version": self.dataset_version,
            "index_version": self.index_version,
            "teacher_models": list(self.teacher_models),
            "prompt_versions": list(self.prompt_versions),
            "source_documents": [doc.to_dict() for doc in self.source_documents],
            "split_seed": self.split_seed,
            "split_ratios": dict(self.split_ratios),
            "counts": dict(self.counts),
            "task_distribution": dict(self.task_distribution),
            "label_distribution": {k: dict(v) for k, v in self.label_distribution.items()},
            "split_group_hashes": {k: list(v) for k, v in self.split_group_hashes.items()},
            "cost": self.cost.to_dict(),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DatasetManifest:
        if not isinstance(data, Mapping):
            raise SchemaValidationError("manifest must be an object")
        return cls(**dict(data))

    def save(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return target

    @classmethod
    def load(cls, path: str | Path) -> DatasetManifest:
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def summarize(
    samples: Sequence[TrainingSample],
    *,
    dataset_version: str,
    index_version: str,
    source_documents: Iterable[SourceDocument] = (),
    split_seed: int = 0,
    split_ratios: Mapping[str, float] | None = None,
    cost: CostReport | None = None,
) -> DatasetManifest:
    """Build a manifest by measuring an actual sample list."""

    tasks: Counter[str] = Counter()
    retrieve: Counter[str] = Counter()
    relevance: Counter[str] = Counter()
    support: Counter[str] = Counter()
    utility: Counter[str] = Counter()
    splits: Counter[str] = Counter()
    teachers: set[str] = set()
    prompts: set[str] = set()
    group_hashes: dict[str, set[str]] = {member.value: set() for member in Split}

    for sample in samples:
        tasks[sample.task_type.value] += 1
        splits[sample.split.value] += 1
        retrieve[sample.labels.retrieve.value] += 1
        teachers.add(f"{sample.teacher.provider}:{sample.teacher.model}")
        prompts.add(sample.teacher.prompt_version)
        group_hashes[sample.split.value].add(_group_hash(sample.source_group_id))
        for evidence in sample.labels.evidence:
            relevance[evidence.relevance.value] += 1
        for segment in sample.labels.segments:
            support[segment.support.value] += 1
            utility[str(segment.utility)] += 1

    manifest = DatasetManifest(
        dataset_version=dataset_version,
        index_version=index_version,
        teacher_models=sorted(teachers),
        prompt_versions=sorted(prompts),
        source_documents=list(source_documents),
        split_seed=split_seed,
        split_ratios=dict(split_ratios or {}),
        counts={"total": len(samples), **{k: v for k, v in sorted(splits.items())}},
        task_distribution=dict(sorted(tasks.items())),
        label_distribution={
            "retrieve": dict(sorted(retrieve.items())),
            "relevance": dict(sorted(relevance.items())),
            "support": dict(sorted(support.items())),
            "utility": dict(sorted(utility.items())),
        },
        split_group_hashes={k: sorted(v) for k, v in group_hashes.items() if v},
        cost=cost or CostReport(),
    )
    manifest.assert_no_group_leakage()
    return manifest


__all__ = [
    "CostReport",
    "DatasetManifest",
    "MANIFEST_VERSION",
    "SourceDocument",
    "summarize",
]
