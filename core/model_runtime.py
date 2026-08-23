from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RuntimeBackendSpec:
    key: str
    label: str
    local: bool
    supports_text: bool
    supports_vision: bool
    available: bool
    note: str = ""


BACKEND_SPECS = {
    "mlx": RuntimeBackendSpec(
        key="mlx",
        label="MLX / Apple Silicon",
        local=True,
        supports_text=True,
        supports_vision=True,
        available=True,
        note="현재 구현된 로컬 백엔드입니다. 모델 config에 따라 LM/VLM을 자동 판별합니다.",
    ),
    "openai": RuntimeBackendSpec(
        key="openai",
        label="OpenAI 호환 API",
        local=False,
        supports_text=True,
        supports_vision=True,
        available=True,
        note="원격 API 백엔드입니다. OpenAI API, llama.cpp 서버 등 OpenAI 호환 /v1/chat/completions 엔드포인트를 지원합니다.",
    ),
}


class ModelRuntime:
    """Common capability wrapper for local/API model backends."""

    backend_key = "unknown"
    display_name = "Unknown Runtime"

    def __init__(self, model: Any = None, processor: Any = None, model_id: str = ""):
        self.model = model
        self.processor = processor
        self.model_id = model_id

    @property
    def supports_text(self) -> bool:
        return True

    @property
    def supports_vision(self) -> bool:
        return False

    @property
    def family(self) -> str:
        return "text"

    def unwrap(self) -> tuple[Any, Any]:
        return self.model, self.processor


class MlxRuntime(ModelRuntime):
    backend_key = "mlx"
    display_name = "MLX"

    @property
    def supports_vision(self) -> bool:
        return hasattr(self.processor, "image_processor")

    @property
    def family(self) -> str:
        config = getattr(self.model, "config", None)
        model_type = str(getattr(config, "model_type", "") or "").lower()
        archs = [str(a).lower() for a in (getattr(config, "architectures", []) or [])]
        template = str(getattr(self.processor, "chat_template", "") or "")
        tokenizer = getattr(self.processor, "tokenizer", None)
        template += str(getattr(tokenizer, "chat_template", "") or "")

        if "qwen" in model_type or any("qwen" in a for a in archs) or "qwen" in template.lower():
            return "qwen"
        if "gemma" in model_type or any("gemma" in a for a in archs) or "gemma" in template.lower():
            return "gemma"
        if self.supports_vision:
            return "vlm"
        return "text"


class ApiRuntime(ModelRuntime):
    backend_key = "api"
    display_name = "API"

    def __init__(self, model: Any, model_id: str = "", supports_vision: bool = False):
        super().__init__(model=model, processor=None, model_id=model_id)
        self._supports_vision = supports_vision

    @property
    def supports_vision(self) -> bool:
        return self._supports_vision

    @property
    def family(self) -> str:
        return "api"


class OpenAICompatRuntime(ApiRuntime):
    backend_key = "openai"
    display_name = "OpenAI 호환 API"


def wrap_model_runtime(
    model: Any,
    processor: Any = None,
    backend_key: str | None = None,
    model_id: str = "",
    supports_vision: bool | None = None,
) -> ModelRuntime:
    if isinstance(model, ModelRuntime):
        return model

    backend = backend_key or detect_backend_key(model, processor)
    if backend == "openai":
        return OpenAICompatRuntime(
            model=model,
            model_id=model_id,
            supports_vision=bool(supports_vision if supports_vision is not None else getattr(model, "supports_vision", False)),
        )
    if backend == "mlx":
        return MlxRuntime(model=model, processor=processor, model_id=model_id)
    return ModelRuntime(model=model, processor=processor, model_id=model_id)


def detect_backend_key(model: Any, processor: Any = None) -> str:
    try:
        from core.openai_compat import OpenAICompatClient

        if isinstance(model, OpenAICompatClient):
            return "openai"
    except ImportError:
        pass

    if processor is not None:
        return "mlx"
    return "unknown"


def model_supports_vision(model: Any, processor: Any = None) -> bool:
    runtime = wrap_model_runtime(model, processor)
    return runtime.supports_vision
