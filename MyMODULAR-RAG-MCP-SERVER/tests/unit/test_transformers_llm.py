"""Unit contract for the lazy local Transformers provider."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import torch

from src.core.settings import load_settings
from src.libs.llm.base_llm import Message
from src.libs.llm.transformers_llm import TransformersLLM


class FakeEncoding(dict):
    pass


class FakeTokenizer:
    def __init__(self) -> None:
        self.template_kwargs = None

    def apply_chat_template(self, messages, **kwargs):
        self.template_kwargs = {"messages": messages, **kwargs}
        return FakeEncoding(input_ids=torch.tensor([[1, 2, 3]]))

    def decode(self, token_ids, skip_special_tokens=True):
        assert skip_special_tokens is True
        assert token_ids.tolist() == [7, 8]
        return "本地回答"


class FakeModel:
    device = torch.device("cpu")

    def generate(self, **kwargs):
        assert kwargs["do_sample"] is False
        assert kwargs["max_new_tokens"] == 12
        return torch.tensor([[1, 2, 3, 7, 8]])


def fake_settings() -> SimpleNamespace:
    return SimpleNamespace(
        llm=SimpleNamespace(
            provider="transformers_local",
            model="artifacts/models/Qwen3-4B",
            temperature=0.0,
            max_tokens=12,
            load_in_4bit=True,
            local_files_only=True,
            device_map="auto",
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            compute_dtype="bfloat16",
            enable_thinking=False,
        )
    )


def test_injected_local_model_generates_without_loading_or_network() -> None:
    tokenizer = FakeTokenizer()
    llm = TransformersLLM(fake_settings(), model=FakeModel(), tokenizer=tokenizer)

    response = llm.chat([Message(role="user", content="你好")])

    assert response.content == "本地回答"
    assert response.model == "artifacts/models/Qwen3-4B"
    assert response.usage == {
        "prompt_tokens": 3,
        "completion_tokens": 2,
        "total_tokens": 5,
    }
    assert tokenizer.template_kwargs["enable_thinking"] is False


def test_local_profile_selects_qwen_fallbacks_and_no_policy_tokens() -> None:
    settings = load_settings("config/settings.selfrag.local.yaml")

    assert settings.llm.provider == "transformers_local"
    assert settings.llm.load_in_4bit is True
    assert settings.llm.local_files_only is True
    assert settings.embedding.model == "qwen3.7-text-embedding"
    assert settings.vision_llm.model == "qwen3.5-ocr"
    assert settings.rerank.provider == "cross_encoder"
    assert settings.rerank.model.endswith("bge-reranker-v2-m3")
    raw = open("config/settings.selfrag.local.yaml", encoding="utf-8").read().lower()
    assert "<retry" not in raw
    assert "<abstain" not in raw


def test_max_tokens_must_be_positive() -> None:
    llm = TransformersLLM(fake_settings(), model=FakeModel(), tokenizer=FakeTokenizer())
    with pytest.raises(ValueError, match="positive"):
        llm.chat([Message(role="user", content="你好")], max_tokens=0)
