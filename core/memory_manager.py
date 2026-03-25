"""메모리 매니저 — CORE/SUMMARY/LOG 3계층 기억 시스템.

파일 위치: ~/.ai-org/memory/{scope}.md
- CORE: importance 9-10, 항상 프롬프트 주입, 수동 관리
- SUMMARY: importance 5-8, LLM 자동 요약 결과
- LOG: 최근 30개 유지, importance 0-10 자동 채점
"""
from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any  # kept for anthropic_client: Any signature compatibility

from loguru import logger

MEMORY_DIR = Path.home() / ".ai-org" / "memory"
MAX_LOG_ENTRIES = 30
MAX_CONTEXT_TOKENS = 1500  # 대략적인 글자 수 기준 (1토큰 ≈ 2-3글자)
MAX_CONTEXT_CHARS = MAX_CONTEXT_TOKENS * 3


# ── 데이터 구조 ───────────────────────────────────────────────────────────────

@dataclass
class LogEntry:
    importance: int
    timestamp: str
    content: str

    def format(self) -> str:
        return f"- [{self.importance}] {self.timestamp} | {self.content}"

    @classmethod
    def parse(cls, line: str) -> "LogEntry | None":
        m = re.match(r"^- \[(\d+)\] (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) \| (.+)$", line.strip())
        if m:
            return cls(importance=int(m.group(1)), timestamp=m.group(2), content=m.group(3))
        return None


@dataclass
class MemoryDoc:
    core: list[str] = field(default_factory=list)
    summary: list[str] = field(default_factory=list)
    log: list[LogEntry] = field(default_factory=list)



# ── MemoryManager ─────────────────────────────────────────────────────────────

class MemoryManager:
    """CORE/SUMMARY/LOG 3계층 메모리 시스템."""

    def __init__(self, scope: str) -> None:
        self.scope = scope
        self.path = MEMORY_DIR / f"{scope}.md"
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        self._context_db = None

    # ── 로드/파싱 ──────────────────────────────────────────────────────────

    def load(self) -> MemoryDoc:
        """CORE, SUMMARY, LOG 파싱해서 MemoryDoc 반환."""
        doc = MemoryDoc()
        if not self.path.exists():
            return doc

        text = self.path.read_text(encoding="utf-8")
        section: str | None = None

        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("## [CORE]"):
                section = "core"
            elif stripped.startswith("## [SUMMARY]"):
                section = "summary"
            elif stripped.startswith("## [LOG]"):
                section = "log"
            elif stripped.startswith("<!--") or not stripped:
                continue
            elif section == "core" and stripped.startswith("- "):
                doc.core.append(stripped[2:])
            elif section == "summary" and stripped.startswith("- "):
                doc.summary.append(stripped[2:])
            elif section == "log" and stripped.startswith("- ["):
                entry = LogEntry.parse(stripped)
                if entry:
                    doc.log.append(entry)

        return doc

    def _save(self, doc: MemoryDoc) -> None:
        """원자적 저장."""
        lines = [
            "## [CORE] 핵심 사실\n",
            "<!-- importance: 9-10 | 항상 프롬프트에 주입 | 수동 관리 -->\n",
        ]
        for item in doc.core:
            lines.append(f"- {item}\n")
        if not doc.core:
            lines.append("<!-- 없음 -->\n")

        lines += [
            "\n## [SUMMARY] 압축된 과거 기억\n",
            "<!-- importance: 5-8 | LLM이 자동 요약 -->\n",
        ]
        for item in doc.summary:
            lines.append(f"- {item}\n")
        if not doc.summary:
            lines.append("<!-- 없음 -->\n")

        lines += [
            "\n## [LOG] 최근 이력\n",
            f"<!-- 최근 {MAX_LOG_ENTRIES}개 유지 -->\n",
        ]
        for entry in doc.log:
            lines.append(entry.format() + "\n")
        if not doc.log:
            lines.append("<!-- 없음 -->\n")

        content = "".join(lines)
        try:
            fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(content)
                os.replace(tmp, str(self.path))
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
        except OSError as e:
            logger.error(f"메모리 저장 실패 ({self.scope}): {e}")

    # ── LOG 추가 ──────────────────────────────────────────────────────────

    async def add_log(self, content: str, anthropic_client: Any = None) -> int:
        """새 LOG 항목 추가. importance 키워드 채점. returns importance 값."""
        importance = self._keyword_score(content)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = LogEntry(importance=importance, timestamp=timestamp, content=content[:200])

        doc = self.load()
        doc.log.append(entry)

        # LOG 30개 초과 시 compress 트리거
        if len(doc.log) > MAX_LOG_ENTRIES:
            doc = await self._compress_doc(doc)
        else:
            self._save(doc)

        logger.debug(f"[{self.scope}] LOG 추가 (importance={importance}): {content[:60]}")
        return importance

    @staticmethod
    def _keyword_score(content: str) -> int:
        """키워드 기반 폴백 채점."""
        score = 3
        high_kw = ["결정", "변경", "상록", "꼭", "필수", "항상", "절대", "중요", "승인", "지시"]
        med_kw = ["완료", "구현", "배포", "수정", "버그", "보안"]
        for kw in high_kw:
            if kw in content:
                score += 2
        for kw in med_kw:
            if kw in content:
                score += 1
        return max(0, min(10, score))

    # ── CORE 수동 관리 ────────────────────────────────────────────────────

    def add_core(self, content: str) -> None:
        """CORE 항목 추가 (수동)."""
        doc = self.load()
        if content not in doc.core:
            doc.core.append(content)
            self._save(doc)
            logger.info(f"[{self.scope}] CORE 추가: {content[:60]}")

    def remove_core(self, index: int) -> None:
        """CORE 항목 제거 (0-indexed)."""
        doc = self.load()
        if 0 <= index < len(doc.core):
            removed = doc.core.pop(index)
            self._save(doc)
            logger.info(f"[{self.scope}] CORE 제거: {removed[:60]}")
        else:
            logger.warning(f"[{self.scope}] CORE index {index} 범위 초과")

    # ── COMPRESS ─────────────────────────────────────────────────────────

    async def compress(self, anthropic_client: Any = None) -> None:
        """사이즈 관리: LOG 초과 시 자동 압축."""
        doc = self.load()
        doc = await self._compress_doc(doc)

    async def _compress_doc(self, doc: MemoryDoc) -> MemoryDoc:
        """
        1. importance 1-4 항목 삭제
        2. importance 5+ 항목 → 첫 항목 기반 한 줄 요약 → SUMMARY 승격
        3. SUMMARY 과다 시 재압축
        """
        low = [e for e in doc.log if e.importance <= 4]
        high = [e for e in doc.log if e.importance >= 5]

        # high 항목들 SUMMARY 승격 (키워드 폴백)
        if high:
            summary_line = self._summarize_entries_fallback(high)
            if summary_line:
                doc.summary.append(summary_line)

        # LOG를 낮은 importance 제거 후 최근 MAX_LOG_ENTRIES 개만 유지
        doc.log = [e for e in doc.log if e.importance >= 5]
        # 여전히 많으면 최근 것만 유지
        if len(doc.log) > MAX_LOG_ENTRIES:
            doc.log = doc.log[-MAX_LOG_ENTRIES:]

        # SUMMARY 과다 시 재압축 (대략 2000토큰 = 6000글자 기준)
        summary_total = sum(len(s) for s in doc.summary)
        if summary_total > 6000:
            doc.summary = doc.summary[-10:]  # 최근 10개만 유지

        self._save(doc)
        logger.info(f"[{self.scope}] 압축 완료: LOG {len(low)}건 제거, SUMMARY {len(doc.summary)}개")
        return doc

    @staticmethod
    def _summarize_entries_fallback(entries: list[LogEntry]) -> str:
        """LOG 항목들을 첫 항목 기반으로 한 줄 요약 (키워드 폴백)."""
        if not entries:
            return ""
        dates = f"{entries[0].timestamp[:7]}~{entries[-1].timestamp[:7]}"
        return f"{dates}: {entries[0].content[:80]}"

    # ── 컨텍스트 생성 ─────────────────────────────────────────────────────

    def build_context(self, task: str = "") -> str:
        """프롬프트용 컨텍스트 생성.

        CORE 전부 + SUMMARY 최근 3개 + LOG에서 키워드 매칭 항목.
        총 MAX_CONTEXT_CHARS 이내.
        """
        doc = self.load()
        parts: list[str] = []

        # CORE (전부)
        if doc.core:
            parts.append("## 핵심 사실 (항상 준수)")
            parts.extend(f"- {c}" for c in doc.core)

        # SUMMARY (최근 3개)
        if doc.summary:
            parts.append("\n## 과거 요약")
            parts.extend(f"- {s}" for s in doc.summary[-3:])

        # LOG (키워드 매칭)
        if doc.log and task:
            task_kw = set(re.findall(r"\w{2,}", task.lower()))
            matched = [
                e for e in doc.log
                if task_kw & set(re.findall(r"\w{2,}", e.content.lower()))
            ]
            if matched:
                parts.append("\n## 관련 최근 이력")
                parts.extend(e.format() for e in matched[-5:])
        elif doc.log:
            # task 없으면 importance 높은 것 5개
            top = sorted(doc.log, key=lambda e: e.importance, reverse=True)[:5]
            if top:
                parts.append("\n## 중요 이력")
                parts.extend(e.format() for e in top)

        result = "\n".join(parts)
        # 길이 제한
        if len(result) > MAX_CONTEXT_CHARS:
            result = result[:MAX_CONTEXT_CHARS] + "\n... (truncated)"
        return result

    # ── 자동 CORE 승격 ────────────────────────────────────────────────────

    async def maybe_promote_to_core(self, content: str, anthropic_client: Any = None) -> bool:
        """'이거 꼭 기억해' 감지 시 CORE 승격. 승격됐으면 True 반환."""
        keywords = ["꼭 기억", "항상 기억", "절대 잊지", "핵심 사실", "반드시 기억", "never forget"]
        if any(kw in content for kw in keywords):
            self.add_core(content)
            return True
        return False

    # ── BM25 통합 검색 ────────────────────────────────────────────────────

    async def search_memories(
        self, query: str, top_k: int = 5, user_id: str = ""
    ) -> list[str]:
        """BM25로 LOG 항목 + conversation_messages 통합 검색.

        rank_bm25 미설치 시 keyword 폴백.
        """
        try:
            from rank_bm25 import BM25Okapi
        except ImportError:
            return self._keyword_search(query, top_k)

        # 1) LOG 항목
        doc = self.load()
        log_entries = [e.content for e in doc.log]

        # 2) conversation_messages (최근 100개, _context_db가 있을 때만)
        conv_entries: list[str] = []
        if self._context_db is not None:
            try:
                rows = await self._context_db.get_conversation_messages(
                    user_id=user_id if user_id else None, limit=100
                )
                conv_entries = [r["content"] for r in rows if r.get("content")]
            except Exception:
                pass

        corpus = log_entries + conv_entries
        if not corpus:
            return []

        tokenized = [entry.split() for entry in corpus]
        bm25 = BM25Okapi(tokenized)
        scores = bm25.get_scores(query.split())
        top_indices = sorted(range(len(corpus)), key=lambda i: scores[i], reverse=True)[:top_k]
        return [corpus[i] for i in top_indices if scores[i] > 0]

    def _keyword_search(self, query: str, top_k: int) -> list[str]:
        """BM25 없을 때 fallback keyword 검색."""
        doc = self.load()
        entries = [e.content for e in doc.log]
        query_words = set(query.lower().split())
        scored = [(e, len(query_words & set(e.lower().split()))) for e in entries]
        return [e for e, s in sorted(scored, key=lambda x: -x[1]) if s > 0][:top_k]

    # ── 유틸 ─────────────────────────────────────────────────────────────

    @property
    def exists(self) -> bool:
        return self.path.exists()

    def stats(self) -> dict:
        doc = self.load()
        return {
            "scope": self.scope,
            "core": len(doc.core),
            "summary": len(doc.summary),
            "log": len(doc.log),
        }
