"""Gemini runner implementation using the google-genai SDK."""

from __future__ import annotations

import logging
import os
from typing import Any

from tools.base_runner import BaseRunner, RunContext, RunnerAuthError

logger = logging.getLogger(__name__)

try:
    import google.genai as genai
    from google.genai import types
    _GENAI_AVAILABLE = True
except ImportError:
    genai = None  # type: ignore[assignment]
    types = None  # type: ignore[assignment]
    _GENAI_AVAILABLE = False


class GeminiRunner(BaseRunner):
    """Runner for Google Gemini models via the google-genai SDK."""

    def __init__(self, **kwargs: Any) -> None:
        self._api_key = (
            os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        )
        self._client = None
        self._last_metrics: dict = {}

        if self._api_key and _GENAI_AVAILABLE:
            self._client = genai.Client(api_key=self._api_key)

    async def run(self, ctx: RunContext) -> str:
        """Execute a prompt and return the result."""
        if not self._api_key:
            raise RunnerAuthError("GOOGLE_API_KEY or GEMINI_API_KEY not set")

        if not _GENAI_AVAILABLE:
            raise ImportError(
                "google-genai package is not installed. "
                "Run: pip install google-genai"
            )

        model = ctx.engine_config.get("model", "gemini-2.5-flash")

        if ctx.progress_callback:
            # Streaming variant
            result_chunks: list[str] = []
            async for chunk in await self._client.aio.models.generate_content_stream(
                model=model,
                contents=ctx.prompt,
            ):
                if chunk.text:
                    result_chunks.append(chunk.text)
                    try:
                        await ctx.progress_callback(chunk.text)
                    except TypeError:
                        ctx.progress_callback(chunk.text)
            text = "".join(result_chunks)
            self._last_metrics = {}
            return text
        else:
            response = await self._client.aio.models.generate_content(
                model=model,
                contents=ctx.prompt,
            )
            text = response.text or ""
            self._last_metrics = {}
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                meta = response.usage_metadata
                self._last_metrics = {
                    "prompt_token_count": getattr(meta, "prompt_token_count", None),
                    "candidates_token_count": getattr(meta, "candidates_token_count", None),
                }
            return text

    async def run_single(self, ctx: RunContext) -> str:
        """Execute a single prompt, passing system_prompt via GenerateContentConfig."""
        if not self._api_key:
            raise RunnerAuthError("GOOGLE_API_KEY or GEMINI_API_KEY not set")

        if not _GENAI_AVAILABLE:
            raise ImportError(
                "google-genai package is not installed. "
                "Run: pip install google-genai"
            )

        if ctx.system_prompt:
            model = ctx.engine_config.get("model", "gemini-2.5-flash")
            config = types.GenerateContentConfig(
                system_instruction=ctx.system_prompt,
            )
            response = await self._client.aio.models.generate_content(
                model=model,
                contents=ctx.prompt,
                config=config,
            )
            text = response.text or ""
            self._last_metrics = {}
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                meta = response.usage_metadata
                self._last_metrics = {
                    "prompt_token_count": getattr(meta, "prompt_token_count", None),
                    "candidates_token_count": getattr(meta, "candidates_token_count", None),
                }
            return text

        return await self.run(ctx)

    async def run_task(self, ctx: RunContext) -> str:
        """Execute with system_prompt prepended to prompt."""
        if ctx.system_prompt:
            combined = RunContext(
                prompt=f"{ctx.system_prompt}\n\n{ctx.prompt}",
                workdir=ctx.workdir,
                progress_callback=ctx.progress_callback,
                session_id=ctx.session_id,
                persona=ctx.persona,
                session_store=ctx.session_store,
                org_id=ctx.org_id,
                global_context=ctx.global_context,
                engine_config=ctx.engine_config,
            )
            return await self.run(combined)
        return await self.run(ctx)

    def get_last_metrics(self) -> dict:
        """Return token counts from the last execution."""
        return self._last_metrics

    def capabilities(self) -> set[str]:
        """Return supported capabilities."""
        return {"streaming"}
