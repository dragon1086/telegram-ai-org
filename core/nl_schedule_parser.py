"""자연어 → cron 표현식 + 태스크 설명 파서.

규칙 기반 패턴 먼저 시도; ANTHROPIC_API_KEY 있으면 복잡한 표현은 LLM fallback.
"""
from __future__ import annotations

import os
import re


class ParseError(Exception):
    """자연어 파싱 실패."""


# ── 상수 ──────────────────────────────────────────────────────────────────

_DAYS_KR = {
    "월요일": 1, "월": 1,
    "화요일": 2, "화": 2,
    "수요일": 3, "수": 3,
    "목요일": 4, "목": 4,
    "금요일": 5, "금": 5,
    "토요일": 6, "토": 6,
    "일요일": 0, "일": 0,
}

_DAYS_KR_LABEL = {
    0: "일요일", 1: "월요일", 2: "화요일", 3: "수요일",
    4: "목요일", 5: "금요일", 6: "토요일",
}

_HOUR_PATTERN = re.compile(
    r"(?:오전|오후|낮|저녁|밤|새벽)?\s*(\d{1,2})\s*시(?:\s*(\d{1,2})\s*분)?"
)
_AM_MARKERS = {"오전", "새벽"}
_PM_MARKERS = {"오후", "저녁", "밤"}

# 태스크 설명에서 시간/빈도 표현을 제거할 패턴
_TIME_STRIP_RE = re.compile(
    r"매일|매주|매달|매월|"
    r"(?:오전|오후|낮|저녁|밤|새벽)?\s*\d{1,2}\s*시(?:\s*\d{1,2}\s*분)?|"
    r"[가-힣]+요일|"
    r"\d{1,2}\s*일\s*에?|"
    r"[에에서]\s*|"
    r"(?:에|마다)\s*"
)


def _parse_hour(text: str) -> tuple[int, int]:
    """텍스트에서 시/분 추출. 반환: (hour_24, minute)."""
    ampm = None
    for marker in _AM_MARKERS:
        if marker in text:
            ampm = "am"
            break
    if ampm is None:
        for marker in _PM_MARKERS:
            if marker in text:
                ampm = "pm"
                break

    m = _HOUR_PATTERN.search(text)
    if not m:
        return 9, 0  # 기본값: 오전 9시

    hour = int(m.group(1))
    minute = int(m.group(2)) if m.group(2) else 0

    if ampm == "pm" and hour != 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    # 오전/오후 없이 12 미만이면 그냥 사용 (오전 9시 등 명시 없어도 오전으로 간주)

    return hour % 24, minute


def _extract_task_description(text: str, time_parts: list[str]) -> str:
    """시간/빈도 표현을 제거해 핵심 태스크만 추출."""
    result = text
    for part in time_parts:
        result = result.replace(part, "")
    result = _TIME_STRIP_RE.sub("", result)
    # 조사/어미 정리
    result = re.sub(r"\s+", " ", result).strip()
    result = result.strip("해줘줘요 .!?")
    return result or text


class NLScheduleParser:
    """자연어 스케줄 표현 → cron + 태스크 설명."""

    def parse(self, text: str) -> dict:
        """
        입력: "매일 오전 9시에 AI 뉴스 3개 요약해줘"
        출력: {
            "cron_expr": "0 9 * * *",
            "task_description": "AI 뉴스 3개 요약",
            "human_readable": "매일 오전 9시",
            "confidence": 0.9
        }

        Raises:
            ParseError: 파싱 불가능한 경우.
        """
        # 1. 규칙 기반 시도
        result = self._rule_based(text)
        if result is not None:
            return result

        # 2. LLM fallback (API key 있을 때만)
        if os.environ.get("ANTHROPIC_API_KEY"):
            result = self._llm_fallback(text)
            if result is not None:
                return result

        raise ParseError(
            f"스케줄 표현을 인식하지 못했습니다: '{text}'\n"
            "예시: '매일 오전 9시에 AI 뉴스 요약', '매주 월요일 오전 10시에 리포트 확인'"
        )

    # ── 규칙 기반 ─────────────────────────────────────────────────────────

    def _rule_based(self, text: str) -> dict | None:
        """규칙 기반 파싱. 인식 불가 시 None."""
        t = text.strip()

        # 매달 N일
        monthly = re.search(r"매달|매월", t)
        day_match = re.search(r"(\d{1,2})\s*일", t)
        if monthly and day_match:
            day = int(day_match.group(1))
            if not 1 <= day <= 31:
                return None
            hour, minute = _parse_hour(t)
            human = f"매달 {day}일 {self._fmt_time(hour, minute)}"
            return {
                "cron_expr": f"{minute} {hour} {day} * *",
                "task_description": self._task_desc(t),
                "human_readable": human,
                "confidence": 0.85,
            }

        # 매주 [요일] [시간]
        weekly = re.search(r"매주", t)
        if weekly:
            day_num = None
            matched_day_str = None
            for kw, num in _DAYS_KR.items():
                if kw in t:
                    day_num = num
                    matched_day_str = kw
                    break
            if day_num is not None:
                hour, minute = _parse_hour(t)
                human = f"매주 {_DAYS_KR_LABEL[day_num]} {self._fmt_time(hour, minute)}"
                return {
                    "cron_expr": f"{minute} {hour} * * {day_num}",
                    "task_description": self._task_desc(t),
                    "human_readable": human,
                    "confidence": 0.9,
                }
            # 매주인데 요일 없으면 실패
            return None

        # 매일 [시간]
        daily = re.search(r"매일", t)
        if daily:
            hour, minute = _parse_hour(t)
            human = f"매일 {self._fmt_time(hour, minute)}"
            return {
                "cron_expr": f"{minute} {hour} * * *",
                "task_description": self._task_desc(t),
                "human_readable": human,
                "confidence": 0.95,
            }

        # 요일만 명시된 경우 (매주 없이) — "월요일 오전 9시에 ..."
        for kw, day_num in _DAYS_KR.items():
            if kw in t:
                hour, minute = _parse_hour(t)
                human = f"매주 {_DAYS_KR_LABEL[day_num]} {self._fmt_time(hour, minute)}"
                return {
                    "cron_expr": f"{minute} {hour} * * {day_num}",
                    "task_description": self._task_desc(t),
                    "human_readable": human,
                    "confidence": 0.75,
                }

        return None

    @staticmethod
    def _fmt_time(hour: int, minute: int) -> str:
        period = "오전" if hour < 12 else "오후"
        h = hour if hour <= 12 else hour - 12
        if minute:
            return f"{period} {h}시 {minute}분"
        return f"{period} {h}시"

    @staticmethod
    def _task_desc(text: str) -> str:
        """시간/빈도 표현 제거 후 태스크 설명 추출."""
        result = _TIME_STRIP_RE.sub(" ", text)
        result = re.sub(r"\s+", " ", result).strip()
        result = result.strip("해줘줘요.!? ")
        return result or text.strip()

    # ── LLM fallback ─────────────────────────────────────────────────────

    def _llm_fallback(self, text: str) -> dict | None:
        """Anthropic API로 cron 추출 시도. 실패 시 None."""
        try:
            import anthropic
            client = anthropic.Anthropic()
            prompt = (
                "아래 한국어 스케줄 표현을 분석해서 JSON으로만 응답하세요.\n"
                "형식: {\"cron_expr\": \"분 시 일 월 요일\", \"task_description\": \"태스크\", \"human_readable\": \"사람이 읽을 수 있는 주기\"}\n"
                "요일: 0=일, 1=월, 2=화, 3=수, 4=목, 5=금, 6=토\n"
                f"스케줄 표현: {text}"
            )
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )
            import json
            content = msg.content[0].text.strip()
            # JSON 추출
            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            if not json_match:
                return None
            data = json.loads(json_match.group())
            if "cron_expr" not in data or "task_description" not in data:
                return None
            data.setdefault("human_readable", text)
            data["confidence"] = 0.7
            return data
        except Exception:
            return None
