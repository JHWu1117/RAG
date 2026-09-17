"""Local Hugging Face Transformers LLM with optional bitsandbytes 4-bit loading."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from src.core.settings import resolve_path
from src.libs.llm.base_llm import BaseLLM, ChatResponse, Message


class TransformersLLMError(RuntimeError):
    """Raised when local model loading or inference fails."""


class TransformersLLM(BaseLLM):
    """Lazy local Transformers provider suitable for an 8GB consumer GPU."""

    _DTYPES = {"float16": "float16", "bfloat16": "bfloat16", "float32": "float32"}

    def __init__(
        self,
        settings: Any,
        *,
        model: Any | None = None,
        tokenizer: Any | None = None,
        **kwargs: Any,
    ) -> None:
        self.model_name = settings.llm.model
        model_path = Path(self.model_name)
        self.model_path = str(resolve_path(model_path)) if not model_path.is_absolute() else str(model_path)
        self.default_temperature = settings.llm.temperature
        self.default_max_tokens = settings.llm.max_tokens
        self.load_in_4bit = bool(getattr(settings.llm, "load_in_4bit", False))
        self.local_files_only = bool(getattr(settings.llm, "local_files_only", True))
        self.device_map = getattr(settings.llm, "device_map", "auto")
        self.quant_type = getattr(settings.llm, "bnb_4bit_quant_type", "nf4")
        self.use_double_quant = bool(
            getattr(settings.llm, "bnb_4bit_use_double_quant", True)
        )
        self.compute_dtype = getattr(settings.llm, "compute_dtype", "bfloat16")
        self.enable_thinking = bool(getattr(settings.llm, "enable_thinking", False))
        self._model = model
        self._tokenizer = tokenizer
        self._lock = threading.RLock()
        self._extra_config = kwargs

    def _ensure_loaded(self) -> None:
        if self._model is not None and self._tokenizer is not None:
            return
        with self._lock:
            if self._model is not None and self._tokenizer is not None:
                return
            try:
                import torch
                from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

                if self.compute_dtype not in self._DTYPES:
                    raise ValueError(
                        f"Unsupported compute_dtype {self.compute_dtype!r}; "
                        f"choose from {sorted(self._DTYPES)}"
                    )
                if self.local_files_only and not Path(self.model_path).is_dir():
                    raise FileNotFoundError(f"Local model directory not found: {self.model_path}")
                load_kwargs: dict[str, Any] = {
                    "device_map": self.device_map,
                    "local_files_only": self.local_files_only,
                    "low_cpu_mem_usage": True,
                }
                if self.load_in_4bit:
                    load_kwargs["quantization_config"] = BitsAndBytesConfig(
                        load_in_4bit=True,
                        bnb_4bit_quant_type=self.quant_type,
                        bnb_4bit_use_double_quant=self.use_double_quant,
                        bnb_4bit_compute_dtype=getattr(torch, self._DTYPES[self.compute_dtype]),
                    )
                self._tokenizer = AutoTokenizer.from_pretrained(
                    self.model_path, local_files_only=self.local_files_only
                )
                self._model = AutoModelForCausalLM.from_pretrained(
                    self.model_path, **load_kwargs
                )
                self._model.eval()
            except Exception as exc:
                raise TransformersLLMError(
                    f"Failed to load local Transformers model {self.model_name!r}: "
                    f"{type(exc).__name__}: {exc}"
                ) from exc

    def chat(
        self,
        messages: list[Message],
        trace: Any | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        del trace
        self.validate_messages(messages)
        self._ensure_loaded()
        temperature = float(kwargs.get("temperature", self.default_temperature))
        max_tokens = int(kwargs.get("max_tokens", self.default_max_tokens))
        if max_tokens < 1:
            raise ValueError("max_tokens must be positive")
        assert self._model is not None and self._tokenizer is not None
        try:
            import torch

            rendered = [{"role": item.role, "content": item.content} for item in messages]
            encoded = self._tokenizer.apply_chat_template(
                rendered,
                tokenize=True,
                add_generation_prompt=True,
                enable_thinking=self.enable_thinking,
                return_dict=True,
                return_tensors="pt",
            )
            device = self._model.device
            encoded = {name: tensor.to(device) for name, tensor in encoded.items()}
            generation: dict[str, Any] = {
                "max_new_tokens": max_tokens,
                "do_sample": temperature > 0,
            }
            if temperature > 0:
                generation["temperature"] = temperature
            with self._lock, torch.inference_mode():
                output = self._model.generate(**encoded, **generation)
            prompt_tokens = int(encoded["input_ids"].shape[-1])
            generated_ids = output[0, prompt_tokens:]
            content = self._tokenizer.decode(generated_ids, skip_special_tokens=True)
            completion_tokens = int(generated_ids.shape[-1])
            return ChatResponse(
                content=content,
                model=self.model_name,
                usage={
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                },
            )
        except TransformersLLMError:
            raise
        except Exception as exc:
            raise TransformersLLMError(
                f"Local Transformers generation failed ({type(exc).__name__}: {exc})"
            ) from exc


__all__ = ["TransformersLLM", "TransformersLLMError"]
