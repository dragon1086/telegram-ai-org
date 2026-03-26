"""Gemini CLI 실행 래퍼 — OAuth 기반 서브프로세스 (gemini -p '...' --output-format json)."""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from loguru import logger

from tools.base_runner import BaseRunner, RunContext, RunnerError, RunnerTimeoutError

GEMINI_CLI = os.environ.get("GEMINI_CLI_PATH", "gemini")
DEFAULT_TIMEOUT = int(os.environ.get("GEMINI_CLI_DEFAULT_TIMEOUT_SEC", "1800"))
GEMINI_FALLBACK_MODEL = os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-2.5-flash")

# Gemini CLI가 stdout에 출력하는 노이즈 라인 (소문자 비교)
_NOISE_LINE_PREFIXES = (
    "loaded cached credentials",
    "loaded credentials",
    "warning:",
)


def _sanitize_output(text: str) -> str:
    """Gemini CLI stdout에서 노이즈 라인을 제거하고 실제 응답만 반환."""
    lines = []
    for line in text.splitlines():
        low = line.lower().strip()
        if any(low.startswith(prefix) for prefix in _NOISE_LINE_PREFIXES):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _extract_json_block(text: str) -> str:
    """첫 번째 '{' 위치부터 JSON 블록을 추출한다."""
    start = text.find("{")
    if start == -1:
        return text
    return text[start:]


class GeminiCLIRunner(BaseRunner):
    """Gemini CLI subprocess 기반 러너.

    gemini -p '<prompt>' --output-format json 을 호출하고,
    JSON 응답의 'response' 필드를 반환한다.
    OAuth 인증 토큰(~/.gemini/oauth_creds.json)을 자동 사용하므로
    GEMINI_API_KEY / GOOGLE_API_KEY 는 subprocess 환경에서 제거된다.
    """

    def __init__(self, **kwargs: Any) -> None:
        self.cli_path = GEMINI_CLI
        self.timeout = DEFAULT_TIMEOUT
        self._last_metrics: dict[str, int | str] = {}

    async def run(self, ctx: RunContext) -> str:
        """프롬프트를 실행하고 결과 텍스트를 반환한다.

        Preview 모델 실패 시 GEMINI_FALLBACK_MODEL(기본값: gemini-2.5-flash GA)로 자동 재시도한다.
        """
        model = (ctx.engine_config or {}).get("model")

        try:
            return await self._run_with_model(ctx, model)
        except RunnerError as exc:
            # Preview 모델이 지정된 경우에만 폴백 시도
            fallback = GEMINI_FALLBACK_MODEL
            if model and model != fallback:
                logger.warning(
                    f"[FALLBACK] Preview 모델 실패 → {fallback}(GA) 로 전환 "
                    f"(원인: {exc})"
                )
                return await self._run_with_model(ctx, fallback)
            raise

    async def _run_with_model(self, ctx: RunContext, model: str | None) -> str:
        """지정된 모델로 Gemini CLI를 실행하고 결과 텍스트를 반환한다."""
        cmd = [self.cli_path, "-p", ctx.prompt, "--output-format", "json"]
        if model:
            cmd += ["--model", model]

        # API 키 환경변수 제거 → OAuth 강제 사용 (codex_runner.py 동일 패턴)
        clean_env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("GEMINI_API_KEY", "GOOGLE_API_KEY")
        }

        workdir = ctx.workdir or os.getcwd()
        model_label = model or "(기본)"
        logger.debug(
            f"[GeminiCLI] 실행: 프롬프트 {len(ctx.prompt)}자, model={model_label}, cwd={workdir}"
        )

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=workdir,
                env=clean_env,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=self.timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                raise RunnerTimeoutError(
                    f"Gemini CLI 타임아웃 ({self.timeout}초)"
                )

            if proc.returncode != 0:
                err = stderr.decode(errors="replace").strip()
                raise RunnerError(f"Gemini CLI 오류 (code={proc.returncode}): {err[:500]}")

            raw = stdout.decode(errors="replace")
            cleaned = _sanitize_output(raw)
            json_text = _extract_json_block(cleaned)

            try:
                data = json.loads(json_text)
                # data.get("response", "") 은 null JSON 값이면 None 반환 → or "" 로 보정
                response: str = data.get("response") or ""

                # 토큰 메트릭 추출
                total_tokens = 0
                for m_stats in data.get("stats", {}).get("models", {}).values():
                    total_tokens += m_stats.get("tokens", {}).get("total", 0)

                self._last_metrics = {
                    "output_chars": len(response),
                    "total_tokens": total_tokens,
                    "usage_source": "gemini_cli_json",
                }
                return response or "(결과 없음)"

            except json.JSONDecodeError:
                # --output-format json 파싱 실패 시 plain text 폴백
                logger.warning("[GeminiCLI] JSON 파싱 실패, plain text 반환")
                self._last_metrics = {
                    "output_chars": len(cleaned),
                    "usage_source": "gemini_cli_plain",
                }
                return cleaned or "(결과 없음)"

        except RunnerTimeoutError:
            raise
        except FileNotFoundError:
            raise RunnerError(f"Gemini CLI 없음: {self.cli_path!r} — npm install -g @google/gemini-cli 로 설치하세요")
        except RunnerError:
            raise
        except Exception as exc:
            raise RunnerError(f"GeminiCLIRunner 예외: {exc}") from exc

    def get_last_metrics(self) -> dict:
        """마지막 실행의 메트릭을 반환한다."""
        return self._last_metrics

    def capabilities(self) -> set[str]:
        """지원 기능 목록."""
        return set()
