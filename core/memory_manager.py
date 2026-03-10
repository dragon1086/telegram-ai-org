"""메모리 매니저 — CORE/SUMMARY/LOG 3계층 기억 시스템.

파일 위치: ~/.ai-org/memory/{scope}.md
- CORE: importance 9-10, 항상 프롬프트 주입, 수동 관리
- SUMMARY: importance 5-8, LLM 자동 요약 결과
- LOG: 최근 30개 유지, importance 0-10 자동 채점
"""
from __future__ import annotations

import re
import tempfile
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

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


# ── importance 채점 프롬프트 ──────────────────────────────────────────────────

_SCORE_SYSTEM = """\
태스크/이벤트의 중요도를 0~10 정수로만 응답하세요. 기준:
- 의사결정/방향 변경 언급: +3
- 사용자(상록)가 명시적 강조: +3
- 반복 참조 가능성 높음: +2
- 향후 작업에 영향: +2
- 일회성 단순 실행: 1-2
정수만 응답. 설명 없음."""

_CORE_DETECT_SYSTEM = """\
아래 내용이 "이거 꼭 기억해", "항상 기억", "절대 잊지 마" 같은 핵심 지시를 포함하면 "yes"로만 응답.
아니면 "no"로만 응답."""

_COMPRESS_SYSTEM = """\
아래 로그 항목들을 한 줄 요약으로 압축하세요. 핵심 내용만 유지. 날짜 범위 포함. 50자 이내."""


# ── MemoryManager ─────────────────────────────────────────────────────────────

class MemoryManager:
    """CORE/SUMMARY/LOG 3계층 메모리 시스템."""

    def __init__(self, scope: str) -> None:
        self.scope = scope
        self.path = MEMORY_DIR / f"{scope}.md"
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)

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

    async def add_log(self, content: str, openai_client: Any = None) -> int:
        """새 LOG 항목 추가. importance 자동 채점. returns importance 값."""
        importance = await self._score_importance(content, openai_client)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = LogEntry(importance=importance, timestamp=timestamp, content=content[:200])

        doc = self.load()
        doc.log.append(entry)

        # LOG 30개 초과 시 compress 트리거
        if len(doc.log) > MAX_LOG_ENTRIES:
            doc = await self._compress_doc(doc, openai_client)
        else:
            self._save(doc)

        logger.debug(f"[{self.scope}] LOG 추가 (importance={importance}): {content[:60]}")
        return importance

    async def _score_importance(self, content: str, openai_client: Any) -> int:
        """LLM으로 importance 0-10 채점. 실패 시 키워드 폴백."""
        if openai_client is None:
            return self._keyword_score(content)
        try:
            resp = await openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": _SCORE_SYSTEM},
                    {"role": "user", "content": content[:500]},
                ],
                max_tokens=5,
                temperature=0,
            )
            raw = resp.choices[0].message.content.strip()
            score = int(re.search(r"\d+", raw).group())  # type: ignore
            return max(0, min(10, score))
        except Exception as e:
            logger.debug(f"importance 채점 LLM 실패: {e}")
            return self._keyword_score(content)

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

    async def compress(self, openai_client: Any = None) -> None:
        """사이즈 관리: LOG 초과 시 자동 압축."""
        doc = self.load()
        doc = await self._compress_doc(doc, openai_client)

    async def _compress_doc(self, doc: MemoryDoc, openai_client: Any) -> MemoryDoc:
        """
        1. importance 1-4 항목 삭제
        2. importance 5+ 항목 → LLM 한 줄 요약 → SUMMARY 승격
        3. SUMMARY 과다 시 재압축
        """
        low = [e for e in doc.log if e.importance <= 4]
        high = [e for e in doc.log if e.importance >= 5]

        # high 항목들 SUMMARY 승격
        if high:
            summary_line = await self._summarize_entries(high, openai_client)
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

    async def _summarize_entries(self, entries: list[LogEntry], openai_client: Any) -> str:
        """LOG 항목들을 한 줄 요약."""
        if not entries:
            return ""
        text = "\n".join(e.format() for e in entries)
        if openai_client is None:
            # 폴백: 첫 항목 내용 사용
            dates = f"{entries[0].timestamp[:7]}~{entries[-1].timestamp[:7]}"
            return f"{dates}: {entries[0].content[:80]}"
        try:
            resp = await openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": _COMPRESS_SYSTEM},
                    {"role": "user", "content": text[:1000]},
                ],
                max_tokens=80,
                temperature=0,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            logger.debug(f"요약 LLM 실패: {e}")
            dates = f"{entries[0].timestamp[:7]}"
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

    async def maybe_promote_to_core(self, content: str, openai_client: Any = None) -> bool:
        """'이거 꼭 기억해' 감지 시 CORE 승격. 승격됐으면 True 반환."""
        # 빠른 키워드 체크 먼저
        keywords = ["꼭 기억", "항상 기억", "절대 잊지", "핵심 사실", "반드시 기억", "never forget"]
        if any(kw in content for kw in keywords):
            self.add_core(content)
            return True

        if openai_client is None:
            return False

        try:
            resp = await openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": _CORE_DETECT_SYSTEM},
                    {"role": "user", "content": content[:300]},
                ],
                max_tokens=5,
                temperature=0,
            )
            answer = resp.choices[0].message.content.strip().lower()
            if answer == "yes":
                self.add_core(content)
                return True
        except Exception as e:
            logger.debug(f"CORE 승격 감지 실패: {e}")

        return False

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
