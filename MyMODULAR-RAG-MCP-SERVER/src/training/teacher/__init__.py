"""Independent Teacher providers for offline Self-RAG dataset construction."""

from src.training.teacher.base_teacher import (
    BaseTeacherLLM,
    BudgetExceededError,
    ModelProbeError,
    OpenAICompatibleTeacherLLM,
    TeacherError,
    TeacherResult,
    TeacherSchemaError,
    TeacherUsage,
)
from src.training.teacher.deepseek_teacher import DeepSeekTeacherLLM
from src.training.teacher.fake_teacher import FakeTeacherLLM
from src.training.teacher.kimi_teacher import KimiTeacherLLM
from src.training.teacher.labeler import LabelingOutcome, QuarantinedLabeling, ReflectionLabeler
from src.training.teacher.query_teacher import StructuredQueryTeacher
from src.training.teacher.teacher_factory import FallbackTeacherLLM, TeacherFactory

__all__ = [
    "BaseTeacherLLM",
    "BudgetExceededError",
    "DeepSeekTeacherLLM",
    "FakeTeacherLLM",
    "FallbackTeacherLLM",
    "KimiTeacherLLM",
    "LabelingOutcome",
    "ModelProbeError",
    "OpenAICompatibleTeacherLLM",
    "QuarantinedLabeling",
    "ReflectionLabeler",
    "TeacherError",
    "TeacherFactory",
    "TeacherResult",
    "TeacherSchemaError",
    "StructuredQueryTeacher",
    "TeacherUsage",
]
