"""tmux 세션 매니저 — 팀별 persistent 세션 관리.

세션 이름 규칙: aiorg_{team_id}
예: aiorg_dev, aiorg_marketing
"""
from __future__ import annotations

import asyncio
import os
import re
import shlex
import subprocess
from collections.abc import Awaitable, Callable
from pathlib import Path

from loguru import logger

SESSION_PREFIX = "aiorg"
OUTPUT_TIMEOUT = 120  # 응답 대기 최대 초
PROMPT_TIMEOUT = 15   # claude 초기화 대기 최대 초

# TUI 아티팩트 제거 패턴
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[mGKHFA-Za-z]")
_BOX_RE = re.compile(r"[╭╮╰╯│─┤├┬┴┼▸▹●○◆◇▲△▼▽►◄╔╗╚╝═║]+")
_OMC_BAR_RE = re.compile(r"\[OMC#.*?\].*")
_PROMPT_RE = re.compile(r"\s*[❯>$]\s*$", re.MULTILINE)

WRITEBACK_PROMPT = """\
지금까지 대화에서 중요한 결정, 사실, 합의사항을 3-10개 추출해서
다음 형식으로만 응답해:
MEMORY_WRITEBACK:
- [중요도1-10] 내용
- [중요도1-10] 내용
"""


class SessionManager:
    """tmux 세션 생성/확인/재시작."""

    def session_name(self, team_id: str) -> str:
        return f"{SESSION_PREFIX}_{team_id}"

    def shell_session_name(self, team_id: str, purpose: str = "exec") -> str:
        return f"{SESSION_PREFIX}_{team_id}_{purpose}"

    # ── tmux 헬퍼 ─────────────────────────────────────────────────────────

    def _run_tmux(self, *args: str) -> str:
        """tmux 명령 실행. stdout 반환. 실패 시 빈 문자열."""
        try:
            result = subprocess.run(
                ["tmux", *args],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return (result.stdout + result.stderr).strip()
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
            logger.debug(f"tmux 명령 실패 ({args}): {e}")
            return ""

    def _tmux_available(self) -> bool:
        return bool(self._run_tmux("-V"))

    # ── 세션 관리 ─────────────────────────────────────────────────────────

    def session_exists(self, team_id: str) -> bool:
        """세션이 존재하면 True."""
        name = self.session_name(team_id)
        out = self._run_tmux("has-session", "-t", name)
        return not out  # has-session은 성공 시 출력 없음, 실패 시 에러 출력

    def ensure_session(self, team_id: str, disable_omc: bool = False) -> str:
        """세션이 없으면 생성 + claude 시작. 세션 이름 반환."""
        name = self.session_name(team_id)
        if not self.session_exists(team_id):
            self._run_tmux("new-session", "-d", "-s", name, "-x", "220", "-y", "50")
            claude_cli = os.environ.get("CLAUDE_CLI_PATH", "/Users/rocky/.local/bin/claude")
            env_prefix = "CLAUDECODE= "
            if disable_omc:
                env_prefix += "DISABLE_OMC=1 "
            self._run_tmux("send-keys", "-t", name,
                           f"{env_prefix}{claude_cli} --dangerously-skip-permissions", "Enter")
            # 프롬프트 나올 때까지 폴링 (sleep 고정 제거)
            ready = self._wait_for_prompt(name, timeout=PROMPT_TIMEOUT)
            if ready:
                logger.info(f"tmux 세션 생성 완료: {name}")
            else:
                logger.warning(f"tmux 세션 프롬프트 타임아웃: {name}")
        else:
            logger.debug(f"tmux 세션 재사용: {name}")
        return name

    def _wait_for_prompt(self, session_name: str, timeout: float = PROMPT_TIMEOUT) -> bool:
        """claude 프롬프트(❯ 또는 >) 나올 때까지 폴링 대기."""
        import time
        start = time.time()
        while time.time() - start < timeout:
            pane = self._run_tmux("capture-pane", "-t", session_name, "-p")
            if "❯" in pane or ("> " in pane and "dangerously" in pane.lower()):
                return True
            # bypass permissions 안내 화면도 준비 완료 신호
            if "bypass" in pane.lower() and ("permission" in pane.lower() or "skip" in pane.lower()):
                return True
            time.sleep(0.5)
        return False

    def list_sessions(self) -> list[str]:
        """aiorg_ 접두어 세션 목록 반환."""
        out = self._run_tmux("list-sessions", "-F", "#{session_name}")
        if not out:
            return []
        return [s for s in out.splitlines() if s.startswith(SESSION_PREFIX + "_")]

    def ensure_shell_session(self, team_id: str, purpose: str = "exec") -> str:
        """일반 쉘 명령 실행용 tmux 세션을 준비한다."""
        if not self._tmux_available():
            raise RuntimeError("tmux unavailable")
        name = self.shell_session_name(team_id, purpose)
        return self._ensure_shell_session_name(name)

    def _ensure_shell_session_name(self, name: str, *, reset: bool = False) -> str:
        if reset:
            self._run_tmux("kill-session", "-t", name)
        out = self._run_tmux("has-session", "-t", name)
        exists = not out
        if not exists:
            self._run_tmux("new-session", "-d", "-s", name, "-x", "220", "-y", "50")
            logger.info(f"tmux shell 세션 생성 완료: {name}")
        return name

    async def run_shell_command(
        self,
        team_id: str,
        command: str,
        *,
        purpose: str = "exec",
        timeout: float | None = None,
        progress_callback: Callable[[str], Awaitable[None]] | None = None,
    ) -> tuple[str, int]:
        """tmux shell 세션에서 명령을 실행하고 stdout/stderr를 수집한다."""
        if not self._tmux_available():
            raise RuntimeError("tmux unavailable")
        name = self._ensure_shell_session_name(self.shell_session_name(team_id, purpose), reset=True)
        output_file = Path.home() / ".ai-org" / "sessions" / f"{name}.out"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text("", encoding="utf-8")

        command_body = (
            f"({command}) > {shlex.quote(str(output_file))} 2>&1; "
            "status=$?; "
            f"printf '\\n__EXIT_CODE__:%s\\n__DONE__\\n' \"$status\" >> {shlex.quote(str(output_file))}"
        )
        shell_cmd = f"bash -lc {shlex.quote(command_body)}"
        self._run_tmux("send-keys", "-t", name, shell_cmd, "Enter")

        try:
            content = await asyncio.wait_for(
                self._wait_for_output(output_file, progress_callback=progress_callback),
                timeout=timeout or OUTPUT_TIMEOUT,
            )
        except asyncio.TimeoutError:
            self._run_tmux("kill-session", "-t", name)
            raise
        exit_code = 0
        m = re.search(r"__EXIT_CODE__:(\d+)", content)
        if m:
            exit_code = int(m.group(1))
            content = re.sub(r"\n?__EXIT_CODE__:\d+\s*", "", content).strip()
        return content, exit_code

    def kill_session(self, team_id: str) -> None:
        """세션 종료."""
        name = self.session_name(team_id)
        if self.session_exists(team_id):
            self._run_tmux("kill-session", "-t", name)
            logger.info(f"tmux 세션 종료: {name}")

    # ── 명령 전송 ─────────────────────────────────────────────────────────

    async def send_to_session(self, team_id: str, prompt: str) -> str:
        """세션에 프롬프트 전송 (비동기). 출력 캡처는 파일 리디렉션으로."""
        name = self.ensure_session(team_id)
        output_file = Path.home() / ".ai-org" / "sessions" / f"{name}.out"
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # 이전 출력 파일 초기화
        output_file.write_text("", encoding="utf-8")

        # 명령을 출력 캡처와 함께 전송
        escaped = prompt.replace("'", "'\\''")
        cmd = f"echo '{escaped}' >> {output_file} && echo '__DONE__' >> {output_file}"
        self._run_tmux("send-keys", "-t", name, cmd, "Enter")

        # __DONE__ 마커 대기
        try:
            return await asyncio.wait_for(
                self._wait_for_output(output_file),
                timeout=OUTPUT_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning(f"세션 응답 타임아웃: {name}")
            return output_file.read_text(encoding="utf-8") if output_file.exists() else ""

    async def _wait_for_output(
        self,
        output_file: Path,
        progress_callback: Callable[[str], Awaitable[None]] | None = None,
    ) -> str:
        """출력 파일에 __DONE__ 마커 나타날 때까지 대기."""
        last_size = 0
        while True:
            await asyncio.sleep(0.5)
            if output_file.exists():
                content = output_file.read_text(encoding="utf-8")
                if progress_callback and len(content) > last_size:
                    delta = content[last_size:]
                    last_size = len(content)
                    for line in delta.splitlines():
                        stripped = line.strip()
                        if not stripped or stripped.startswith("__EXIT_CODE__") or stripped == "__DONE__":
                            continue
                        try:
                            await progress_callback(stripped)
                        except Exception as cb_err:
                            logger.warning(f"shell progress_callback 오류: {cb_err}")
                if "__DONE__" in content:
                    return content.replace("__DONE__", "").strip()

    # ── 컨텍스트 재주입 재시작 ────────────────────────────────────────────

    async def restart_session(self, team_id: str, context: str) -> None:
        """세션 재시작 + 컨텍스트 재주입."""
        self.kill_session(team_id)
        name = self.ensure_session(team_id)

        if context:
            context_file = Path.home() / ".ai-org" / "sessions" / f"{name}_context.md"
            context_file.parent.mkdir(parents=True, exist_ok=True)
            context_file.write_text(context, encoding="utf-8")
            # 세션 시작 시 컨텍스트 파일 경로 환경변수로 설정
            self._run_tmux(
                "send-keys", "-t", name,
                f"export AI_ORG_CONTEXT={context_file}", "Enter",
            )
            logger.info(f"세션 재시작 + 컨텍스트 주입: {name}")

    # ── claude 통신 ───────────────────────────────────────────────────────

    def _capture_pane(self, session_name: str) -> str:
        """tmux pane 현재 내용 캡처."""
        return self._run_tmux("capture-pane", "-t", session_name, "-p", "-S", "-100")

    def _extract_response(self, current_pane: str, before_pane: str) -> str:
        """TUI 아티팩트 제거 + 실제 응답만 추출."""
        # before에 없는 새 라인만 추출
        before_set = set(before_pane.splitlines())
        new_lines = [l for l in current_pane.splitlines() if l not in before_set]
        text = "\n".join(new_lines)

        # ANSI 이스케이프 코드 제거
        text = _ANSI_RE.sub("", text)
        # 박스 문자 제거
        text = _BOX_RE.sub("", text)
        # OMC 상태바 라인 제거
        text = _OMC_BAR_RE.sub("", text)
        # 프롬프트 라인 제거
        text = _PROMPT_RE.sub("", text)
        # bypass permissions 안내 제거
        text = re.sub(r"bypass permissions.*", "", text, flags=re.IGNORECASE)
        # 연속 빈 줄 정리
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()

    # 하위 호환: 기존 코드에서 _extract_new_content 호출 가능하도록 유지
    def _extract_new_content(self, before: str, after: str) -> str:
        return self._extract_response(after, before)

    async def _wait_for_response(self, session_name: str, before: str) -> str:
        """프롬프트(❯) 재등장으로 완료 감지 + 안정화 확인."""
        last_content = ""
        stable_count = 0
        STABLE_THRESHOLD = 2

        await asyncio.sleep(1.0)

        while True:
            await asyncio.sleep(0.8)
            current = self._capture_pane(session_name)

            # 프롬프트가 다시 나타나면 응답 완료 신호
            prompt_ready = "❯" in current and current != before
            if prompt_ready:
                content = self._extract_response(current, before)
                if content == last_content:
                    stable_count += 1
                    if stable_count >= STABLE_THRESHOLD:
                        return content
                else:
                    last_content = content
                    stable_count = 0
            else:
                stable_count = 0
                last_content = ""

    async def send_message(self, team_id: str, message: str) -> str:
        """tmux 세션의 claude에 메시지 전달 후 응답 수집.

        흐름:
        1. claude 프롬프트 준비 확인
        2. 현재 pane 스냅샷 저장
        3. 메시지 전송 (긴 메시지는 tempfile 경유)
        4. 프롬프트 재등장까지 대기 후 TUI 아티팩트 제거된 텍스트 반환
        """
        name = self.ensure_session(team_id)

        # claude 준비 확인
        if not self._wait_for_prompt(name, timeout=5):
            logger.warning(f"claude 세션 준비 미완료: {name}")
            return "❌ claude 세션 준비 안됨"

        # 전송 전 스냅샷
        before = self._capture_pane(name)

        # 메시지 전송
        if len(message) > 200:
            import tempfile
            with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
                f.write(message)
                tmp = f.name
            self._run_tmux("send-keys", "-t", name, f"cat {tmp}", "Enter")
        else:
            self._run_tmux("send-keys", "-t", name, message, "Enter")

        # 응답 완료 대기
        try:
            response = await asyncio.wait_for(
                self._wait_for_response(name, before),
                timeout=OUTPUT_TIMEOUT,
            )
            return response
        except asyncio.TimeoutError:
            logger.warning(f"응답 타임아웃: {name}")
            current = self._capture_pane(name)
            return self._extract_response(current, before)

    async def maybe_compact(self, team_id: str, message_count: int = 0) -> bool:
        """컨텍스트 70% 초과 감지 시 /compact 실행. 실행 여부 반환.

        감지 방법:
        1. message_count >= 35 이면 compact 트리거
        2. pane 출력에서 'context' + '%' 패턴 탐색

        세션 탐색 순서: claude-agent-team → 기본 세션
        """
        # claude-agent-team 세션 우선 시도 (Codex/Claude Code 공용 세션)
        agent_team_name = self.shell_session_name(team_id, "claude-agent-team")
        if self._run_tmux("has-session", "-t", agent_team_name).strip() == "":
            name = agent_team_name
        else:
            name = self.session_name(team_id)
            if not self.session_exists(team_id):
                return False

        should_compact = False

        # 메시지 수 기반
        if message_count >= 35:
            should_compact = True
        else:
            # pane 출력에서 컨텍스트 사용량 감지
            pane = self._capture_pane(name)
            m = re.search(r"(\d+)%\s*(?:context|컨텍스트)", pane, re.IGNORECASE)
            if m and int(m.group(1)) >= 70:
                should_compact = True

        if should_compact:
            logger.info(f"[{team_id}] /compact 실행 (message_count={message_count})")
            self._run_tmux("send-keys", "-t", name, "/compact", "Enter")
            await asyncio.sleep(3)  # compact 완료 대기
            return True

        return False

    async def writeback_and_reset(self, team_id: str, memory_mgr) -> None:
        """세션 한계 도달 시:
        1. WRITEBACK_PROMPT 전송 → 응답 파싱 → memory 저장
        2. 세션 종료
        3. 새 세션 생성 + 메모리 컨텍스트 주입
        """
        logger.info(f"[{team_id}] writeback 시작")

        # 1. WRITEBACK_PROMPT 전송
        try:
            response = await self.send_message(team_id, WRITEBACK_PROMPT)
        except Exception as e:
            logger.warning(f"writeback 응답 실패: {e}")
            response = ""

        # 2. 응답 파싱
        if "MEMORY_WRITEBACK:" in response:
            lines = response.split("MEMORY_WRITEBACK:", 1)[1].strip().splitlines()
            for line in lines:
                line = line.strip()
                if not line.startswith("- "):
                    continue
                item = line[2:].strip()
                # [중요도] 파싱
                m = re.match(r"\[(\d+)\]\s*(.*)", item)
                if m:
                    importance = int(m.group(1))
                    content = m.group(2).strip()
                    if importance >= 9:
                        memory_mgr.add_core(content)
                    else:
                        await memory_mgr.add_log(content)
                    logger.debug(f"writeback 저장 [{importance}]: {content[:60]}")

        # 3. 세션 종료
        self.kill_session(team_id)
        await asyncio.sleep(1)

        # 4. 새 세션 + 메모리 컨텍스트 주입
        context = memory_mgr.build_context()
        name = self.ensure_session(team_id)
        if context:
            self.inject_context(team_id, context)

        logger.info(f"[{team_id}] 세션 리셋 완료")

    def inject_context(self, team_id: str, context: str) -> None:
        """새 세션 시작 시 메모리 컨텍스트를 claude에 주입."""
        name = self.session_name(team_id)
        if not context:
            return

        # 컨텍스트를 파일로 저장 후 claude에 전달
        context_file = Path.home() / ".ai-org" / "sessions" / f"{name}_context.md"
        context_file.parent.mkdir(parents=True, exist_ok=True)
        context_file.write_text(context, encoding="utf-8")

        intro = f"다음은 이전 대화의 중요 컨텍스트입니다. 참고해서 대화를 이어가세요:\n\n{context}"
        # 짧으면 직접 전송, 길면 파일 참조
        if len(intro) < 500:
            self._run_tmux("send-keys", "-t", name, intro, "Enter")
        else:
            msg = f"컨텍스트 파일을 읽어 참고하세요: {context_file}"
            self._run_tmux("send-keys", "-t", name, msg, "Enter")

        logger.info(f"컨텍스트 주입 완료: {name} ({len(context)}글자)")

    # ── 상태 요약 ─────────────────────────────────────────────────────────

    def status(self) -> dict:
        """활성 세션 상태 요약."""
        if not self._tmux_available():
            return {"tmux": False, "sessions": []}
        sessions = self.list_sessions()
        return {
            "tmux": True,
            "sessions": sessions,
            "count": len(sessions),
        }
