"""Provider-independent contracts and OpenAI-compatible Teacher transport.

The offline Teacher plane deliberately does not reuse the online Student LLM
settings.  Responses are schema validated and represented by a digest plus
normalized data; raw provider payloads and credentials never enter datasets.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
import jsonschema


class TeacherError(RuntimeError):
    """Base error for an unavailable or invalid Teacher response."""


class TeacherSchemaError(TeacherError):
    """Raised when a Teacher response does not satisfy the requested schema."""


class ModelProbeError(TeacherError):
    """Raised when the configured model cannot be verified at startup."""


class BudgetExceededError(TeacherError):
    """Raised before a request that would exceed the configured daily budget."""


@dataclass(frozen=True)
class TeacherUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass(frozen=True)
class TeacherResult:
    data: Mapping[str, Any]
    provider: str
    model: str
    usage: TeacherUsage
    raw_response_hash: str
    cost_usd: float


class TeacherTransport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, Any] | None,
        timeout: float,
    ) -> Mapping[str, Any]: ...


class HttpxTeacherTransport:
    """Small synchronous transport whose errors never echo response bodies."""

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, Any] | None,
        timeout: float,
    ) -> Mapping[str, Any]:
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.request(method, url, headers=dict(headers), json=payload)
        except httpx.TimeoutException as exc:
            raise TeacherError("Teacher request timed out") from exc
        except httpx.RequestError as exc:
            raise TeacherError(f"Teacher connection failed ({type(exc).__name__})") from exc
        if not response.is_success:
            # Provider bodies can contain echoed prompts or account metadata.
            provider_code = "unknown"
            try:
                error = response.json().get("error", {})
                if isinstance(error, Mapping):
                    candidate = error.get("code") or error.get("type")
                    if isinstance(candidate, str) and candidate.isascii():
                        provider_code = candidate[:80]
            except (ValueError, AttributeError):
                pass
            raise TeacherError(
                f"Teacher API returned HTTP {response.status_code} ({provider_code})"
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise TeacherError("Teacher API returned invalid JSON") from exc
        if not isinstance(body, Mapping):
            raise TeacherError("Teacher API response must be a JSON object")
        return body


class SlidingWindowRateLimiter:
    def __init__(
        self,
        requests_per_minute: int,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if isinstance(requests_per_minute, bool) or requests_per_minute < 1:
            raise ValueError("requests_per_minute must be a positive integer")
        self._limit = requests_per_minute
        self._clock = clock
        self._sleep = sleeper
        self._timestamps: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = self._clock()
                while self._timestamps and now - self._timestamps[0] >= 60.0:
                    self._timestamps.popleft()
                if len(self._timestamps) < self._limit:
                    self._timestamps.append(now)
                    return
                delay = max(0.0, 60.0 - (now - self._timestamps[0]))
            self._sleep(delay)


class DailyBudget:
    """Process-local UTC-day budget ledger using configured token prices."""

    def __init__(
        self,
        limit_usd: float | None,
        *,
        input_per_million_usd: float = 0.0,
        output_per_million_usd: float = 0.0,
    ) -> None:
        if limit_usd is not None and limit_usd < 0:
            raise ValueError("daily_budget_usd must be non-negative")
        if input_per_million_usd < 0 or output_per_million_usd < 0:
            raise ValueError("token prices must be non-negative")
        self.limit_usd = limit_usd
        self.input_price = input_per_million_usd
        self.output_price = output_per_million_usd
        self.spent_usd = 0.0
        self._lock = threading.Lock()

    def estimate(self, prompt_tokens: int, completion_tokens: int) -> float:
        return (
            prompt_tokens * self.input_price + completion_tokens * self.output_price
        ) / 1_000_000

    def authorize(self, estimated_cost: float) -> None:
        with self._lock:
            if self.limit_usd is not None and self.spent_usd + estimated_cost > self.limit_usd:
                raise BudgetExceededError("Teacher daily budget would be exceeded")

    def record(self, cost: float) -> None:
        with self._lock:
            self.spent_usd += cost


class BaseTeacherLLM(ABC):
    provider_name: str
    model: str

    @abstractmethod
    def generate_structured(
        self,
        prompt: str,
        schema: Mapping[str, Any],
        *,
        system_prompt: str | None = None,
        schema_name: str = "teacher_output",
    ) -> TeacherResult:
        """Generate and validate one structured result."""

    @abstractmethod
    def probe_model(self) -> None:
        """Fail fast when the configured model alias is not available."""


class OpenAICompatibleTeacherLLM(BaseTeacherLLM):
    """OpenAI-compatible implementation shared by Kimi, DeepSeek, and DashScope."""

    provider_name = "openai_compatible"
    native_schema_mode = "json_schema"

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        base_url: str,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        max_retries: int = 3,
        requests_per_minute: int = 30,
        daily_budget_usd: float | None = None,
        input_cost_per_million_usd: float = 0.0,
        output_cost_per_million_usd: float = 0.0,
        require_json_schema: bool = True,
        native_schema_mode: str | None = None,
        timeout_seconds: float = 60.0,
        transport: TeacherTransport | None = None,
        rate_limiter: SlidingWindowRateLimiter | None = None,
        budget: DailyBudget | None = None,
        provider_name: str | None = None,
    ) -> None:
        if not model.strip():
            raise ValueError("Teacher model must be non-empty")
        if not api_key.strip():
            raise ValueError("Teacher API key is missing")
        if not base_url.strip():
            raise ValueError("Teacher base URL must be non-empty")
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_retries = max_retries
        self.require_json_schema = require_json_schema
        if native_schema_mode not in {None, "json_schema", "json_object"}:
            raise ValueError("native_schema_mode must be json_schema or json_object")
        if native_schema_mode is not None:
            self.native_schema_mode = native_schema_mode
        self.timeout_seconds = timeout_seconds
        self.provider_name = provider_name or type(self).provider_name
        self._transport = transport or HttpxTeacherTransport()
        self._rate_limiter = rate_limiter or SlidingWindowRateLimiter(requests_per_minute)
        self._budget = budget or DailyBudget(
            daily_budget_usd,
            input_per_million_usd=input_cost_per_million_usd,
            output_per_million_usd=output_cost_per_million_usd,
        )

    def generate_structured(
        self,
        prompt: str,
        schema: Mapping[str, Any],
        *,
        system_prompt: str | None = None,
        schema_name: str = "teacher_output",
    ) -> TeacherResult:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("Teacher prompt must be non-empty")
        jsonschema.validators.validator_for(schema).check_schema(schema)
        request_prompt = prompt
        if self.require_json_schema and self.native_schema_mode == "json_object":
            # json_object only constrains syntax. Providers that do not accept
            # OpenAI's strict json_schema wire format still need the complete
            # contract in-context before we enforce it locally.
            request_prompt += "\n\nOUTPUT_JSON_SCHEMA:\n" + json.dumps(
                schema, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": request_prompt})
        estimated_prompt_tokens = max(1, len(request_prompt) // 4)
        estimated_cost = self._budget.estimate(estimated_prompt_tokens, self.max_tokens)

        last_error: TeacherError | None = None
        for _attempt in range(self.max_retries + 1):
            self._budget.authorize(estimated_cost)
            self._rate_limiter.acquire()
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
                "response_format": self._response_format(schema_name, schema),
            }
            try:
                body = self._transport.request(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    payload=payload,
                    timeout=self.timeout_seconds,
                )
                return self._parse_and_validate(body, schema)
            except (TeacherError, KeyError, TypeError, json.JSONDecodeError) as exc:
                last_error = exc if isinstance(exc, TeacherError) else TeacherError(
                    "Teacher response format was invalid"
                )
        assert last_error is not None
        raise last_error

    def probe_model(self) -> None:
        try:
            body = self._transport.request(
                "GET",
                f"{self.base_url}/models",
                headers=self._headers(),
                payload=None,
                timeout=self.timeout_seconds,
            )
            models = body.get("data", [])
            identifiers = {
                item.get("id") for item in models if isinstance(item, Mapping)
            }
            if self.model not in identifiers:
                raise ModelProbeError(
                    f"Configured Teacher model is unavailable: provider={self.provider_name}, "
                    f"model={self.model}"
                )
        except ModelProbeError:
            raise
        except Exception as exc:
            raise ModelProbeError(
                f"Teacher model probe failed: provider={self.provider_name}, model={self.model}"
            ) from exc

    def _response_format(
        self, schema_name: str, schema: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        if not self.require_json_schema or self.native_schema_mode == "json_object":
            return {"type": "json_object"}
        return {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "strict": True, "schema": dict(schema)},
        }

    def _headers(self) -> Mapping[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _parse_and_validate(
        self, body: Mapping[str, Any], schema: Mapping[str, Any]
    ) -> TeacherResult:
        try:
            content = body["choices"][0]["message"]["content"]
            if isinstance(content, str):
                data = json.loads(content)
            elif isinstance(content, Mapping):
                data = dict(content)
            else:
                raise TypeError("content is not JSON")
            jsonschema.validate(data, schema)
        except jsonschema.ValidationError as exc:
            instance_keys = sorted(exc.instance) if isinstance(exc.instance, Mapping) else []
            raise TeacherSchemaError(
                "Teacher output failed JSON Schema validation "
                f"(validator={exc.validator}, path={list(exc.path)}, keys={instance_keys})"
            ) from exc
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise TeacherSchemaError("Teacher output was not a valid JSON object") from exc

        usage_data = body.get("usage", {})
        if not isinstance(usage_data, Mapping):
            usage_data = {}
        usage = TeacherUsage(
            prompt_tokens=int(usage_data.get("prompt_tokens", 0) or 0),
            completion_tokens=int(usage_data.get("completion_tokens", 0) or 0),
            total_tokens=int(usage_data.get("total_tokens", 0) or 0),
        )
        cost = self._budget.estimate(usage.prompt_tokens, usage.completion_tokens)
        self._budget.record(cost)
        canonical = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        response_hash = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return TeacherResult(
            data=data,
            provider=self.provider_name,
            model=str(body.get("model") or self.model),
            usage=usage,
            raw_response_hash=response_hash,
            cost_usd=cost,
        )


__all__ = [
    "BaseTeacherLLM",
    "BudgetExceededError",
    "DailyBudget",
    "HttpxTeacherTransport",
    "ModelProbeError",
    "OpenAICompatibleTeacherLLM",
    "SlidingWindowRateLimiter",
    "TeacherError",
    "TeacherResult",
    "TeacherSchemaError",
    "TeacherTransport",
    "TeacherUsage",
]
