from typing import Any

import pytest
from markettwin_execution_orchestrator.models import model_factory
from markettwin_execution_orchestrator.models.model_factory import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_OLLAMA_API_BASE,
    DEFAULT_OLLAMA_MODEL_NAME,
    DEFAULT_OLLAMA_NUM_CTX,
    create_model,
)


def test_create_model_uses_safe_local_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def capture_model(model: str, **kwargs: Any) -> object:
        captured.update(model=model, **kwargs)
        return object()

    monkeypatch.delenv("OLLAMA_MODEL_NAME", raising=False)
    monkeypatch.delenv("OLLAMA_API_BASE", raising=False)
    monkeypatch.delenv("MARKETTWIN_OLLAMA_NUM_CTX", raising=False)
    monkeypatch.setattr(model_factory, "LiteLlm", capture_model)

    create_model()

    assert captured == {
        "model": DEFAULT_OLLAMA_MODEL_NAME,
        "api_base": DEFAULT_OLLAMA_API_BASE,
        "max_tokens": DEFAULT_MAX_TOKENS,
        "num_ctx": DEFAULT_OLLAMA_NUM_CTX,
        "reasoning_effort": "none",
    }


def test_create_model_accepts_local_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def capture_model(model: str, **kwargs: Any) -> object:
        captured.update(model=model, **kwargs)
        return object()

    monkeypatch.setenv("OLLAMA_MODEL_NAME", "ollama_chat/test-model")
    monkeypatch.setenv("OLLAMA_API_BASE", "http://127.0.0.1:12345")
    monkeypatch.setenv("MARKETTWIN_OLLAMA_NUM_CTX", "4096")
    monkeypatch.setattr(model_factory, "LiteLlm", capture_model)

    create_model()

    assert captured["model"] == "ollama_chat/test-model"
    assert captured["api_base"] == "http://127.0.0.1:12345"
    assert captured["num_ctx"] == 4096
