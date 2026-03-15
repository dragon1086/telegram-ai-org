"""텔레그램 최종 사용자 전달 품질 가드레일."""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

from core.pm_decision import DecisionClientProtocol

LOCAL_PATH_RE = re.compile(r"(?:(?<=\s)|^)(~?/[^ \t\r\n'\"`]+)")


def extract_local_artifact_names(text: str) -> list[str]:
    names: list[str] = []
    for raw in LOCAL_PATH_RE.findall(text or ""):
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
    decision_client: DecisionClientProtocol | None = None,
) -> str:
    cleaned = (draft or "").strip()
    artifact_names = extract_local_artifact_names(cleaned)

    if decision_client is not None and needs_rewrite_for_telegram(cleaned):
        prompt = (
            "You are rewriting a PM update for a Telegram-only end user.\n"
            "Rewrite in Korean.\n"
            "Rules:\n"
            "- First paragraph must directly answer the user.\n"
            "- Do not expose local filesystem paths.\n"
            "- If artifacts exist, refer to them as attached files by filename only.\n"
            "- Explain the substance first, attachments second.\n"
            "- Preserve factual claims.\n\n"
            f"Original request:\n{original_request[:1200]}\n\n"
            f"Draft:\n{cleaned[:6000]}"
        )
        try:
            rewritten = await asyncio.wait_for(decision_client.complete(prompt), timeout=35.0)
            if rewritten and rewritten.strip():
                return _heuristic_cleanup(rewritten.strip(), artifact_names)
        except Exception:
            pass

    return _heuristic_cleanup(cleaned, artifact_names)


def _heuristic_cleanup(text: str, artifact_names: list[str]) -> str:
    cleaned = LOCAL_PATH_RE.sub("", text or "").strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    if artifact_names:
        note = "첨부 예정 산출물: " + ", ".join(artifact_names)
        if note not in cleaned:
            cleaned = f"{cleaned}\n\n{note}".strip()
    return cleaned or "최종 전달본을 정리 중입니다."
