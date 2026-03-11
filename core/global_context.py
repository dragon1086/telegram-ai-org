"""글로벌 맥락 관리 — PM들의 공유 집단 기억."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

CONTEXT_FILE = Path.home() / ".ai-org" / "global_context.md"
MAX_ENTRIES = 50  # 최대 항목 수


class GlobalContext:
    def __init__(self) -> None:
        CONTEXT_FILE.parent.mkdir(parents=True, exist_ok=True)

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
            # 가장 오래된 항목 제거 (앞에서부터 ### 하나 찾아서 다음 ### 전까지 제거)
            first = current.find("\n### [")
            second = current.find("\n### [", first + 1)
            if second > 0:
                current = current[:first] + current[second:]

        # 헤더 없으면 추가
        if not current.strip():
            current = "# 🧠 글로벌 맥락 — PM 공유 집단 기억\n"

        CONTEXT_FILE.write_text(current + entry, encoding="utf-8")

    def build_system_prompt(self, org_id: str) -> str:
        """Claude --append-system-prompt에 주입할 맥락 텍스트."""
        ctx = self.read()
        if not ctx:
            return ""
        # 최근 10개 항목만 추출
        entries = ctx.split("\n### [")
        recent = entries[-10:] if len(entries) > 10 else entries[1:]
        recent_text = "\n### [".join(recent)
        return (
            f"## 조직 공유 맥락 (다른 PM들의 최근 작업)\n"
            f"당신은 {org_id} PM입니다. 아래는 다른 PM들의 최근 작업 내용입니다:\n\n"
            f"### [{recent_text}\n\n"
            f"이 맥락을 참고해서 중복 작업을 피하고, 연관된 작업이라면 언급해주세요."
        )

    def extract_and_save(self, org_id: str, task: str, result: str) -> str:
        """작업 결과에서 핵심 내용 추출 후 저장. 추출된 요약 반환."""
        # 짧은 결과는 저장 불필요
        if len(result) < 100:
            return ""

        lines = result.splitlines()
        # 결론/완료/요약 키워드가 있는 줄 찾기
        conclusion_lines = [
            line for line in lines
            if any(k in line for k in ["완료", "결론", "요약", "총", "결과", "발견", "권장", "추천", "✅", "⚠️", "❌"])
        ]

        summary_lines: list[str] = []
        summary_lines.extend(lines[:3])         # 앞 3줄 (작업 개요)
        summary_lines.extend(conclusion_lines[:5])  # 결론 줄 (최대 5개)

        summary = "\n".join(summary_lines)[:500]
        if summary:
            category = (
                "분석" if any(k in task for k in ["분석", "평가", "검토"]) else
                "개발" if any(k in task for k in ["구현", "작성", "수정", "개발"]) else
                "기획" if any(k in task for k in ["기획", "전략", "계획"]) else
                "작업"
            )
            self.append_entry(
                org_id,
                f"**작업**: {task[:80]}\n**요약**: {summary}",
                category,
            )

        return summary
