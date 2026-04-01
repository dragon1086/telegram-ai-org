"""PM 오케스트레이션 판단 전용 엔진 클라이언트."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from loguru import logger

from core.eval_context import inject_eval_context
from core.orchestration_config import load_orchestration_config
from core.pm_identity import PMIdentity
from core.session_store import SessionStore


class DecisionClientProtocol(Protocol):
    async def complete(
        self,
        prompt: str,
        *,
        system_prompt: str = "",
        workdir: str | None = None,
    ) -> str: ...


def _resolve_engine(org_id: str, engine: str) -> str:
    if engine in {"claude-code", "codex", "gemini", "gemini-cli"}:
        return engine
    try:
        org = load_orchestration_config().get_org(org_id)
    except Exception:
        org = None
    if org and org.preferred_engine in {"claude-code", "codex", "gemini", "gemini-cli"}:
        return org.preferred_engine
    return "claude-code"


def _resolve_fallback_engine(org_id: str) -> str | None:
    """organizations.yaml의 fallback_engine 반환. 없거나 preferred와 같으면 None."""
    try:
        org = load_orchestration_config().get_org(org_id)
    except Exception:
        return "gemini-cli"
    if not org:
        return "gemini-cli"
    fallback = org.fallback_engine
    if fallback and fallback != org.preferred_engine:
        return fallback
    return "gemini-cli"


class PMDecisionClient:
    """PM의 configured engine으로 짧은 판단 태스크를 수행한다."""

    def __init__(
        self,
        org_id: str,
        *,
        engine: str = "auto",
        session_store: SessionStore | None = None,
        default_workdir: str | None = None,
    ) -> None:
        self.org_id = org_id
        self.engine = _resolve_engine(org_id, engine)
        self._session_store = session_store
        self._default_workdir = default_workdir or str(Path(__file__).resolve().parent.parent)
        self._runner = None

    def _base_system_prompt(self) -> str:
        identity = PMIdentity(self.org_id)
        data = identity.load()
        role = data.get("role", "") or "총괄 PM"
        specialties = ", ".join(data.get("specialties", []) or []) or "없음"
        direction = data.get("direction", "") or "조직 정체성에 맞게 판단"
        base = (
            "당신은 사용자를 대신해 실행하는 PM의 내부 판단 엔진이다.\n"
            "이 호출에서는 실제 작업을 수행하지 말고, 요청된 분류/계획/판단만 하라.\n"
            "반드시 요청된 형식만 출력하고 군더더기 설명을 추가하지 마라.\n\n"
            f"조직: {self.org_id}\n"
            f"역할: {role}\n"
            f"전문 분야: {specialties}\n"
            f"방향성: {direction}"
        )
        # 평가 컨텍스트 주입 — ENABLE_EVAL_CONTEXT=1/EVAL_ALWAYS=1 설정 시 항상 포함
        eval_notice = inject_eval_context()
        if eval_notice:
            base = f"{eval_notice}\n\n{base}"
        return base

    def _get_runner(self):
        if self._runner is not None:
            return self._runner
        from tools.base_runner import RunnerFactory
        self._runner = RunnerFactory.create(self.engine)
        return self._runner

    async def complete(
        self,
        prompt: str,
        *,
        system_prompt: str = "",
        workdir: str | None = None,
    ) -> str:
        resolved_workdir = workdir or self._default_workdir
        combined_system = self._base_system_prompt()
        if system_prompt:
            combined_system = f"{combined_system}\n\n{system_prompt}"

        from tools.base_runner import RunContext, RunnerError

        try:
            return await self._execute(
                self._get_runner(), self.engine,
                prompt, combined_system, resolved_workdir,
            )
        except (RunnerError, RuntimeError) as primary_err:
            err_msg = str(primary_err).lower()
            is_rate_limit = any(k in err_msg for k in (
                "hit your limit", "rate limit", "quota", "overloaded",
            ))
            if not is_rate_limit:
                raise

            fallback_engine = _resolve_fallback_engine(self.org_id)
            if not fallback_engine or fallback_engine == self.engine:
                raise

            logger.warning(
                f"[PMDecisionClient] {self.engine} rate limit → "
                f"fallback to {fallback_engine}: {primary_err}"
            )
            from tools.base_runner import RunnerFactory
            fallback_runner = RunnerFactory.create(fallback_engine)
            return await self._execute(
                fallback_runner, fallback_engine,
                prompt, combined_system, resolved_workdir,
            )

    async def _execute(
        self, runner, engine: str,
        prompt: str, system_prompt: str, workdir: str,
    ) -> str:
        from tools.base_runner import RunContext

        if engine == "codex":
            full_prompt = f"{system_prompt}\n\n{prompt}"
            return await runner.run(RunContext(
                prompt=full_prompt,
                workdir=workdir,
            ))

        return await runner.run_single(RunContext(
            prompt=prompt,
            system_prompt=system_prompt,
            org_id=self.org_id,
            session_store=self._session_store,
            global_context=None,
            workdir=workdir,
        ))
