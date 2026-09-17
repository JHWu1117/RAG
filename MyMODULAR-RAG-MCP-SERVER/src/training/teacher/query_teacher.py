"""Adapter from the K5 structured Teacher to K3 synthetic-query generation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from src.training.data.synthetic_query_generator import QueryGenerationRequest, QueryKind
from src.training.teacher.base_teacher import BaseTeacherLLM


class StructuredQueryTeacher:
    def __init__(self, teacher: BaseTeacherLLM, prompt_path: str | Path | None = None) -> None:
        root = Path(__file__).resolve().parents[3]
        path = Path(prompt_path) if prompt_path else (
            root / "config" / "prompts" / "self_rag" / "teacher" / "query_generation_v1.md"
        )
        self._prompt = path.read_text(encoding="utf-8")
        self._teacher = teacher

    def generate_query(self, request: QueryGenerationRequest) -> Mapping[str, Any]:
        payload = {
            "source_text": request.source_text,
            "query_kind": request.query_kind.value,
            "language": request.language,
            "source_group_id": request.source_group_id,
        }
        prompt = self._prompt + "\n\nINPUT_JSON:\n" + json.dumps(
            payload, ensure_ascii=False, sort_keys=True
        )
        result = self._teacher.generate_structured(
            prompt,
            self._schema(request.query_kind),
            system_prompt="你是企业年报训练问题生成器。只输出符合 Schema 的 JSON。",
            schema_name="selfrag_query_generation_v1",
        )
        return result.data

    @staticmethod
    def _schema(kind: QueryKind) -> dict[str, Any]:
        answer_schema: dict[str, Any]
        if kind is QueryKind.UNANSWERABLE:
            answer_schema = {"type": "null"}
        else:
            answer_schema = {"type": ["string", "null"]}
        return {
            "type": "object",
            "properties": {
                "instruction": {"type": "string", "minLength": 3},
                "reference_answer": answer_schema,
            },
            "required": ["instruction", "reference_answer"],
            "additionalProperties": False,
        }


__all__ = ["StructuredQueryTeacher"]
