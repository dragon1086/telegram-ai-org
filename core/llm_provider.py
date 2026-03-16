"""LLM Provider 추상화 레이어.

환경변수 자동 감지로 사용 가능한 첫 번째 provider를 반환.
우선순위: GEMINI → OPENAI → ANTHROPIC → DEEPSEEK → OLLAMA(자동감지)
"""
from __future__ import annotations

import asyncio
import json
import os
from abc import ABC, abstractmethod

from loguru import logger


class LLMProvider(ABC):
    """단일 인터페이스 — prompt → response text."""

    @abstractmethod
    async def complete(self, prompt: str, timeout: float = 10.0) -> str:
        """프롬프트 → 응답 텍스트 반환."""


# ──────────────────────────────────────────────
# Gemini
# ──────────────────────────────────────────────

class GeminiProvider(LLMProvider):
    """google-genai 패키지 또는 REST API로 Gemini 호출."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def complete(self, prompt: str, timeout: float = 10.0) -> str:
        loop = asyncio.get_event_loop()

        def _run() -> str:
            try:
                from google import genai  # type: ignore
                client = genai.Client(api_key=self._api_key)
                resp = client.models.generate_content(
                    model="gemini-3-flash-preview",
                    contents=prompt,
                )
                return resp.text.strip()
            except ImportError:
                pass

            # fallback: httpx REST
            import urllib.request
            url = (
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"gemini-3-flash-preview:generateContent?key={self._api_key}"
            )
            body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode()
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read())
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()

        return await asyncio.wait_for(loop.run_in_executor(None, _run), timeout=timeout)

    def __repr__(self) -> str:
        return "GeminiProvider(gemini-3-flash-preview)"


# ──────────────────────────────────────────────
# OpenAI
# ──────────────────────────────────────────────

class OpenAIProvider(LLMProvider):
    """openai 패키지 또는 REST API로 OpenAI 호출."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def complete(self, prompt: str, timeout: float = 10.0) -> str:
        loop = asyncio.get_event_loop()

        def _run() -> str:
            try:
                import openai  # type: ignore
                client = openai.OpenAI(api_key=self._api_key)
                resp = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=64,
                )
                return resp.choices[0].message.content.strip()
            except ImportError:
                pass

            import urllib.request
            url = "https://api.openai.com/v1/chat/completions"
            body = json.dumps({
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 64,
            }).encode()
            req = urllib.request.Request(url, data=body, headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            })
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read())
            return data["choices"][0]["message"]["content"].strip()

        return await asyncio.wait_for(loop.run_in_executor(None, _run), timeout=timeout)

    def __repr__(self) -> str:
        return "OpenAIProvider(gpt-4o-mini)"


# ──────────────────────────────────────────────
# Anthropic
# ──────────────────────────────────────────────

class AnthropicProvider(LLMProvider):
    """Anthropic REST API 직접 호출 (CLI 아님, rate limit 독립)."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def complete(self, prompt: str, timeout: float = 10.0) -> str:
        loop = asyncio.get_event_loop()

        def _run() -> str:
            try:
                import anthropic  # type: ignore
                if self._api_key.startswith("sk-ant-oat"):
                    client = anthropic.Anthropic(
                        auth_token=self._api_key,
                        base_url="https://api.anthropic.com",
                    )
                else:
                    client = anthropic.Anthropic(api_key=self._api_key)
                msg = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=64,
                    messages=[{"role": "user", "content": prompt}],
                )
                return msg.content[0].text.strip()
            except ImportError:
                pass

            import urllib.request
            url = "https://api.anthropic.com/v1/messages"
            body = json.dumps({
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 64,
                "messages": [{"role": "user", "content": prompt}],
            }).encode()
            # OAuth 토큰(oat01)은 Bearer, 일반 API 키는 x-api-key
            if self._api_key.startswith("sk-ant-oat"):
                auth_headers = {"Authorization": f"Bearer {self._api_key}"}
            else:
                auth_headers = {"x-api-key": self._api_key}
            req = urllib.request.Request(url, data=body, headers={
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01",
                **auth_headers,
            })
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read())
            return data["content"][0]["text"].strip()

        return await asyncio.wait_for(loop.run_in_executor(None, _run), timeout=timeout)

    def __repr__(self) -> str:
        return "AnthropicProvider(claude-haiku-4-5)"


# ──────────────────────────────────────────────
# DeepSeek
# ──────────────────────────────────────────────

class DeepSeekProvider(LLMProvider):
    """DeepSeek REST API (OpenAI 호환 엔드포인트)."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def complete(self, prompt: str, timeout: float = 10.0) -> str:
        loop = asyncio.get_event_loop()

        def _run() -> str:
            import urllib.request
            url = "https://api.deepseek.com/v1/chat/completions"
            body = json.dumps({
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 64,
            }).encode()
            req = urllib.request.Request(url, data=body, headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            })
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read())
            return data["choices"][0]["message"]["content"].strip()

        return await asyncio.wait_for(loop.run_in_executor(None, _run), timeout=timeout)

    def __repr__(self) -> str:
        return "DeepSeekProvider(deepseek-chat)"


# ──────────────────────────────────────────────
# Ollama (로컬)
# ──────────────────────────────────────────────

class OllamaProvider(LLMProvider):
    """로컬 Ollama REST API. API key 불필요."""

    def __init__(self, host: str = "http://localhost:11434", model: str = "llama3") -> None:
        self._host = host.rstrip("/")
        self._model = model

    async def complete(self, prompt: str, timeout: float = 10.0) -> str:
        loop = asyncio.get_event_loop()

        def _run() -> str:
            import urllib.request
            url = f"{self._host}/api/generate"
            body = json.dumps({
                "model": self._model,
                "prompt": prompt,
                "stream": False,
            }).encode()
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read())
            return data["response"].strip()

        return await asyncio.wait_for(loop.run_in_executor(None, _run), timeout=timeout)

    def __repr__(self) -> str:
        return f"OllamaProvider({self._host}, model={self._model})"


# ──────────────────────────────────────────────
# 자동 감지
# ──────────────────────────────────────────────

_cached_provider: LLMProvider | None | bool = False  # False = 미초기화


def _probe_ollama(host: str) -> bool:
    """Ollama가 실제로 응답하는지 확인."""
    import urllib.request
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=2):
            return True
    except Exception:
        return False


def get_provider() -> LLMProvider | None:
    """환경변수 자동 감지 → 첫 번째 사용 가능 provider 반환. 없으면 None.

    결과는 모듈 수준에서 캐싱 (매 호출마다 재생성 금지).
    """
    global _cached_provider
    if _cached_provider is not False:
        return _cached_provider  # type: ignore[return-value]

    provider: LLMProvider | None = None

    # 1. Gemini
    key = os.environ.get("GEMINI_API_KEY", "")
    if key:
        logger.debug("[llm_provider] GeminiProvider 선택")
        provider = GeminiProvider(key)

    # 2. OpenAI
    if provider is None:
        key = os.environ.get("OPENAI_API_KEY", "")
        if key:
            logger.debug("[llm_provider] OpenAIProvider 선택")
            provider = OpenAIProvider(key)

    # 3. Anthropic (API 키 또는 OAuth 토큰 자동 선택)
    if provider is None:
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            # Claude Code OAuth 토큰으로 fallback
            oauth = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "")
            if not oauth:
                try:
                    oauth = (Path.home() / ".claude" / "oauth-token").read_text().strip()
                except Exception:
                    pass
            if oauth:
                key = oauth
                logger.debug("[llm_provider] AnthropicProvider (OAuth 토큰 사용)")
        if key:
            logger.debug("[llm_provider] AnthropicProvider 선택")
            provider = AnthropicProvider(key)

    # 4. DeepSeek
    if provider is None:
        key = os.environ.get("DEEPSEEK_API_KEY", "")
        if key:
            logger.debug("[llm_provider] DeepSeekProvider 선택")
            provider = DeepSeekProvider(key)

    # 5. Ollama (로컬 자동 감지)
    if provider is None:
        host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        if _probe_ollama(host):
            model = os.environ.get("OLLAMA_MODEL", "llama3")
            logger.debug(f"[llm_provider] OllamaProvider 선택 ({host})")
            provider = OllamaProvider(host, model)

    if provider is None:
        logger.debug("[llm_provider] 사용 가능한 provider 없음 → keyword fallback 사용")

    _cached_provider = provider
    return provider
