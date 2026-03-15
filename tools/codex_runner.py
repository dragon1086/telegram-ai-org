"""Codex CLI 실행 래퍼 — 에이전트 프롬프트 주입 지원."""
from __future__ import annotations

import asyncio
import os
import re
import shlex
from pathlib import Path

from loguru import logger


CODEX_CLI = os.environ.get("CODEX_CLI_PATH", "codex")
DEFAULT_TIMEOUT = int(os.environ.get("CODEX_DEFAULT_TIMEOUT_SEC", "1800"))
COMPLEX_TASK_TIMEOUT = int(os.environ.get("CODEX_COMPLEX_TIMEOUT_SEC", "14400"))
AGENT_DIRS = [
    Path.home() / ".claude" / "agents",
    Path.home() / ".ai-org" / "agents",
]
_REPO_CUE_RE = re.compile(
    r"(repo|repository|directory|dir|path|folder|workspace|github\.com|git@|"
    r"리포|리파지토리|레포|저장소|디렉토리|폴더|경로|워크스페이스)",
    re.IGNORECASE,
)
_SECTION_HEADERS = {
    "thinking": "drop",
    "exec": "drop",
    "codex": "keep",
    "collab": "drop",
}
_DROP_LINE_PREFIXES = (
    "🌐 searching the web",
    "🌐 searched",
    "spawn_agent(",
    "wait(",
    "collab ",
    "receivers:",
    "pending init:",
    "agent:",
    "/bin/zsh -lc",
    "succeeded in",
    "plan update",
    "__exit_code__:",
    "__done__",
    "openai codex v",
    "workdir:",
    "model:",
    "provider:",
    "approval:",
    "sandbox:",
    "reasoning effort:",
    "reasoning summaries:",
    "session id:",
    "user",
    "[agent:",
    "--- name:",
)
_DROP_LINE_CONTAINS = (
    "## 협업 요청",
    "## 응답 언어",
    "## pm 배정 태스크",
    "## 팀 구성 원칙",
    "## 동료 팀",
    "→ 응답에 [collab:",
    "→ 위 팀이 더 적합한 업무가 있으면",
    "→ 태그는 한 번에 최대 1개",
    "→ 협업 결과는 채팅방에서 자동으로 전달됩니다",
    "⚠️ **무조건 응답 맨 첫 줄에 [team:",
)

# 키워드 → 에이전트 파일명 매핑 (agent_catalog._KEYWORD_MAP 기반)
_AGENT_KEYWORD_MAP: list[tuple[list[str], list[str]]] = [
    (
        ["implement", "build", "code", "develop", "refactor", "fix", "debug",
         "구현", "코딩", "개발", "수정", "버그", "빌드", "리팩토링"],
        ["executor.md", "debugger.md"],
    ),
    (
        ["analysis", "research", "data", "analyze", "compare",
         "분석", "리서치", "데이터", "비교", "조사"],
        ["analyst.md", "data-analytics-reporter.md"],
    ),
    (
        ["design", "ui", "ux", "layout", "prototype",
         "디자인", "프로토타입", "레이아웃"],
        ["designer.md", "design-brand-guardian.md"],
    ),
    (
        ["review", "audit", "security", "quality",
         "리뷰", "검토", "감사", "보안", "품질"],
        ["code-reviewer.md", "security-reviewer.md"],
    ),
    (
        ["plan", "architect", "strategy", "설계", "계획", "전략", "아키텍처"],
        ["architect.md", "planner.md"],
    ),
    (
        ["test", "qa", "verify", "테스트", "검증"],
        ["test-engineer.md", "qa-tester.md"],
    ),
    (
        ["write", "document", "report", "작성", "문서", "보고서"],
        ["writer.md", "document-specialist.md"],
    ),
]


def _find_agent_file(agent_name: str) -> Path | None:
    for directory in AGENT_DIRS:
        if not directory.is_dir():
            continue
        exact = directory / f"{agent_name}.md"
        if exact.is_file():
            return exact
        matches = sorted(directory.glob(f"*{agent_name}*.md"))
        if matches:
            return matches[0]
    return None


def _select_agent_prompts(
    task: str,
    max_agents: int = 2,
    agent_names: list[str] | None = None,
) -> str:
    """태스크/명시 에이전트에 맞는 에이전트 프롬프트를 읽어서 반환."""
    if not any(directory.is_dir() for directory in AGENT_DIRS):
        return ""

    selected_names: list[str] = []
    if agent_names:
        selected_names = [name for name in agent_names if name]
    else:
        try:
            from tools.agent_catalog_v2 import recommend_agents_llm_sync
            selected_names = recommend_agents_llm_sync(task, "", max_agents=max_agents)
        except Exception:
            selected_names = []

    if not selected_names:
        task_lower = task.lower()
        matched_files: list[str] = []

        for keywords, agent_files in _AGENT_KEYWORD_MAP:
            if any(kw in task_lower for kw in keywords):
                matched_files.extend(agent_files)

        seen: set[str] = set()
        unique: list[str] = []
        for f in matched_files:
            stem = Path(f).stem
            if stem not in seen:
                seen.add(stem)
                unique.append(stem)
        selected_names = unique[:max_agents]

    if not selected_names:
        return ""

    prompts: list[str] = []
    for name in selected_names[:max_agents]:
        fpath = _find_agent_file(name)
        if fpath and fpath.is_file():
            content = fpath.read_text(errors="replace")[:2000]  # 토큰 절약
            prompts.append(f"[Agent: {fpath.stem}]\n{content}")
            logger.debug(f"에이전트 주입: {fpath.name} ({len(content)}자)")

    return "\n\n".join(prompts)


def _looks_like_repo_search_intent(prompt: str) -> bool:
    return bool(_REPO_CUE_RE.search(prompt))


def _looks_like_noise_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False

    lowered = stripped.lower()
    if lowered.startswith(_DROP_LINE_PREFIXES):
        return True
    if any(token in lowered for token in _DROP_LINE_CONTAINS):
        return True
    if stripped.startswith("<") and stripped.endswith(">"):
        return True
    return False


def _sanitize_codex_output(text: str) -> str:
    """Codex transcript/tool 로그에서 사용자에게 보여줄 답변만 최대한 추린다."""
    if not text:
        return text

    mode: str | None = None
    skip_numeric_after_tokens = False
    cleaned_lines: list[str] = []

    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.rstrip()
        stripped = line.strip()
        lowered = stripped.lower()

        header_mode = _SECTION_HEADERS.get(lowered)
        if header_mode is not None:
            mode = header_mode
            continue

        if lowered.startswith("tokens used"):
            skip_numeric_after_tokens = True
            continue
        if skip_numeric_after_tokens and re.fullmatch(r"[\d,]+", stripped):
            skip_numeric_after_tokens = False
            continue
        skip_numeric_after_tokens = False

        if mode == "drop":
            continue
        if _looks_like_noise_line(line):
            continue
        if stripped.startswith("[TEAM:") or stripped.startswith("💬 PM 직접 답변"):
            mode = "keep"
        cleaned_lines.append(line)

    cleaned = "\n".join(cleaned_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()

    if "[TEAM:" in cleaned:
        cleaned = cleaned[cleaned.rfind("[TEAM:"):].strip()
    elif "💬 PM 직접 답변" in cleaned:
        cleaned = cleaned[cleaned.rfind("💬 PM 직접 답변"):].strip()

    return cleaned or text.strip()


class CodexRunner:
    """OpenAI Codex CLI를 subprocess로 실행하는 래퍼."""

    def __init__(
        self,
        cli_path: str = CODEX_CLI,
        timeout: int = DEFAULT_TIMEOUT,
        workdir: str | None = None,
    ) -> None:
        self.cli_path = cli_path
        self.timeout = timeout
        self.workdir = workdir or str(Path.home() / ".ai-org" / "workspace")
        Path(self.workdir).mkdir(parents=True, exist_ok=True)
        self._last_run_metrics: dict[str, int | float | str] = {}

    def get_last_run_metrics(self) -> dict[str, int | float | str]:
        return dict(self._last_run_metrics)

    def _resolve_workdir(self, prompt: str) -> str:
        """프롬프트에서 외부 로컬 리포지토리/디렉토리를 찾아 작업 디렉토리로 사용한다."""
        explicit = self._extract_explicit_path(prompt)
        if explicit is not None:
            logger.info(f"Codex 작업 디렉토리 선택(명시 경로): {explicit}")
            return str(explicit)

        repo_dir = self._find_repo_from_prompt(prompt)
        if repo_dir is not None:
            logger.info(f"Codex 작업 디렉토리 선택(로컬 리포지토리): {repo_dir}")
            return str(repo_dir)

        return self.workdir

    def _extract_explicit_path(self, prompt: str) -> Path | None:
        for raw in re.findall(r"(?:(?<=\s)|^)(~?/[^ \t\r\n'\"`]+)", prompt):
            candidate = Path(raw).expanduser()
            if not candidate.exists():
                continue
            target = candidate if candidate.is_dir() else candidate.parent
            repo_root = self._find_repo_root(target)
            return repo_root or target
        return None

    def _find_repo_from_prompt(self, prompt: str) -> Path | None:
        if not _looks_like_repo_search_intent(prompt):
            return None

        names = self._extract_repo_names(prompt)
        if not names:
            return None

        for search_root in self._iter_search_roots():
            for repo_name in names:
                for candidate in search_root.glob(f"**/{repo_name}"):
                    if not candidate.is_dir():
                        continue
                    repo_root = self._find_repo_root(candidate)
                    if repo_root is not None:
                        return repo_root
        return None

    def _extract_repo_names(self, prompt: str) -> list[str]:
        names: list[str] = []
        for match in re.findall(r"\b[a-zA-Z0-9._-]{2,}\b", prompt):
            lowered = match.lower()
            if lowered in {"repo", "repository", "directory", "dir", "path", "local", "git"}:
                continue
            if lowered not in names:
                names.append(lowered)
        return names

    def _iter_search_roots(self) -> list[Path]:
        configured = os.environ.get("CODEX_REPO_SEARCH_ROOTS", "")
        if configured:
            roots = [
                Path(part).expanduser()
                for part in configured.split(os.pathsep)
                if part.strip()
            ]
        else:
            home = Path.home()
            roots = [
                home / "Downloads",
                home / "Desktop",
                home / "Documents",
                home / "workspace",
                home / "code",
                home / "src",
            ]
        return [root for root in roots if root.is_dir()]

    def _find_repo_root(self, path: Path) -> Path | None:
        current = path.resolve()
        for candidate in [current, *current.parents]:
            git_dir = candidate / ".git"
            if git_dir.exists():
                return candidate
        return None

    async def _run(
        self,
        prompt: str,
        model: str | None = None,
        workdir: str | None = None,
        workdir_hint: str | None = None,
        agents: list[str] | None = None,
        shell_session_manager=None,
        shell_team_id: str | None = None,
        shell_purpose: str = "codex-batch",
    ) -> str:
        """Codex 실행 후 결과 반환. 에이전트 프롬프트 자동 주입."""
        self._last_run_metrics = {}
        # 에이전트 프롬프트 주입
        agent_context = _select_agent_prompts(prompt, agent_names=agents)
        full_prompt = f"{agent_context}\n\n{prompt}" if agent_context else prompt
        resolved_workdir = workdir or self._resolve_workdir(workdir_hint or prompt)
        timeout_sec = self._effective_timeout(agents)

        # codex exec <PROMPT> — 비인터랙티브 모드, --prompt 플래그 없음
        cmd = [
            self.cli_path,
            "exec",
            "--dangerously-bypass-approvals-and-sandbox",
            "--skip-git-repo-check",
            full_prompt,
        ]
        if model:
            cmd += ["-c", f"model={model}"]

        logger.debug(f"Codex 실행: 프롬프트 {len(prompt)}자")

        if shell_session_manager and shell_team_id:
            shell_cmd = f"cd {shlex.quote(resolved_workdir)} && {shlex.join(cmd)}"
            try:
                output, exit_code = await shell_session_manager.run_shell_command(
                    shell_team_id,
                    shell_cmd,
                    purpose=shell_purpose,
                    timeout=timeout_sec,
                )
                self._last_run_metrics = {
                    "output_chars": len(output or ""),
                    "usage_source": "codex_no_usage",
                }
                if exit_code != 0 and not output:
                    return f"❌ Codex 오류 (code={exit_code})"
                sanitized = _sanitize_codex_output(output or "")
                return sanitized or "(결과 없음)"
            except asyncio.TimeoutError:
                return f"❌ Codex 타임아웃 ({timeout_sec}초)"

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=resolved_workdir,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)

            if proc.returncode != 0:
                error = stderr.decode(errors="replace")
                return f"❌ Codex 오류: {error[:500]}"

            text = stdout.decode(errors="replace").strip() or "(결과 없음)"
            text = _sanitize_codex_output(text) or "(결과 없음)"
            self._last_run_metrics = {
                "output_chars": len(text),
                "usage_source": "codex_no_usage",
            }
            return text

        except asyncio.TimeoutError:
            return f"❌ Codex 타임아웃 ({timeout_sec}초)"
        except FileNotFoundError:
            return f"❌ Codex CLI 없음: {self.cli_path}"
        except Exception as e:
            return f"❌ 예외: {e}"

    def _effective_timeout(self, agents: list[str] | None = None) -> int:
        if agents and len([name for name in agents if name]) >= 2:
            return max(self.timeout, COMPLEX_TASK_TIMEOUT)
        return self.timeout

    async def run(
        self,
        prompt: str,
        model: str | None = None,
        workdir: str | None = None,
        workdir_hint: str | None = None,
        agents: list[str] | None = None,
        shell_session_manager=None,
        shell_team_id: str | None = None,
        shell_purpose: str = "codex-batch",
    ) -> str:
        """Codex 실행 후 결과 반환. 에이전트 프롬프트 자동 주입."""
        return await self._run(
            prompt,
            model=model,
            workdir=workdir,
            workdir_hint=workdir_hint,
            agents=agents,
            shell_session_manager=shell_session_manager,
            shell_team_id=shell_team_id,
            shell_purpose=shell_purpose,
        )
