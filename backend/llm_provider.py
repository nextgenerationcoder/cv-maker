"""Thin abstraction over the LLM used for CV tailoring, so the business
logic in tailoring_llm_steps.py never touches an SDK directly. Swapping
providers later means adding a new class here, not touching the pipeline.
"""
import os
from typing import Optional, Type, TypeVar

import anthropic
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

TAILOR_MODEL = os.environ.get("TAILOR_LLM_MODEL", "claude-opus-5")


class LLMUsage(BaseModel):
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0


class LLMProvider:
    """Interface: implementations must provide structured_call()."""

    def structured_call(
        self,
        *,
        system_blocks: list[dict],
        content_blocks: list[dict],
        output_model: Type[T],
        max_tokens: int = 8000,
    ) -> tuple[T, LLMUsage]:
        raise NotImplementedError


class AnthropicProvider(LLMProvider):
    def __init__(self) -> None:
        self._client: Optional[anthropic.Anthropic] = None

    def _get_client(self) -> anthropic.Anthropic:
        if self._client is None:
            self._client = anthropic.Anthropic()
        return self._client

    def structured_call(
        self,
        *,
        system_blocks: list[dict],
        content_blocks: list[dict],
        output_model: Type[T],
        max_tokens: int = 8000,
    ) -> tuple[T, LLMUsage]:
        response = self._get_client().messages.parse(
            model=TAILOR_MODEL,
            max_tokens=max_tokens,
            system=system_blocks,
            messages=[{"role": "user", "content": content_blocks}],
            output_format=output_model,
        )
        usage = response.usage
        return response.parsed_output, LLMUsage(
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            cached_input_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
        )


_provider: Optional[LLMProvider] = None


def get_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        _provider = AnthropicProvider()
    return _provider
