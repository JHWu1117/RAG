"""Configuration-driven Teacher creation and deterministic provider fallback."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from typing import Any

from src.training.teacher.base_teacher import (
    BaseTeacherLLM,
    OpenAICompatibleTeacherLLM,
    TeacherError,
    TeacherResult,
    TeacherTransport,
)
from src.training.teacher.deepseek_teacher import DeepSeekTeacherLLM
from src.training.teacher.fake_teacher import FakeTeacherLLM
from src.training.teacher.kimi_teacher import KimiTeacherLLM

_ENV_REF = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")


class FallbackTeacherLLM(BaseTeacherLLM):
    """Use fallback only after the primary provider exhausts its own retries."""

    provider_name = "fallback_chain"

    def __init__(self, primary: BaseTeacherLLM, fallback: BaseTeacherLLM) -> None:
        self.primary = primary
        self.fallback = fallback
        self.model = f"{primary.model}->{fallback.model}"
        self.last_provider: str | None = None

    def generate_structured(
        self,
        prompt: str,
        schema: Mapping[str, Any],
        *,
        system_prompt: str | None = None,
        schema_name: str = "teacher_output",
    ) -> TeacherResult:
        try:
            result = self.primary.generate_structured(
                prompt, schema, system_prompt=system_prompt, schema_name=schema_name
            )
        except TeacherError:
            result = self.fallback.generate_structured(
                prompt, schema, system_prompt=system_prompt, schema_name=schema_name
            )
        self.last_provider = result.provider
        return result

    def probe_model(self) -> None:
        try:
            self.primary.probe_model()
        except TeacherError:
            self.fallback.probe_model()


class TeacherFactory:
    _PROVIDERS: dict[str, type[OpenAICompatibleTeacherLLM]] = {
        "kimi": KimiTeacherLLM,
        "deepseek": DeepSeekTeacherLLM,
        "openai_compatible": OpenAICompatibleTeacherLLM,
        "dashscope": OpenAICompatibleTeacherLLM,
    }

    @classmethod
    def create(
        cls,
        config: Mapping[str, Any],
        *,
        env: Mapping[str, str] | None = None,
        transport: TeacherTransport | None = None,
        probe_on_startup: bool = True,
    ) -> BaseTeacherLLM:
        if not isinstance(config, Mapping):
            raise ValueError("teacher config must be an object")
        environment = os.environ if env is None else env
        labeling = config.get("labeling", {})
        if not isinstance(labeling, Mapping):
            raise ValueError("teacher.labeling must be an object")
        primary = cls._create_one(
            config.get("primary"), labeling, environment, transport=transport
        )
        fallback_config = config.get("fallback")
        teacher: BaseTeacherLLM = primary
        if fallback_config is not None:
            fallback = cls._create_one(
                fallback_config, labeling, environment, transport=transport
            )
            teacher = FallbackTeacherLLM(primary, fallback)
        if probe_on_startup:
            teacher.probe_model()
        return teacher

    @classmethod
    def _create_one(
        cls,
        provider_config: Any,
        labeling: Mapping[str, Any],
        env: Mapping[str, str],
        *,
        transport: TeacherTransport | None,
    ) -> BaseTeacherLLM:
        if not isinstance(provider_config, Mapping):
            raise ValueError("Teacher provider config must be an object")
        provider = str(provider_config.get("provider", "")).strip().lower()
        if provider == "fake":
            return FakeTeacherLLM(
                response=provider_config.get("response", {}),
                model=str(provider_config.get("model", "fake-teacher")),
            )
        provider_type = cls._PROVIDERS.get(provider)
        if provider_type is None:
            available = ", ".join([*sorted(cls._PROVIDERS), "fake"])
            raise ValueError(f"Unsupported Teacher provider {provider!r}; available={available}")

        model = str(provider_config.get("model", "")).strip()
        api_key = cls._resolve_secret(provider_config, "api_key", "api_key_env", env)
        base_url = cls._resolve_value(provider_config, "base_url", "base_url_env", env)
        if not base_url:
            base_url = getattr(provider_type, "DEFAULT_BASE_URL", "")
        return provider_type(
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=float(labeling.get("temperature", 0.0)),
            max_tokens=int(labeling.get("max_tokens", 2048)),
            max_retries=int(labeling.get("max_retries", 3)),
            requests_per_minute=int(labeling.get("requests_per_minute", 30)),
            daily_budget_usd=cls._optional_float(labeling.get("daily_budget_usd")),
            input_cost_per_million_usd=float(
                provider_config.get("input_cost_per_million_usd", 0.0)
            ),
            output_cost_per_million_usd=float(
                provider_config.get("output_cost_per_million_usd", 0.0)
            ),
            require_json_schema=bool(labeling.get("require_json_schema", True)),
            native_schema_mode=provider_config.get("native_schema_mode"),
            timeout_seconds=float(labeling.get("timeout_seconds", 60.0)),
            transport=transport,
            provider_name=provider,
        )

    @staticmethod
    def _resolve_secret(
        config: Mapping[str, Any],
        value_key: str,
        env_key: str,
        env: Mapping[str, str],
    ) -> str:
        value = TeacherFactory._resolve_value(config, value_key, env_key, env)
        if not value:
            variable = config.get(env_key, "provider-specific environment variable")
            raise ValueError(f"Teacher API key is missing; configure environment variable {variable}")
        return value

    @staticmethod
    def _resolve_value(
        config: Mapping[str, Any],
        value_key: str,
        env_key: str,
        env: Mapping[str, str],
    ) -> str:
        direct = config.get(value_key)
        if isinstance(direct, str):
            match = _ENV_REF.fullmatch(direct.strip())
            return env.get(match.group(1), "") if match else direct.strip()
        variable = config.get(env_key)
        return env.get(str(variable), "") if variable else ""

    @staticmethod
    def _optional_float(value: Any) -> float | None:
        return None if value is None else float(value)


__all__ = ["FallbackTeacherLLM", "TeacherFactory"]
