"""Kimi Teacher provider."""

from src.training.teacher.base_teacher import OpenAICompatibleTeacherLLM


class KimiTeacherLLM(OpenAICompatibleTeacherLLM):
    provider_name = "kimi"
    DEFAULT_BASE_URL = "https://api.moonshot.ai/v1"


__all__ = ["KimiTeacherLLM"]
