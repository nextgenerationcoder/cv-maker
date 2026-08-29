"""LLM abstraction used by both the job-scoring feature and the CV
tailoring pipeline. A user can configure their own provider + API key on
the Settings page; if they haven't, calls fall back to this server's own
ANTHROPIC_API_KEY (the original behavior). Swapping in a new provider
means adding a class here — callers only ever see the LLMProvider
interface.
"""
import json
import logging
import os
from typing import Optional, Type, TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

import settings_store

logger = logging.getLogger("cv_maker.llm_provider")

T = TypeVar("T", bound=BaseModel)

ANTHROPIC_MODEL = os.environ.get("TAILOR_LLM_MODEL", "claude-opus-5")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")


class LLMUsage(BaseModel):
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0


class LLMProvider:
    """Interface: implementations must provide structured_call() and
    identify themselves via provider_name/model_name (used in generation
    metadata so the UI/logs show which provider actually ran a call)."""

    provider_name: str = "unknown"
    model_name: str = "unknown"

    def structured_call(
        self,
        *,
        system_blocks: list[dict],
        content_blocks: list[dict],
        output_model: Type[T],
        max_tokens: int = 8000,
    ) -> tuple[T, LLMUsage]:
        raise NotImplementedError


def _blocks_to_text(blocks: list[dict]) -> str:
    return "\n\n".join(b["text"] for b in blocks if b.get("text"))


class AnthropicProvider(LLMProvider):
    provider_name = "anthropic"

    def __init__(self, api_key: Optional[str] = None, model: str = ANTHROPIC_MODEL) -> None:
        self.model_name = model
        # None => SDK resolves ANTHROPIC_API_KEY from the environment, same as before.
        self._client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    def structured_call(
        self,
        *,
        system_blocks: list[dict],
        content_blocks: list[dict],
        output_model: Type[T],
        max_tokens: int = 8000,
    ) -> tuple[T, LLMUsage]:
        response = self._client.messages.parse(
            model=self.model_name,
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


class DeepSeekProvider(LLMProvider):
    """DeepSeek's API is OpenAI-compatible (per their own docs: use the
    `openai` SDK with base_url pointed at DeepSeek) — this is not an
    OpenAI integration, just SDK reuse for an OpenAI-shaped API. DeepSeek
    doesn't offer Anthropic-style enforced JSON-schema structured output,
    so we ask for JSON mode + a hand-written schema in the prompt, then
    validate server-side and retry once on a malformed/invalid response.
    """

    provider_name = "deepseek"

    def __init__(self, api_key: str, model: str = DEEPSEEK_MODEL) -> None:
        from openai import OpenAI

        self.model_name = model
        self._client = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)

    def structured_call(
        self,
        *,
        system_blocks: list[dict],
        content_blocks: list[dict],
        output_model: Type[T],
        max_tokens: int = 8000,
    ) -> tuple[T, LLMUsage]:
        system_text = _blocks_to_text(system_blocks)
        user_text = _blocks_to_text(content_blocks)
        schema_text = json.dumps(output_model.model_json_schema())

        messages = [
            {
                "role": "system",
                "content": system_text
                + "\n\nRespond with ONLY a single JSON object matching this JSON Schema exactly "
                "— no prose, no markdown fences:\n" + schema_text,
            },
            {"role": "user", "content": user_text},
        ]

        last_error: Optional[Exception] = None
        for attempt in range(2):
            response = self._client.chat.completions.create(
                model=self.model_name,
                max_tokens=max_tokens,
                messages=messages,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content or ""
            try:
                parsed = output_model.model_validate_json(raw)
                usage_obj = response.usage
                cached = getattr(usage_obj, "prompt_cache_hit_tokens", 0) or 0
                usage = LLMUsage(
                    input_tokens=getattr(usage_obj, "prompt_tokens", 0) or 0,
                    cached_input_tokens=cached,
                    output_tokens=getattr(usage_obj, "completion_tokens", 0) or 0,
                )
                return parsed, usage
            except (ValidationError, ValueError) as exc:
                last_error = exc
                logger.warning("DeepSeek returned invalid structured output (attempt %d): %s", attempt + 1, exc)
                messages.append({"role": "assistant", "content": raw})
                messages.append(
                    {
                        "role": "user",
                        "content": f"That response was invalid JSON for the required schema ({exc}). "
                        "Return corrected JSON only, matching the schema exactly.",
                    }
                )

        raise ValueError(f"DeepSeek returned invalid structured output after retry: {last_error}")


def get_provider_for_user(user_id: str) -> LLMProvider:
    settings = settings_store.get_settings(user_id)
    provider_name = settings["llm_provider"] if settings else "anthropic"
    api_key = settings_store.get_decrypted_api_key(user_id) if settings else None

    if provider_name == "deepseek":
        if not api_key:
            raise ValueError(
                "DeepSeek is selected in Settings but no API key is saved — add one on the Settings page."
            )
        return DeepSeekProvider(api_key=api_key)

    return AnthropicProvider(api_key=api_key)
