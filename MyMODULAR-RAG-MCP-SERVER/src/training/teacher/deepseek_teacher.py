"""DeepSeek Teacher provider with provider-specific JSON-object mode."""

from src.training.teacher.base_teacher import OpenAICompatibleTeacherLLM


class DeepSeekTeacherLLM(OpenAICompatibleTeacherLLM):
    provider_name = "deepseek"
    DEFAULT_BASE_URL = "https://api.deepseek.com"
    # DeepSeek-compatible deployments do not all expose OpenAI strict schema;
    # outputs are still validated locally against the complete JSON Schema.
    native_schema_mode = "json_object"


__all__ = ["DeepSeekTeacherLLM"]
