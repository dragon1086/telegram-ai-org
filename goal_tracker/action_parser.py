"""조치사항 파서 — 텔레그램 봇 메시지에서 액션아이템 추출.

지원 패턴:
    1. 액션아이템 키워드: "액션아이템:", "ACTION ITEM:", "조치사항:", "TODO:"
    2. 담당자 패턴:       "담당자:", "담당:", "@org", "[aiorg_xxx_bot]"
    3. 마감일 패턴:       "마감:", "기한:", "due:", "~날짜"
    4. 불릿 리스트 패턴:  "- [ ] 태스크", "* 태스크", "1. 태스크"

파싱 결과:
    ActionItem(
        description="태스크 설명",
        assigned_dept="aiorg_engineering_bot",  # 담당 부서 (없으면 자동 라우팅)
        due_date="2026-03-31",                  # 마감일 (없으면 None)
        priority="high" | "medium" | "low",
        source_text="원문 메시지",
        confidence=0.9,                         # 파싱 신뢰도
    )
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# ── 키워드 패턴 정의 ──────────────────────────────────────────────────────────

# 액션아이템 섹션 시작 키워드 (대소문자 무시)
ACTION_HEADER_PATTERNS = [
    r"액션\s*아이템\s*[:：]?",
    r"action\s*item\s*[:：]?",
    r"조치\s*사항\s*[:：]?",
    r"TODO\s*[:：]?",
    r"할\s*일\s*[:：]?",
    r"결정\s*사항\s*[:：]?",
    r"후속\s*조치\s*[:：]?",
    r"follow\s*[-\s]?up\s*[:：]?",
]

# 담당자 패턴
ASSIGNEE_PATTERNS = [
    r"담당자\s*[:：]\s*([^\n,]+)",
    r"담당\s*[:：]\s*([^\n,]+)",
    r"@(\w+)",
    r"\[(aiorg_\w+)\]",
    r"→\s*(aiorg_\w+)",
    r"assigned\s+to\s*[:：]?\s*([^\n,]+)",
]

# 마감일 패턴
DUE_DATE_PATTERNS = [
    r"마감\s*[:：]\s*(\d{4}[-/.]\d{1,2}[-/.]\d{1,2})",
    r"기한\s*[:：]\s*(\d{4}[-/.]\d{1,2}[-/.]\d{1,2})",
    r"due\s*[:：]?\s*(\d{4}[-/.]\d{1,2}[-/.]\d{1,2})",
    r"~(\d{4}[-/.]\d{1,2}[-/.]\d{1,2})",
    r"(\d{4}[-/.]\d{1,2}[-/.]\d{1,2})\s*까지",
    r"(\d{1,2}/\d{1,2})\s*까지",
]

# 우선순위 패턴
PRIORITY_PATTERNS = {
    "high":   [r"긴급", r"urgent", r"high", r"최우선", r"P0", r"P1", r"🔴"],
    "medium": [r"보통", r"medium", r"normal", r"P2", r"🟡"],
    "low":    [r"낮음", r"low", r"나중에", r"P3", r"P4", r"🟢"],
}

# 불릿 리스트 태스크 패턴
TASK_LINE_PATTERNS = [
    r"^[-*•]\s+\[[ x]\]\s+(.+)$",   # - [ ] 태스크 / - [x] 완료
    r"^[-*•]\s+(.+)$",               # - 태스크
    r"^\d+\.\s+(.+)$",               # 1. 태스크
    r"^>?\s*[-*•]\s+(.+)$",          # > - 태스크 (인용 블록 안)
]

# 조직 이름 → org_id 매핑
ORG_NAME_MAP: dict[str, str] = {
    "개발실": "aiorg_engineering_bot",
    "기획실": "aiorg_product_bot",
    "디자인실": "aiorg_design_bot",
    "운영실": "aiorg_ops_bot",
    "성장실": "aiorg_growth_bot",
    "리서치실": "aiorg_research_bot",
    "PM": "aiorg_pm_bot",
    "pm": "aiorg_pm_bot",
    "engineering": "aiorg_engineering_bot",
    "product": "aiorg_product_bot",
    "design": "aiorg_design_bot",
    "ops": "aiorg_ops_bot",
    "growth": "aiorg_growth_bot",
    "research": "aiorg_research_bot",
}


@dataclass
class ActionItem:
    """파싱된 조치사항 단일 항목."""

    description: str
    assigned_dept: Optional[str] = None   # org_id (None이면 자동 라우팅)
    due_date: Optional[str] = None        # "YYYY-MM-DD" 형식
    priority: str = "medium"              # "high" | "medium" | "low"
    source_text: str = ""                 # 원문
    confidence: float = 1.0              # 파싱 신뢰도 0.0~1.0
    tags: list[str] = field(default_factory=list)

    def to_goal_description(self) -> str:
        """GoalTracker 태스크 형식으로 변환."""
        parts = [self.description]
        if self.assigned_dept:
            parts.append(f"[담당: {self.assigned_dept}]")
        if self.due_date:
            parts.append(f"[기한: {self.due_date}]")
        if self.priority != "medium":
            parts.append(f"[우선순위: {self.priority}]")
        return " ".join(parts)


class ActionParser:
    """텔레그램 봇 메시지에서 조치사항(액션아이템) 파싱.

    사용 예::

        parser = ActionParser()
        items = parser.parse(message_text)
        for item in items:
            print(item.description, item.assigned_dept)
    """

    def __init__(self) -> None:
        # 컴파일된 패턴 캐시
        self._header_re = re.compile(
            "|".join(ACTION_HEADER_PATTERNS), re.IGNORECASE
        )
        self._task_line_res = [
            re.compile(p, re.MULTILINE) for p in TASK_LINE_PATTERNS
        ]
        self._assignee_res = [
            re.compile(p, re.IGNORECASE) for p in ASSIGNEE_PATTERNS
        ]
        self._due_date_res = [
            re.compile(p, re.IGNORECASE) for p in DUE_DATE_PATTERNS
        ]
        self._priority_res = {
            level: [re.compile(p, re.IGNORECASE) for p in patterns]
            for level, patterns in PRIORITY_PATTERNS.items()
        }

    # ── 메인 파싱 ─────────────────────────────────────────────────────────

    def parse(self, message_text: str) -> list[ActionItem]:
        """메시지 전체에서 모든 조치사항을 파싱.

        Args:
            message_text: 텔레그램 봇 메시지 원문.

        Returns:
            ActionItem 리스트 (빈 메시지 → 빈 리스트).
        """
        if not message_text or not message_text.strip():
            return []

        items: list[ActionItem] = []

        # 1. 액션아이템 섹션 감지 → 섹션 하위 불릿 파싱
        section_items = self._parse_action_sections(message_text)
        items.extend(section_items)

        # 2. 섹션 없으면 전체 메시지에서 불릿 파싱 (신뢰도 낮춤)
        if not items:
            bullet_items = self._parse_bullet_lines(message_text, confidence=0.7)
            items.extend(bullet_items)

        # 중복 제거 (동일 description)
        seen: set[str] = set()
        unique: list[ActionItem] = []
        for item in items:
            key = item.description.strip().lower()
            if key and key not in seen:
                seen.add(key)
                unique.append(item)

        return unique

    def parse_line(self, line: str) -> Optional[ActionItem]:
        """단일 라인에서 ActionItem 파싱 (빠른 단위 처리용).

        Returns:
            ActionItem 또는 None (태스크 아닌 라인).
        """
        line = line.strip()
        if not line:
            return None

        # 불릿 제거
        desc = self._strip_bullet(line)
        if not desc:
            return None

        return ActionItem(
            description=desc,
            assigned_dept=self._extract_assignee(line),
            due_date=self._extract_due_date(line),
            priority=self._extract_priority(line),
            source_text=line,
            confidence=0.8,
        )

    # ── 섹션 파싱 ─────────────────────────────────────────────────────────

    def _parse_action_sections(self, text: str) -> list[ActionItem]:
        """액션아이템 섹션 헤더 이후 불릿 파싱."""
        items: list[ActionItem] = []
        lines = text.splitlines()
        in_section = False

        for line in lines:
            stripped = line.strip()

            # 헤더 감지
            if self._header_re.search(stripped):
                in_section = True
                # 헤더 라인 자체에 태스크가 포함된 경우 처리
                after_header = self._header_re.sub("", stripped).strip()
                if after_header:
                    item = self._parse_task_line(after_header, confidence=0.95)
                    if item:
                        items.append(item)
                continue

            if in_section:
                # 빈 줄 2개 이상이거나 새로운 헤더 섹션 시작 → 섹션 종료
                if not stripped and len(items) > 0:
                    # 한 번의 빈 줄은 허용, 두 번이면 종료
                    pass
                elif stripped.startswith("##") or stripped.startswith("**") and stripped.endswith("**"):
                    in_section = False
                    continue
                else:
                    item = self._parse_task_line(stripped, confidence=0.95)
                    if item:
                        items.append(item)

        return items

    def _parse_bullet_lines(self, text: str, confidence: float = 0.7) -> list[ActionItem]:
        """전체 텍스트에서 불릿 라인 파싱."""
        items: list[ActionItem] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            item = self._parse_task_line(stripped, confidence=confidence)
            if item:
                items.append(item)
        return items

    def _parse_task_line(self, line: str, confidence: float = 1.0) -> Optional[ActionItem]:
        """단일 라인에서 ActionItem 파싱 시도."""
        desc = self._strip_bullet(line)
        if not desc or len(desc) < 3:
            return None

        return ActionItem(
            description=desc,
            assigned_dept=self._extract_assignee(line),
            due_date=self._extract_due_date(line),
            priority=self._extract_priority(line),
            source_text=line,
            confidence=confidence,
        )

    # ── 추출 헬퍼 ─────────────────────────────────────────────────────────

    def _strip_bullet(self, line: str) -> str:
        """불릿 문자 제거 후 태스크 텍스트 반환."""
        for pattern in self._task_line_res:
            m = pattern.match(line)
            if m:
                return m.group(1).strip()

        # 불릿 없는 일반 라인도 허용 (섹션 내부일 때)
        # 단, 빈 줄이나 헤더 패턴은 제외
        if not line.startswith("#") and not line.startswith("```"):
            return line.strip()
        return ""

    def _extract_assignee(self, text: str) -> Optional[str]:
        """담당자 추출 → org_id 변환."""
        for pattern in self._assignee_res:
            m = pattern.search(text)
            if m:
                raw = m.group(1).strip()
                # org_id 형식인지 확인
                if raw.startswith("aiorg_"):
                    return raw
                # 조직 이름 매핑
                mapped = ORG_NAME_MAP.get(raw)
                if mapped:
                    return mapped
        return None

    def _extract_due_date(self, text: str) -> Optional[str]:
        """마감일 추출 → 표준화 문자열 반환."""
        for pattern in self._due_date_res:
            m = pattern.search(text)
            if m:
                raw = m.group(1).strip()
                # 날짜 형식 정규화: / → -
                normalized = re.sub(r"[/.]", "-", raw)
                # MM/DD 형식이면 현재 연도 추가 (간단 처리)
                if len(normalized.split("-")) == 2:
                    from datetime import date
                    normalized = f"{date.today().year}-{normalized}"
                return normalized
        return None

    def _extract_priority(self, text: str) -> str:
        """우선순위 추출."""
        for level, patterns in self._priority_res.items():
            for pattern in patterns:
                if pattern.search(text):
                    return level
        return "medium"

    # ── 유틸리티 ──────────────────────────────────────────────────────────

    def has_action_items(self, text: str) -> bool:
        """메시지에 액션아이템이 포함되어 있는지 빠른 검사."""
        return bool(self._header_re.search(text))

    def extract_meeting_type(self, text: str) -> Optional[str]:
        """메시지에서 회의 유형 추출.

        Returns:
            "daily_retro" | "weekly_meeting" | None
        """
        lower = text.lower()
        if any(kw in lower for kw in ["일일회고", "daily retro", "데일리", "daily review"]):
            return "daily_retro"
        if any(kw in lower for kw in ["주간회의", "weekly meeting", "주간 미팅", "스탠드업"]):
            return "weekly_meeting"
        return None
