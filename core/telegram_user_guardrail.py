"""텔레그램 최종 사용자 전달 품질 가드레일."""
from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Protocol


class DecisionClientProtocol(Protocol):
    async def complete(self, prompt: str) -> str: ...

LOCAL_PATH_RE = re.compile(r"(?:(?<=\s)|^)(~?/[^ \t\r\n'\"`]+)")
ARTIFACT_MARKER_RE = re.compile(r"\[ARTIFACT:([^\]]+)\]")


def extract_local_artifact_paths(text: str) -> list[str]:
    paths: list[str] = []
    for raw in ARTIFACT_MARKER_RE.findall(text or ""):
        candidate = raw.strip()
        if candidate and candidate not in paths:
            paths.append(candidate)
    for raw in LOCAL_PATH_RE.findall(text or ""):
        candidate = raw.strip()
        if candidate and candidate not in paths:
            paths.append(candidate)
    return paths


def extract_local_artifact_names(text: str) -> list[str]:
    names: list[str] = []
    for raw in extract_local_artifact_paths(text):
        name = Path(raw).name
        if name and name not in names:
            names.append(name)
    return names


def needs_rewrite_for_telegram(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return True
    artifact_names = extract_local_artifact_names(stripped)
    if len(artifact_names) >= 2:
        return True
    if stripped.count("/") >= 3 and len(artifact_names) >= 1:
        return True
    lower = stripped.lower()
    return "첨부" not in stripped and any(token in lower for token in ("reports/", ".md", ".html", ".pdf"))


async def ensure_user_friendly_output(
    draft: str,
    *,
    original_request: str = "",
    full_context: str = "",
    decision_client: DecisionClientProtocol | None = None,
) -> str:
    cleaned = (draft or "").strip()
    artifact_names = extract_local_artifact_names(cleaned)

    should_rewrite = needs_rewrite_for_telegram(cleaned) or bool(full_context)
    if decision_client is not None and should_rewrite:
        context_section = (
            f"\n\nFULL DEPARTMENT RESULTS (use these to produce a comprehensive report — do NOT compress or omit key findings):\n"
            f"{full_context[:8000]}"
        ) if full_context else ""
        prompt = (
            "You are a PM writing a final executive report for a Telegram-only end user.\n"
            "Apply Pyramid Principle (BLUF + MECE): conclusion first, evidence second.\n"
            "Rewrite the draft into a clean, structured Korean report.\n\n"
            "## Pre-writing checklist (do mentally before writing):\n"
            "  1. Identify the single most important conclusion (will go in ## 결론).\n"
            "  2. Cluster all findings by TOPIC (not by department).\n"
            "  3. Merge any duplicate findings into ONE bullet.\n"
            "  4. Extract PM's explicit recommendation (will go in ## PM 결정 및 권고).\n\n"
            "## Required 5-section structure (follow exactly):\n\n"
            "  ## 결론\n"
            "  [REQUIRED. ONE sentence max 50 chars. Directly answer user's request + PM recommendation.]\n\n"
            "  ## 핵심 발견사항\n"
            "  [REQUIRED. 3~5 bullets. Topic-based, NOT department-based.\n"
            "   If 2+ departments say the same thing, merge into ONE bullet with concrete numbers.]\n\n"
            "  ## 위험·이슈 (있을 때만)\n"
            "  [CONDITIONAL. Risks, conflicts, unresolved items. OMIT entirely if nothing to report.]\n\n"
            "  ## PM 결정 및 권고\n"
            "  [REQUIRED. PM's own judgment + prioritized action recommendations (P1/P2/P3).\n"
            "   Not a department summary — this is the PM's voice.]\n\n"
            "  ## 다음 조치 (있을 때만)\n"
            "  [CONDITIONAL. Concrete tasks with owner/timeline. OMIT entirely if no tasks remain.]\n\n"
            "## Hard rules (violating degrades quality):\n"
            "- 결론 must be the FIRST section — no background paragraph before it.\n"
            "- NEVER use department name as a section header.\n"
            "- NEVER copy raw department text verbatim — synthesize from PM perspective.\n"
            "- NEVER repeat the same finding across 2+ sections (MECE).\n"
            "- NEVER expose local filesystem paths — use filename only.\n"
            "- Remove all internal tags: [TEAM:], [COLLAB:], [ARTIFACT:], '역할은 여기서 끝',\n"
            "  '운영실에 위임', or any bot-internal control language.\n"
            "- Preserve all factual claims, numbers, commit hashes, and proper nouns.\n"
            "- Total report body: 15 lines max. Overflow goes to 다음 조치 or omit.\n"
            "- Use Telegram markdown only: ## headers, **bold**, - bullets,\n"
            "  `inline code`, ```lang\\ncode\\n```. NO HTML tags.\n"
            "- If artifacts exist, list filenames only at the very end (after 다음 조치).\n\n"
            f"Original request:\n{original_request[:1500]}\n\n"
            f"Draft:\n{cleaned[:4000]}"
            f"{context_section}"
        )
        try:
            rewritten = await asyncio.wait_for(decision_client.complete(prompt), timeout=60.0)
            if rewritten and rewritten.strip():
                return _heuristic_cleanup(rewritten.strip(), artifact_names)
        except Exception:
            pass

    return _heuristic_cleanup(cleaned, artifact_names)


EXIT_CODE_RE = re.compile(r"__EXIT_CODE__:\d+\s*", re.MULTILINE)
# PM 메타 태그: [TEAM:...], [COLLAB:...] 등 봇 내부 제어 태그 — 사용자에게 노출 금지
_META_TAG_RE = re.compile(r"\[(?:TEAM|COLLAB|SOLO|ARTIFACT)[^\]]*\]")


def _heuristic_cleanup(text: str, artifact_names: list[str]) -> str:
    cleaned = ARTIFACT_MARKER_RE.sub("", text or "").strip()
    cleaned = EXIT_CODE_RE.sub("", cleaned).strip()
    cleaned = LOCAL_PATH_RE.sub("", cleaned).strip()
    cleaned = _META_TAG_RE.sub("", cleaned).strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    if artifact_names:
        note = "첨부 산출물: " + ", ".join(artifact_names)
        if note not in cleaned:
            cleaned = f"{cleaned}\n\n{note}".strip()
    return cleaned or "최종 전달본을 정리 중입니다."
