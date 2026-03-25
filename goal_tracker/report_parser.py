"""GoalTracker 보고 파서 — 일일회고/주간회의 텍스트에서 조치사항 추출.

`parse_action_items(report_text, report_type)` 함수가 메인 진입점이다.
내부적으로 ActionParser를 사용하되, 보고 유형별 전처리·후처리를 추가한다.

보고 유형별 포맷:
    daily_retro (일일회고):
        - ## 오늘 한 일 / ## 내일 할 일 / ## 이슈/블로커
        - 조치사항 섹션: "조치사항:", "액션아이템:", "후속 조치:"
        - 불릿 리스트 중 "내일 할 일" / "이슈" 섹션 우선 파싱

    weekly_meeting (주간회의):
        - ## 주간 목표 달성 현황 / ## 다음 주 계획 / ## 결정 사항
        - 조치사항 섹션: "결정 사항:", "다음 주 계획:", "액션아이템:"
        - "담당자:" + 조직명 패턴 적극 추출
"""
from __future__ import annotations

import re
from typing import Optional

from goal_tracker.action_parser import ORG_NAME_MAP, ActionItem, ActionParser
from goal_tracker.meeting_handler import MeetingType

# ── 보고 유형별 섹션 헤더 ─────────────────────────────────────────────────────

_DAILY_PRIORITY_SECTIONS = [
    r"내일\s*할\s*일",
    r"tomorrow",
    r"이슈",
    r"블로커",
    r"blocker",
    r"조치\s*사항",
    r"액션\s*아이템",
    r"후속\s*조치",
    r"할\s*일",
]

_WEEKLY_PRIORITY_SECTIONS = [
    r"다음\s*주\s*계획",
    r"next\s*week",
    r"결정\s*사항",
    r"decision",
    r"액션\s*아이템",
    r"action\s*item",
    r"조치\s*사항",
    r"후속\s*조치",
    r"follow[\s\-]*up",
    r"주간\s*목표",
]

# 섹션 헤더 패턴 (마크다운 헤더 + 콜론 접미사 모두 허용)
_SECTION_HEADER_RE = re.compile(
    r"^(?:#{1,3}\s*|[-*]\s*|\*\*)?(.+?)(?:\*\*)?[\s:：]*$", re.MULTILINE
)


def _make_section_re(patterns: list[str]) -> re.Pattern:
    return re.compile("|".join(patterns), re.IGNORECASE)


_DAILY_PRIORITY_RE = _make_section_re(_DAILY_PRIORITY_SECTIONS)
_WEEKLY_PRIORITY_RE = _make_section_re(_WEEKLY_PRIORITY_SECTIONS)


# ── 보고 유형 정규화 ──────────────────────────────────────────────────────────

def _normalize_report_type(report_type: str) -> MeetingType:
    """report_type 문자열 → MeetingType 변환."""
    lower = report_type.lower().replace("-", "_").replace(" ", "_")
    if any(kw in lower for kw in ["daily", "retro", "일일", "데일리"]):
        return MeetingType.DAILY_RETRO
    if any(kw in lower for kw in ["weekly", "주간", "meeting"]):
        return MeetingType.WEEKLY_MEETING
    return MeetingType.UNKNOWN


# ── 섹션 추출 ─────────────────────────────────────────────────────────────────

def _extract_priority_sections(text: str, priority_re: re.Pattern) -> list[str]:
    """우선 섹션 헤더 이후 내용을 추출하여 반환.

    마크다운 헤더(##/###)나 볼드 헤더(**헤더**) 뒤에 오는 내용을 섹션 단위로 분리.
    """
    sections: list[str] = []
    lines = text.splitlines()
    in_section = False
    current_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        # 헤더 감지: ## 헤더 or **헤더**
        header_match = re.match(r"^(#{1,4}|\*\*(.+?)\*\*)\s*(.*)$", stripped)
        if header_match:
            header_text = stripped.lstrip("#").strip().strip("*").strip()
            if priority_re.search(header_text):
                # 이전 섹션 저장
                if current_lines:
                    sections.append("\n".join(current_lines))
                current_lines = []
                in_section = True
                # 헤더 라인 뒤 인라인 내용 처리
                rest = header_match.group(3).strip() if header_match.lastindex == 3 else ""
                if rest:
                    current_lines.append(rest)
                continue
            elif in_section:
                # 다른 헤더 시작 → 현재 섹션 종료
                if current_lines:
                    sections.append("\n".join(current_lines))
                    current_lines = []
                in_section = False
        elif in_section:
            current_lines.append(line)

    if current_lines and in_section:
        sections.append("\n".join(current_lines))

    return sections


# ── 주간회의 전용: 담당자+태스크 패턴 ─────────────────────────────────────────

_WEEKLY_ASSIGNEE_TASK_RE = re.compile(
    r"(?:담당자?\s*[:：]\s*)?(?P<org>"
    + "|".join(re.escape(k) for k in ORG_NAME_MAP)
    + r")\s*[:：]?\s+(?P<task>[^\n]+)",
    re.IGNORECASE,
)


def _extract_weekly_assignee_tasks(text: str) -> list[ActionItem]:
    """주간회의 전용: '개발실: 기능 구현' 형식 파싱."""
    items: list[ActionItem] = []
    for m in _WEEKLY_ASSIGNEE_TASK_RE.finditer(text):
        org_name = m.group("org").strip()
        task_desc = m.group("task").strip()
        if not task_desc or len(task_desc) < 3:
            continue
        org_id = ORG_NAME_MAP.get(org_name)
        items.append(
            ActionItem(
                description=task_desc,
                assigned_dept=org_id,
                source_text=m.group(0),
                confidence=0.9,
            )
        )
    return items


# ── 메인 함수 ─────────────────────────────────────────────────────────────────

_parser = ActionParser()  # 모듈 수준 싱글톤


def parse_action_items(
    report_text: str,
    report_type: str,
    *,
    min_confidence: float = 0.0,
) -> list[ActionItem]:
    """보고 텍스트에서 조치사항(ActionItem) 리스트를 추출.

    Args:
        report_text: 일일회고 또는 주간회의 전체 보고 텍스트.
        report_type:  "daily_retro" | "weekly_meeting" (그 외: UNKNOWN 처리).
        min_confidence: 이 값 미만 confidence 아이템 제외 (기본 0.0 = 전체 반환).

    Returns:
        ActionItem 리스트. 중복 제거, confidence 내림차순 정렬.
    """
    if not report_text or not report_text.strip():
        return []

    meeting_type = _normalize_report_type(report_type)
    items: list[ActionItem] = []
    seen: set[str] = set()

    # 1. 보고 유형별 우선 섹션 추출
    if meeting_type == MeetingType.DAILY_RETRO:
        priority_sections = _extract_priority_sections(report_text, _DAILY_PRIORITY_RE)
    elif meeting_type == MeetingType.WEEKLY_MEETING:
        priority_sections = _extract_priority_sections(report_text, _WEEKLY_PRIORITY_RE)
        # 주간회의 전용: 담당자+태스크 패턴도 추출
        assignee_items = _extract_weekly_assignee_tasks(report_text)
        for ai in assignee_items:
            key = ai.description.strip().lower()
            if key and key not in seen:
                seen.add(key)
                items.append(ai)
    else:
        priority_sections = []

    # 2. 우선 섹션에서 ActionParser로 파싱 (confidence=1.0)
    for section in priority_sections:
        for item in _parser.parse(section):
            key = item.description.strip().lower()
            if key and key not in seen:
                item.confidence = max(item.confidence, 0.9)
                seen.add(key)
                items.append(item)

    # 3. 전체 텍스트에서 ActionParser 보완 파싱
    for item in _parser.parse(report_text):
        key = item.description.strip().lower()
        if key and key not in seen:
            seen.add(key)
            items.append(item)

    # 4. confidence 필터링 + 내림차순 정렬
    if min_confidence > 0.0:
        items = [i for i in items if i.confidence >= min_confidence]

    items.sort(key=lambda i: i.confidence, reverse=True)
    return items


def parse_report_metadata(report_text: str, report_type: str) -> dict:
    """보고 텍스트에서 메타데이터(날짜, 참석자, 제목 등) 추출.

    Returns:
        {
            "report_type": str,
            "meeting_type": str,
            "date": str | None,     # "YYYY-MM-DD"
            "participants": list[str],
            "title": str,
        }
    """
    meeting_type = _normalize_report_type(report_type)

    # 날짜 추출
    date_match = re.search(
        r"(\d{4}[-/.]\d{1,2}[-/.]\d{1,2})", report_text
    )
    date_str: Optional[str] = None
    if date_match:
        date_str = re.sub(r"[/.]", "-", date_match.group(1))

    # 참석자 추출 (org_id 또는 조직명)
    participants: list[str] = []
    for org_id in re.findall(r"aiorg_\w+_bot", report_text):
        if org_id not in participants:
            participants.append(org_id)
    for org_name, org_id in ORG_NAME_MAP.items():
        if org_name in report_text and org_id not in participants:
            participants.append(org_id)

    # 제목 추출 (첫 번째 # 헤더)
    title_match = re.search(r"^#\s+(.+)$", report_text, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else ""

    return {
        "report_type": report_type,
        "meeting_type": meeting_type.value,
        "date": date_str,
        "participants": participants,
        "title": title,
    }
