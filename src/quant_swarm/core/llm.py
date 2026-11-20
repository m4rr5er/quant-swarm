"""OpenAI-compatible LLM client + named profiles.

Profiles live in ``configs/settings.yaml -> llm.profiles.<name>``; the api key
is read from the env var named by ``api_key_env`` — never from the yaml itself.
Works with DeepSeek / Qwen / GLM / Moonshot / OpenAI / Ollama / any gateway.
"""

from __future__ import annotations

import json
import os
from typing import TypeVar

from loguru import logger
from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from quant_swarm.core.config import LLMProfile

T = TypeVar("T", bound=BaseModel)


class LLMConfigError(RuntimeError):
    pass


class LLMParseError(RuntimeError):
    pass


def _extract_json(text: str) -> str:
    """Tolerate ```json fences and prose around the payload."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1]
        if t.startswith("json"):
            t = t[4:]
        t = t.rsplit("```", 1)[0].strip()
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end <= start:
        raise LLMParseError("no JSON object found in LLM output")
    return t[start : end + 1]


class LLMClient:
    def __init__(self, profile: LLMProfile, *, api_key: str | None = None) -> None:
        key = api_key or os.environ.get(profile.api_key_env, "")
        if not key:
            raise LLMConfigError(
                f"no api key for profile (model={profile.model!r}): set env {profile.api_key_env}"
            )
        self.profile = profile
        self.last_usage: dict | None = None
        self._client = AsyncOpenAI(
            base_url=profile.base_url, api_key=key, timeout=profile.timeout_sec
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def _create(self, messages: list[dict], **kw):
        params = {
            "model": self.profile.model,
            "messages": messages,
            "temperature": self.profile.temperature,
            **self.profile.extra,
            **kw,
        }
        if self.profile.max_tokens is not None:
            params.setdefault("max_tokens", self.profile.max_tokens)
        resp = await self._client.chat.completions.create(**params)
        self.last_usage = resp.usage.model_dump() if resp.usage else None
        logger.debug("llm {} usage={}", self.profile.model, self.last_usage)
        return resp

    async def chat(self, messages: list[dict], **kw) -> str:
        resp = await self._create(messages, **kw)
        return resp.choices[0].message.content or ""

    async def chat_structured(
        self,
        messages: list[dict],
        model: type[T],
        *,
        retries: int = 1,
        **kw,
    ) -> T:
        """Ask for JSON, validate into ``model``, auto-repair once on failure.

        Uses ``json_object`` mode (broadly supported) rather than
        ``json_schema`` (not portable across providers yet).
        """
        kw.setdefault("response_format", {"type": "json_object"})
        history = list(messages)
        last_err: Exception | None = None
        for _ in range(1 + retries):
            content = await self.chat(history, **kw)
            try:
                return model.model_validate(json.loads(_extract_json(content)))
            except (ValidationError, json.JSONDecodeError, LLMParseError) as e:
                last_err = e
                history = [
                    *messages,
                    {"role": "assistant", "content": content},
                    {
                        "role": "user",
                        "content": (
                            "Output was not valid for the required schema. "
                            f"Reply with ONLY the corrected JSON object. Error: {e}"
                        ),
                    },
                ]
        raise LLMParseError(f"structured output failed validation: {last_err}")
