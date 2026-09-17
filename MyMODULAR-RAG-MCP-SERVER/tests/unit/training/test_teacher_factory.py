"""K5 unit tests: independent Teacher providers, validation, and fallback."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml

from src.training.teacher.base_teacher import (
    BudgetExceededError,
    DailyBudget,
    ModelProbeError,
    OpenAICompatibleTeacherLLM,
    TeacherError,
    TeacherSchemaError,
)
from src.training.teacher.deepseek_teacher import DeepSeekTeacherLLM
from src.training.teacher.fake_teacher import FakeTeacherLLM
from src.training.teacher.kimi_teacher import KimiTeacherLLM
from src.training.teacher.teacher_factory import FallbackTeacherLLM, TeacherFactory

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA = {
    "type": "object",
    "properties": {"label": {"type": "string", "enum": ["yes", "no"]}},
    "required": ["label"],
    "additionalProperties": False,
}


class RecordingTransport:
    def __init__(self, responses: list[Mapping[str, Any] | Exception]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def request(self, method, url, *, headers, payload, timeout):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers),
                "payload": payload,
                "timeout": timeout,
            }
        )
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def completion(content: str, *, model: str = "teacher-model") -> dict[str, Any]:
    return {
        "model": model,
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
    }


def base_config(provider: str, *, fallback: bool = False) -> dict[str, Any]:
    config: dict[str, Any] = {
        "primary": {
            "provider": provider,
            "model": f"{provider}-model",
            "base_url_env": "TEACHER_BASE_URL",
            "api_key_env": "TEACHER_API_KEY",
        },
        "labeling": {
            "max_retries": 0,
            "requests_per_minute": 100,
            "require_json_schema": True,
        },
    }
    if fallback:
        config["fallback"] = {
            "provider": "deepseek",
            "model": "deepseek-v4-pro",
            "api_key_env": "DEEPSEEK_API_KEY",
        }
    return config


def test_factory_switches_provider_using_only_config() -> None:
    env = {"TEACHER_BASE_URL": "https://teacher.test/v1", "TEACHER_API_KEY": "secret"}

    kimi = TeacherFactory.create(base_config("kimi"), env=env, probe_on_startup=False)
    deepseek = TeacherFactory.create(
        base_config("deepseek"), env=env, probe_on_startup=False
    )
    compatible = TeacherFactory.create(
        base_config("openai_compatible"), env=env, probe_on_startup=False
    )

    assert isinstance(kimi, KimiTeacherLLM)
    assert isinstance(deepseek, DeepSeekTeacherLLM)
    assert isinstance(compatible, OpenAICompatibleTeacherLLM)
    assert {kimi.provider_name, deepseek.provider_name, compatible.provider_name} == {
        "kimi",
        "deepseek",
        "openai_compatible",
    }


def test_primary_failure_falls_back_to_deepseek() -> None:
    primary = FakeTeacherLLM(failure=TeacherError("primary unavailable"), model="kimi-k3")
    primary.provider_name = "kimi"
    fallback = FakeTeacherLLM({"label": "yes"}, model="deepseek-v4-pro")
    fallback.provider_name = "deepseek"
    chain = FallbackTeacherLLM(primary, fallback)

    result = chain.generate_structured("judge", SCHEMA)

    assert result.data == {"label": "yes"}
    assert result.provider == "deepseek"
    assert chain.last_provider == "deepseek"
    assert primary.calls == fallback.calls == 1


def test_fake_teacher_is_deterministic_and_offline() -> None:
    teacher = FakeTeacherLLM({"label": "yes"})

    first = teacher.generate_structured("one", SCHEMA)
    second = teacher.generate_structured("two", SCHEMA)

    assert first.data == second.data == {"label": "yes"}
    assert first.raw_response_hash == second.raw_response_hash
    assert first.cost_usd == 0
    assert teacher.calls == 2


def test_openai_compatible_provider_sends_schema_and_validates_response() -> None:
    transport = RecordingTransport([completion('{"label":"yes"}', model="qwen")])
    teacher = OpenAICompatibleTeacherLLM(
        model="qwen",
        api_key="do-not-log-this",
        base_url="https://teacher.test/v1/",
        max_retries=0,
        transport=transport,
    )

    result = teacher.generate_structured("只输出 JSON", SCHEMA, schema_name="reflection")

    request = transport.calls[0]
    assert request["url"] == "https://teacher.test/v1/chat/completions"
    assert request["payload"]["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "reflection", "strict": True, "schema": SCHEMA},
    }
    assert result.data == {"label": "yes"}
    assert result.raw_response_hash.startswith("sha256:")
    assert "do-not-log-this" not in repr(teacher)


def test_deepseek_preserves_json_object_wire_difference_but_validates_locally() -> None:
    transport = RecordingTransport([completion('{"label":"yes"}')])
    teacher = DeepSeekTeacherLLM(
        model="deepseek-v4-pro",
        api_key="secret",
        base_url="https://deepseek.test",
        max_retries=0,
        transport=transport,
    )

    teacher.generate_structured("judge", SCHEMA)

    payload = transport.calls[0]["payload"]
    assert payload["response_format"] == {"type": "json_object"}
    user_prompt = payload["messages"][-1]["content"]
    assert user_prompt.startswith("judge\n\nOUTPUT_JSON_SCHEMA:\n")
    assert '"required":["label"]' in user_prompt


def test_invalid_teacher_output_is_rejected_after_retries() -> None:
    transport = RecordingTransport([completion('{"label":"unknown"}')])
    teacher = OpenAICompatibleTeacherLLM(
        model="teacher",
        api_key="secret",
        base_url="https://teacher.test/v1",
        max_retries=0,
        transport=transport,
    )

    with pytest.raises(TeacherSchemaError, match="JSON Schema"):
        teacher.generate_structured("judge", SCHEMA)


def test_model_probe_checks_configured_alias() -> None:
    available = RecordingTransport([{"data": [{"id": "qwen3.5-omni-plus"}]}])
    teacher = OpenAICompatibleTeacherLLM(
        model="qwen3.5-omni-plus",
        api_key="secret",
        base_url="https://teacher.test/v1",
        transport=available,
    )
    teacher.probe_model()
    assert available.calls[0]["method"] == "GET"

    missing = RecordingTransport([{"data": [{"id": "another-model"}]}])
    teacher = OpenAICompatibleTeacherLLM(
        model="qwen3.8-27b",
        api_key="secret",
        base_url="https://teacher.test/v1",
        transport=missing,
    )
    with pytest.raises(ModelProbeError, match="unavailable"):
        teacher.probe_model()


def test_budget_blocks_request_before_transport_call() -> None:
    transport = RecordingTransport([completion('{"label":"yes"}')])
    teacher = OpenAICompatibleTeacherLLM(
        model="teacher",
        api_key="secret",
        base_url="https://teacher.test/v1",
        max_tokens=100,
        max_retries=0,
        transport=transport,
        budget=DailyBudget(0.00001, output_per_million_usd=100.0),
    )

    with pytest.raises(BudgetExceededError):
        teacher.generate_structured("judge", SCHEMA)
    assert not transport.calls


def test_factory_probe_uses_fallback_when_primary_alias_is_missing() -> None:
    transport = RecordingTransport(
        [
            {"data": [{"id": "not-kimi"}]},
            {"data": [{"id": "deepseek-v4-pro"}]},
        ]
    )
    config = base_config("kimi", fallback=True)
    env = {
        "TEACHER_BASE_URL": "https://kimi.test/v1",
        "TEACHER_API_KEY": "kimi-secret",
        "DEEPSEEK_API_KEY": "deepseek-secret",
    }

    chain = TeacherFactory.create(config, env=env, transport=transport)

    assert isinstance(chain, FallbackTeacherLLM)
    assert [call["url"] for call in transport.calls] == [
        "https://kimi.test/v1/models",
        "https://api.deepseek.com/models",
    ]


def test_factory_errors_do_not_disclose_secret_values() -> None:
    config = base_config("kimi")
    with pytest.raises(ValueError) as error:
        TeacherFactory.create(config, env={}, probe_on_startup=False)
    assert "super-secret" not in str(error.value)


def test_dataset_config_uses_independent_teacher_environment_references() -> None:
    config = yaml.safe_load((REPO_ROOT / "config" / "dataset.yaml").read_text("utf-8"))
    teacher = config["teacher"]

    assert teacher["primary"]["provider"] == "openai_compatible"
    assert teacher["primary"]["api_key_env"] == "OPENAI_API_KEY"
    assert "api_key" not in teacher["primary"]
    assert teacher["labeling"]["require_json_schema"] is True
    raw = (REPO_ROOT / "config" / "dataset.yaml").read_text("utf-8")
    assert "sk-" not in raw
