"""PM 오케스트레이션 판단 전용 엔진 클라이언트."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

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
    if engine in {"claude-code", "codex", "gemini"}:
        return engine
    try:
        org = load_orchestration_config().get_org(org_id)
    except Exception:
        org = None
    if org and org.preferred_engine in {"claude-code", "codex", "gemini"}:
        return org.preferred_engine
    return "claude-code"


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
        return (
            "당신은 사용자를 대신해 실행하는 PM의 내부 판단 엔진이다.\n"
            "이 호출에서는 실제 작업을 수행하지 말고, 요청된 분류/계획/판단만 하라.\n"
            "반드시 요청된 형식만 출력하고 군더더기 설명을 추가하지 마라.\n\n"
            f"조직: {self.org_id}\n"
            f"역할: {role}\n"
            f"전문 분야: {specialties}\n"
            f"방향성: {direction}"
        )

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
        runner = self._get_runner()
        resolved_workdir = workdir or self._default_workdir
        combined_system = self._base_system_prompt()
        if system_prompt:
            combined_system = f"{combined_system}\n\n{system_prompt}"

        from tools.base_runner import RunContext

        if self.engine == "codex":
            full_prompt = f"{combined_system}\n\n{prompt}"
            return await runner.run(RunContext(
                prompt=full_prompt,
                workdir=resolved_workdir,
            ))

        return await runner.run_single(RunContext(
            prompt=prompt,
            system_prompt=combined_system,
            org_id=self.org_id,
            session_store=self._session_store,
            global_context=None,
            workdir=resolved_workdir,
        ))
