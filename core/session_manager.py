"""tmux 세션 매니저 — 팀별 persistent 세션 관리.

세션 이름 규칙: aiorg_{team_id}
예: aiorg_dev, aiorg_marketing
"""
from __future__ import annotations

import asyncio
import os
import re
import subprocess
from pathlib import Path

from loguru import logger

SESSION_PREFIX = "aiorg"
OUTPUT_TIMEOUT = 30  # 응답 대기 최대 초

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

    def ensure_session(self, team_id: str) -> str:
        """세션이 없으면 생성 + claude 시작. 세션 이름 반환."""
        name = self.session_name(team_id)
        if not self.session_exists(team_id):
            self._run_tmux("new-session", "-d", "-s", name)
            # claude CLI를 대화형으로 시작
            claude_cli = os.environ.get("CLAUDE_CLI_PATH", "/Users/rocky/.local/bin/claude")
            self._run_tmux("send-keys", "-t", name,
                           f"{claude_cli} --dangerously-skip-permissions", "Enter")
            import time; time.sleep(2)  # claude 초기화 대기
            logger.info(f"tmux 세션 생성 + claude 시작: {name}")
        else:
            logger.debug(f"tmux 세션 재사용: {name}")
        return name

    def list_sessions(self) -> list[str]:
        """aiorg_ 접두어 세션 목록 반환."""
        out = self._run_tmux("list-sessions", "-F", "#{session_name}")
        if not out:
            return []
        return [s for s in out.splitlines() if s.startswith(SESSION_PREFIX + "_")]

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

    async def _wait_for_output(self, output_file: Path) -> str:
        """출력 파일에 __DONE__ 마커 나타날 때까지 대기."""
        while True:
            await asyncio.sleep(0.5)
            if output_file.exists():
                content = output_file.read_text(encoding="utf-8")
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

    def _extract_new_content(self, before: str, after: str) -> str:
        """before → after 사이에 새로 추가된 내용 추출."""
        before_lines = before.splitlines()
        after_lines = after.splitlines()

        # before의 마지막 줄부터 after에서 새로운 부분 찾기
        if before_lines:
            last_before = before_lines[-1]
            try:
                idx = after_lines.index(last_before)
                new_lines = after_lines[idx + 1:]
            except ValueError:
                new_lines = after_lines
        else:
            new_lines = after_lines

        # 프롬프트 라인 제거 (claude 프롬프트 기호)
        cleaned = [l for l in new_lines if not l.strip().startswith(("❯", ">", "$"))]
        return "\n".join(cleaned).strip()

    async def _wait_for_response(self, session_name: str, before: str) -> str:
        """출력이 안정화될 때까지 대기 (응답 완료 감지)."""
        prev_content = before
        stable_count = 0
        STABLE_THRESHOLD = 3  # 3회 연속 동일하면 완료로 판단

        await asyncio.sleep(1.0)  # 초기 대기

        while True:
            await asyncio.sleep(0.8)
            current = self._capture_pane(session_name)

            if current == prev_content:
                stable_count += 1
                if stable_count >= STABLE_THRESHOLD:
                    # 출력 안정화 → 완료
                    return self._extract_new_content(before, current)
            else:
                stable_count = 0
                prev_content = current

    async def send_message(self, team_id: str, message: str) -> str:
        """tmux 세션의 claude에 메시지 전달 후 응답 수집.

        흐름:
        1. 현재 pane 내용을 스냅샷으로 저장
        2. tmux send-keys로 메시지 입력
        3. claude 응답 완료까지 대기 (출력 안정화 감지)
        4. 새로 추가된 텍스트 반환
        """
        name = self.ensure_session(team_id)

        # 1. 전송 전 스냅샷
        before = self._capture_pane(name)

        # 2. 메시지 전송
        escaped = message.replace("'", "'\\''")
        self._run_tmux("send-keys", "-t", name, message, "Enter")

        # 3. 응답 완료 대기
        try:
            response = await asyncio.wait_for(
                self._wait_for_response(name, before),
                timeout=OUTPUT_TIMEOUT,
            )
            return response
        except asyncio.TimeoutError:
            logger.warning(f"응답 타임아웃: {name}")
            current = self._capture_pane(name)
            return self._extract_new_content(before, current)

    async def maybe_compact(self, team_id: str, message_count: int = 0) -> bool:
        """컨텍스트 80% 초과 감지 시 /compact 실행. 실행 여부 반환.

        감지 방법:
        1. message_count >= 50 이면 compact 트리거
        2. pane 출력에서 'context' + '%' 패턴 탐색
        """
        name = self.session_name(team_id)
        if not self.session_exists(team_id):
            return False

        should_compact = False

        # 메시지 수 기반
        if message_count >= 50:
            should_compact = True
        else:
            # pane 출력에서 컨텍스트 사용량 감지
            pane = self._capture_pane(name)
            m = re.search(r"(\d+)%\s*(?:context|컨텍스트)", pane, re.IGNORECASE)
            if m and int(m.group(1)) >= 80:
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
