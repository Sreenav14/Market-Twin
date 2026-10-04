"""LLM model configuration for the MarketTwin execution orchestrator."""

import os
from dataclasses import dataclass
from typing import Final

from google.adk.models.lite_llm import LiteLlm
from markettwin_shared.model_parameters import completion_parameters

DEFAULT_MODEL_PROVIDER: Final[str] = "openai"
DEFAULT_OPENAI_MODEL_NAME: Final[str] = "openai/gpt-4o-mini"
DEFAULT_OPENAI_NUM_RETRIES: Final[int] = 2

DEFAULT_OLLAMA_MODEL_NAME: Final[str] = "ollama_chat/qwen3:1.7b"
DEFAULT_OLLAMA_API_BASE: Final[str] = "http://localhost:11434"
DEFAULT_OLLAMA_NUM_CTX: Final[int] = 8_192

DEFAULT_MAX_TOKENS: Final[int] = 512


@dataclass(frozen=True, slots=True)
class ModelRuntimeConfiguration:
    """Safe semantic model configuration used by MarketTwin."""

    provider: str
    model_name: str
    max_tokens: int
    num_retries: int | None = None
    num_ctx: int | None = None
    reasoning_effort: str | None = None

    def snapshot_parameters(self) -> dict[str, object]:
        """Return safe model parameters suitable for runtime snapshots."""

        parameters: dict[str, object] = {
            "max_tokens": self.max_tokens,
        }

        if self.num_retries is not None:
            parameters["num_retries"] = self.num_retries

        if self.num_ctx is not None:
            parameters["num_ctx"] = self.num_ctx

        if self.reasoning_effort is not None:
            parameters["reasoning_effort"] = (
                self.reasoning_effort
            )

        return parameters


def resolve_model_runtime_configuration(
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> ModelRuntimeConfiguration:
    """Resolve the safe semantic configuration for the active model."""

    provider = os.getenv(
        "MODEL_PROVIDER",
        DEFAULT_MODEL_PROVIDER,
    ).strip().casefold() or DEFAULT_MODEL_PROVIDER

    configured_model = (os.getenv("MODEL_NAME") or "").strip()
    if "/" in configured_model and not (provider == "ollama" and os.getenv("OLLAMA_MODEL_NAME")):
        provider = configured_model.split("/", 1)[0]
        if provider == "ollama_chat":
            provider = "ollama"

    if provider == "openai":
        model_name = (
            os.getenv("MODEL_NAME")
            or DEFAULT_OPENAI_MODEL_NAME
        ).strip()

        if not model_name.startswith("openai/"):
            model_name = f"openai/{model_name}"

        return ModelRuntimeConfiguration(
            provider="openai",
            model_name=model_name,
            max_tokens=max_tokens,
            num_retries=DEFAULT_OPENAI_NUM_RETRIES,
            reasoning_effort=(os.getenv("MODEL_REASONING_EFFORT") or "").strip() or None,
        )

    if provider == "ollama":
        model_name = os.getenv(
            "OLLAMA_MODEL_NAME",
            os.getenv(
                "MODEL_NAME",
                DEFAULT_OLLAMA_MODEL_NAME,
            ),
        )

        num_ctx = int(
            os.getenv(
                "MARKETTWIN_OLLAMA_NUM_CTX",
                DEFAULT_OLLAMA_NUM_CTX,
            )
        )

        return ModelRuntimeConfiguration(
            provider="ollama",
            model_name=model_name,
            max_tokens=max_tokens,
            num_ctx=num_ctx,
            reasoning_effort="none",
        )

    if configured_model:
        model_name = (
            configured_model if "/" in configured_model else f"{provider}/{configured_model}"
        )
        return ModelRuntimeConfiguration(
            provider=provider, model_name=model_name, max_tokens=max_tokens,
            num_retries=DEFAULT_OPENAI_NUM_RETRIES,
        )
    raise ValueError(f'MODEL_NAME is required for MODEL_PROVIDER "{provider}".')


def create_model(
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> LiteLlm:
    """Create the configured LLM used by MarketTwin agents."""

    configuration = resolve_model_runtime_configuration(
        max_tokens=max_tokens,
    )

    if configuration.provider == "openai":
        if configuration.num_retries is None:
            raise RuntimeError(
                "OpenAI model configuration requires num_retries."
            )

        api_key = (
            os.getenv("MODEL_API_KEY")
            or os.getenv("OPENAI_API_KEY")
        )

        if api_key:
            return LiteLlm(
                model=configuration.model_name,
                api_key=api_key,
                **completion_parameters(configuration.model_name, configuration.max_tokens),
                num_retries=configuration.num_retries,
            )

        return LiteLlm(
            model=configuration.model_name,
            **completion_parameters(configuration.model_name, configuration.max_tokens),
            num_retries=configuration.num_retries,
        )

    if configuration.provider == "ollama":
        if configuration.num_ctx is None:
            raise RuntimeError(
                "Ollama model configuration requires num_ctx."
            )

        if configuration.reasoning_effort is None:
            raise RuntimeError(
                "Ollama model configuration requires reasoning_effort."
            )

        api_base = os.getenv(
            "OLLAMA_API_BASE",
            DEFAULT_OLLAMA_API_BASE,
        )

        return LiteLlm(
            model=configuration.model_name,
            api_base=api_base,
            max_tokens=configuration.max_tokens,
            num_ctx=configuration.num_ctx,
            reasoning_effort=configuration.reasoning_effort,
        )

    parameters = completion_parameters(configuration.model_name, configuration.max_tokens)
    api_key = os.getenv("MODEL_API_KEY")
    return LiteLlm(
        model=configuration.model_name, api_key=api_key,
        num_retries=configuration.num_retries, **parameters,
    )
