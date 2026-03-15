"""글로벌 맥락 관리 — PM들의 공유 집단 기억."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

from core.pm_decision import DecisionClientProtocol

CONTEXT_FILE = Path.home() / ".ai-org" / "global_context.md"
MAX_ENTRIES = 50   # 최대 항목 수
MAX_CHARS = 8000   # 파일 최대 크기 (바이트)


class GlobalContext:
    def __init__(self, decision_client: DecisionClientProtocol | None = None) -> None:
        self._decision_client = decision_client
        CONTEXT_FILE.parent.mkdir(parents=True, exist_ok=True)

    def set_decision_client(self, decision_client: DecisionClientProtocol | None) -> None:
        self._decision_client = decision_client

    def read(self) -> str:
        """현재 글로벌 맥락 읽기."""
        if not CONTEXT_FILE.exists():
            return ""
        return CONTEXT_FILE.read_text(encoding="utf-8")

    def append_entry(self, org_id: str, summary: str, category: str = "작업") -> None:
        """새 항목 추가. 오래된 항목 자동 정리."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = f"\n### [{now}] {org_id} — {category}\n{summary.strip()}\n"

        current = self.read()
        lines = current.splitlines()

        # 항목 수 관리 (### 기준으로 카운트)
        entry_count = sum(1 for line in lines if line.startswith("### ["))
        if entry_count >= MAX_ENTRIES:
            first = current.find("\n### [")
            second = current.find("\n### [", first + 1)
            if second > 0:
                current = current[:first] + current[second:]

        # 헤더 없으면 추가
        if not current.strip():
            current = "# 🧠 글로벌 맥락 — PM 공유 집단 기억\n"

        new_content = current + entry

        # 파일 크기 한도 초과 시 오래된 항목부터 제거
        while len(new_content) > MAX_CHARS:
            first = new_content.find("\n### [")
            second = new_content.find("\n### [", first + 1)
            if second > 0:
                new_content = new_content[:first] + new_content[second:]
            else:
                break

        CONTEXT_FILE.write_text(new_content, encoding="utf-8")

    async def build_system_prompt(self, org_id: str, task: str = "") -> str:
        """Claude --append-system-prompt에 주입할 맥락 텍스트.

        task가 주어지면 LLM으로 상위 3개 관련 항목을 선택(최근 15개 중).
        실패 시 최근 3개로 fallback. 결과는 2000자 하드 캡.
        """
        ctx = self.read()
        if not ctx:
            return ""

        parts = ctx.split("\n### [")
        all_entries = parts[1:] if len(parts) > 1 else parts
        candidates = all_entries[-15:]

        selected: list[str] = []

        if task and candidates:
            numbered = "\n".join(
                f"{i}. ### [{e[:200]}" for i, e in enumerate(candidates)
            )
            prompt = (
                f"Given task: {task}\n"
                f"Entries:\n{numbered}\n"
                "Return JSON array of indices of most relevant entries (max 3). "
                "Example: [0,2,5]. Return only the JSON array, nothing else."
            )
            try:
                if self._decision_client is not None:
                    raw = await asyncio.wait_for(
                        self._decision_client.complete(prompt), timeout=5.0
                    )
                else:
                    from core.llm_provider import get_provider
                    provider = get_provider()
                    if not provider:
                        raise RuntimeError("provider unavailable")
                    raw = await asyncio.wait_for(
                        provider.complete(prompt, timeout=3.0), timeout=3.0
                    )
                raw = raw.strip()
                start, end = raw.find("["), raw.rfind("]")
                if start >= 0 and end > start:
                    indices = json.loads(raw[start : end + 1])
                    selected = [
                        candidates[i]
                        for i in indices
                        if isinstance(i, int) and 0 <= i < len(candidates)
                    ]
            except Exception:
                pass

        if not selected:
            selected = candidates[-3:]

        recent_text = "\n### [".join(selected)

        def _build(sel: list[str]) -> str:
            body = "\n### [".join(sel)
            return (
                f"## 조직 공유 맥락 (다른 PM들의 최근 작업)\n"
                f"당신은 {org_id} PM입니다. 아래는 다른 PM들의 최근 작업 내용입니다:\n\n"
                f"### [{body}\n\n"
                "이 맥락을 참고해서 중복 작업을 피하고, 연관된 작업이라면 언급해주세요."
            )

        result = _build(selected)

        # 2000자 하드 캡 — 오래된 항목부터 제거
        while len(result) > 2000 and len(selected) > 1:
            selected = selected[1:]
            result = _build(selected)
        if len(result) > 2000:
            result = result[:2000]

        return result

    async def extract_and_save(self, org_id: str, task: str, result: str) -> str:
        """작업 결과에서 핵심 내용 추출 후 저장. 추출된 요약 반환."""
        if len(result) < 100:
            return ""

        lines = result.splitlines()
        conclusion_lines = [
            line for line in lines
            if any(k in line for k in ["완료", "결론", "요약", "총", "결과", "발견", "권장", "추천", "✅", "⚠️", "❌"])
        ]

        summary_lines: list[str] = []
        summary_lines.extend(lines[:3])
        summary_lines.extend(conclusion_lines[:5])

        summary = "\n".join(summary_lines)[:300]

        if summary:
            category = "작업"
            try:
                if self._decision_client is not None:
                    raw_cat = await asyncio.wait_for(
                        self._decision_client.complete(
                            f"Categorize in one word (개발/기획/분석/마케팅/운영/기타): {task[:100]}"
                        ),
                        timeout=5.0,
                    )
                else:
                    from core.llm_provider import get_provider
                    provider = get_provider()
                    if not provider:
                        raise RuntimeError("provider unavailable")
                    cat_prompt = (
                        f"Categorize in one word (개발/기획/분석/마케팅/운영/기타): {task[:100]}"
                    )
                    raw_cat = await asyncio.wait_for(
                        provider.complete(cat_prompt, timeout=3.0), timeout=3.0
                    )
                valid = {"개발", "기획", "분석", "마케팅", "운영", "기타"}
                for word in raw_cat.strip().split():
                    if word in valid:
                        category = word
                        break
            except Exception:
                pass

            self.append_entry(
                org_id,
                f"**작업**: {task[:80]}\n**요약**: {summary}",
                category,
            )

        return summary
