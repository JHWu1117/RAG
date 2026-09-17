"""Deterministic offline Teacher used by tests and dry runs."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from typing import Any

import jsonschema

from src.training.teacher.base_teacher import (
    BaseTeacherLLM,
    TeacherError,
    TeacherResult,
    TeacherSchemaError,
    TeacherUsage,
)


class FakeTeacherLLM(BaseTeacherLLM):
    provider_name = "fake"

    def __init__(
        self,
        response: Mapping[str, Any] | None = None,
        *,
        model: str = "fake-teacher",
        responder: Callable[[str, Mapping[str, Any]], Mapping[str, Any]] | None = None,
        failure: Exception | None = None,
    ) -> None:
        self.model = model
        self._response = dict(response or {})
        self._responder = responder
        self._failure = failure
        self.calls = 0

    def generate_structured(
        self,
        prompt: str,
        schema: Mapping[str, Any],
        *,
        system_prompt: str | None = None,
        schema_name: str = "teacher_output",
    ) -> TeacherResult:
        del system_prompt, schema_name
        self.calls += 1
        if self._failure is not None:
            if isinstance(self._failure, TeacherError):
                raise self._failure
            raise TeacherError("FakeTeacher injected failure") from self._failure
        data = dict(self._responder(prompt, schema) if self._responder else self._response)
        try:
            jsonschema.validate(data, schema)
        except jsonschema.ValidationError as exc:
            raise TeacherSchemaError("FakeTeacher output failed JSON Schema validation") from exc
        raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return TeacherResult(
            data=data,
            provider=self.provider_name,
            model=self.model,
            usage=TeacherUsage(),
            raw_response_hash="sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            cost_usd=0.0,
        )

    def probe_model(self) -> None:
        if self._failure is not None:
            raise self._failure


__all__ = ["FakeTeacherLLM"]
