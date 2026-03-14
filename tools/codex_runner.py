"""Codex CLI 실행 래퍼 — 에이전트 프롬프트 주입 지원."""
from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path

from loguru import logger


CODEX_CLI = os.environ.get("CODEX_CLI_PATH", "codex")
DEFAULT_TIMEOUT = 300
AGENTS_DIR = Path.home() / ".ai-org" / "agents"

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


def _select_agent_prompts(task: str, max_agents: int = 2) -> str:
    """태스크 키워드에 맞는 에이전트 프롬프트를 읽어서 반환."""
    if not AGENTS_DIR.is_dir():
        return ""

    task_lower = task.lower()
    matched_files: list[str] = []

    for keywords, agent_files in _AGENT_KEYWORD_MAP:
        if any(kw in task_lower for kw in keywords):
            matched_files.extend(agent_files)

    # 중복 제거, max_agents 제한
    seen: set[str] = set()
    unique: list[str] = []
    for f in matched_files:
        if f not in seen:
            seen.add(f)
            unique.append(f)
    unique = unique[:max_agents]

    if not unique:
        return ""

    prompts: list[str] = []
    for fname in unique:
        fpath = AGENTS_DIR / fname
        if fpath.is_file():
            content = fpath.read_text(errors="replace")[:2000]  # 토큰 절약
            prompts.append(f"[Agent: {fname}]\n{content}")
            logger.debug(f"에이전트 주입: {fname} ({len(content)}자)")

    return "\n\n".join(prompts)


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
            roots = [Path(part).expanduser() for part in configured.split(os.pathsep) if part.strip()]
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
    ) -> str:
        """Codex 실행 후 결과 반환. 에이전트 프롬프트 자동 주입."""
        # 에이전트 프롬프트 주입
        agent_context = _select_agent_prompts(prompt)
        full_prompt = f"{agent_context}\n\n{prompt}" if agent_context else prompt
        resolved_workdir = workdir or self._resolve_workdir(full_prompt)

        # codex exec <PROMPT> — 비인터랙티브 모드, --prompt 플래그 없음
        cmd = [self.cli_path, "exec", "--skip-git-repo-check", full_prompt]
        if model:
            cmd += ["-c", f"model={model}"]

        logger.debug(f"Codex 실행: 프롬프트 {len(prompt)}자")

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=resolved_workdir,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout)

            if proc.returncode != 0:
                error = stderr.decode(errors="replace")
                return f"❌ Codex 오류: {error[:500]}"

            return stdout.decode(errors="replace").strip() or "(결과 없음)"

        except asyncio.TimeoutError:
            return f"❌ Codex 타임아웃 ({self.timeout}초)"
        except FileNotFoundError:
            return f"❌ Codex CLI 없음: {self.cli_path}"
        except Exception as e:
            return f"❌ 예외: {e}"

    async def run(self, prompt: str, model: str | None = None, workdir: str | None = None) -> str:
        """Codex 실행 후 결과 반환. 에이전트 프롬프트 자동 주입."""
        return await self._run(prompt, model=model, workdir=workdir)
