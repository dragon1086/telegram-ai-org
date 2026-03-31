"""회고(Retro) 텍스트 전용 ActionItem 파서.

일일회고 텍스트에서 RETRO-N 태그, ACTION N: 형식, 체크박스 형식 등을
특화 파싱하여 RetroActionItem 리스트로 반환한다.

지원 패턴:
    1. [RETRO-N] 태그 포함 항목
    2. ACTION N: 설명 형식
    3. - [ ] 설명 체크박스 형식
    4. **해야 할 것**, **다음 조치** 섹션 이후 불릿
    5. ### ⚙️ 개발실 같은 조직별 블록 컨텍스트 기반
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Optional

from goal_tracker.action_parser import ActionItem, ActionParser, ORG_NAME_MAP

logger = logging.getLogger(__name__)

# ── 부서명 → org_id 매핑 (collab_dispatcher와 동일) ─────────────────────────
ORG_DEPT_NAMES: dict[str, str] = {
    "aiorg_engineering_bot": "개발실",
    "aiorg_ops_bot": "운영실",
    "aiorg_design_bot": "디자인실",
    "aiorg_product_bot": "기획실",
    "aiorg_growth_bot": "성장실",
    "aiorg_research_bot": "리서치실",
    "aiorg_pm_bot": "PM",
}

# 조직별 이모지 매핑
ORG_EMOJI_MAP: dict[str, str] = {
    "aiorg_engineering_bot": "⚙️",
    "aiorg_ops_bot": "🔧",
    "aiorg_design_bot": "🎨",
    "aiorg_product_bot": "📋",
    "aiorg_growth_bot": "📈",
    "aiorg_research_bot": "🔍",
    "aiorg_pm_bot": "📌",
}

# RETRO-N 태그 정규식
_RETRO_ID_RE = re.compile(r"\[RETRO-(\d+)\]", re.IGNORECASE)

# 조직 섹션 헤더 정규식 (### ⚙️ 개발실 / ## 개발실 등)
_ORG_HEADER_RE = re.compile(
    r"^#{2,3}\s*"
    r"(?P<emoji>[^\w\s]*\s*)?"
    r"(?P<org_name>" + "|".join(re.escape(k) for k in ORG_NAME_MAP) + r")"
    r"\s*$",
    re.MULTILINE | re.IGNORECASE,
)

# ACTION N: 패턴
_ACTION_N_RE = re.compile(
    r"^(?:\*\*)?ACTION\s*(\d+)\s*[:：]\s*(?:\*\*)?(.+?)(?:\*\*)?$",
    re.MULTILINE | re.IGNORECASE,
)

# 체크박스 패턴
_CHECKBOX_RE = re.compile(
    r"^[-*•]\s+\[[ xX]\]\s+(.+)$",
    re.MULTILINE,
)

# **해야 할 것** / **다음 조치** 섹션 키워드
_ACTION_SECTION_KEYWORDS = [
    r"\*\*해야\s*할\s*것\*\*",
    r"\*\*다음\s*조치\*\*",
    r"\*\*액션\s*아이템\*\*",
    r"\*\*조치\s*사항\*\*",
    r"해야\s*할\s*것\s*[:：]",
    r"다음\s*조치\s*[:：]",
]
_ACTION_SECTION_RE = re.compile(
    "|".join(_ACTION_SECTION_KEYWORDS), re.IGNORECASE
)


@dataclass
class RetroActionItem(ActionItem):
    """회고 텍스트에서 파싱된 조치사항 항목.

    ActionItem을 상속하며 회고 전용 필드를 추가한다.
    """

    retro_id: str = ""        # 예: "RETRO-21"
    org_emoji: str = ""       # 조직 이모지 (예: "⚙️")


class RetroActionParser:
    """회고 텍스트 전용 조치사항 파서.

    기존 ActionParser를 내부적으로 활용하여 코드 재사용하되,
    회고 특화 패턴(RETRO-N 태그, 조직별 블록 등)을 추가 지원한다.

    사용 예::

        parser = RetroActionParser()
        items = parser.parse(retro_text)
        for item in items:
            print(item.description, item.retro_id, item.assigned_dept)
    """

    def __init__(self) -> None:
        self._base_parser = ActionParser()

    # ── 메인 파싱 ─────────────────────────────────────────────────────────

    def parse(self, text: str) -> list[RetroActionItem]:
        """회고 텍스트 전체에서 RetroActionItem 리스트를 파싱.

        파싱 우선순위:
        1. 조직별 블록(### ⚙️ 개발실) 컨텍스트 기반 ACTION N: 패턴
        2. [RETRO-N] 태그 포함 항목
        3. **해야 할 것** 섹션 하위 불릿
        4. - [ ] 체크박스 형식
        5. 전체 텍스트 기반 기존 ActionParser 보완

        Args:
            text: 회고 텍스트 전체 문자열.

        Returns:
            RetroActionItem 리스트 (빈 텍스트 → 빈 리스트).
        """
        if not text or not text.strip():
            return []

        items: list[RetroActionItem] = []
        seen: set[str] = set()

        def _add(item: RetroActionItem) -> None:
            key = item.description.strip().lower()
            if key and key not in seen:
                seen.add(key)
                items.append(item)

        # 1. 조직별 블록 기반 파싱 (가장 높은 신뢰도)
        for item in self._parse_org_blocks(text):
            _add(item)

        # 2. 체크박스 형식
        for item in self._parse_checkboxes(text):
            _add(item)

        # 3. **해야 할 것** 섹션 하위 불릿
        for item in self._parse_action_sections(text):
            _add(item)

        # 4. 기존 ActionParser 보완 (중복 제거 후 추가)
        for base_item in self._base_parser.parse(text):
            retro_item = RetroActionItem(
                description=base_item.description,
                assigned_dept=base_item.assigned_dept,
                due_date=base_item.due_date,
                priority=base_item.priority,
                source_text=base_item.source_text,
                confidence=base_item.confidence * 0.9,  # 낮은 신뢰도
                tags=base_item.tags,
                retro_id=self._extract_retro_id(base_item.source_text),
                org_emoji=ORG_EMOJI_MAP.get(base_item.assigned_dept or "", ""),
            )
            _add(retro_item)

        logger.debug(f"[RetroActionParser] 파싱 완료 — {len(items)}개 항목 추출")
        return items

    def parse_org_block(self, org_name: str, block_text: str) -> list[RetroActionItem]:
        """조직별 블록 텍스트에서 RetroActionItem 파싱.

        Args:
            org_name: 조직 이름 (예: "개발실").
            block_text: 해당 조직 블록 텍스트.

        Returns:
            RetroActionItem 리스트.
        """
        org_id = ORG_NAME_MAP.get(org_name)
        emoji = ORG_EMOJI_MAP.get(org_id or "", "")
        return self._extract_action_items_from_section(block_text, org_id or "", emoji)

    # ── 조직별 블록 파싱 ─────────────────────────────────────────────────

    def _parse_org_blocks(self, text: str) -> list[RetroActionItem]:
        """조직 헤더(### ⚙️ 개발실) 이후 블록에서 액션 아이템 추출."""
        items: list[RetroActionItem] = []
        lines = text.splitlines()
        current_org_id: str | None = None
        current_org_emoji: str = ""
        current_block_lines: list[str] = []

        def _flush_block() -> None:
            if current_org_id and current_block_lines:
                block_text = "\n".join(current_block_lines)
                extracted = self._extract_action_items_from_section(
                    block_text, current_org_id, current_org_emoji
                )
                items.extend(extracted)

        for line in lines:
            stripped = line.strip()
            org_id, emoji = self._extract_org_from_header(stripped)
            if org_id:
                # 이전 블록 처리
                _flush_block()
                current_org_id = org_id
                current_org_emoji = emoji
                current_block_lines = []
            elif current_org_id:
                # 다른 섹션 헤더 만나면 블록 종료 (## 이상 헤더)
                if re.match(r"^#{2,}\s", stripped) and not _ORG_HEADER_RE.match(stripped):
                    _flush_block()
                    current_org_id = None
                    current_org_emoji = ""
                    current_block_lines = []
                else:
                    current_block_lines.append(line)

        _flush_block()
        return items

    # ── 체크박스 파싱 ─────────────────────────────────────────────────────

    def _parse_checkboxes(self, text: str) -> list[RetroActionItem]:
        """- [ ] 체크박스 형식 파싱."""
        items: list[RetroActionItem] = []
        for m in _CHECKBOX_RE.finditer(text):
            desc_raw = m.group(1).strip()
            retro_id = self._extract_retro_id(desc_raw)
            # RETRO-N 태그 제거
            desc = _RETRO_ID_RE.sub("", desc_raw).strip()
            if not desc or len(desc) < 3:
                continue
            assigned = self._base_parser._extract_assignee(desc_raw)
            items.append(
                RetroActionItem(
                    description=desc,
                    assigned_dept=assigned,
                    due_date=self._base_parser._extract_due_date(desc_raw),
                    priority=self._base_parser._extract_priority(desc_raw),
                    source_text=m.group(0),
                    confidence=0.9,
                    retro_id=retro_id,
                    org_emoji=ORG_EMOJI_MAP.get(assigned or "", ""),
                )
            )
        return items

    # ── 섹션 기반 파싱 ───────────────────────────────────────────────────

    def _parse_action_sections(self, text: str) -> list[RetroActionItem]:
        """**해야 할 것** 등 섹션 이후 불릿에서 항목 추출."""
        items: list[RetroActionItem] = []
        lines = text.splitlines()
        in_section = False

        for line in lines:
            stripped = line.strip()
            if _ACTION_SECTION_RE.search(stripped):
                in_section = True
                continue
            if in_section:
                if re.match(r"^#{1,4}\s", stripped) or re.match(r"^\*\*[^*]+\*\*\s*$", stripped):
                    in_section = False
                    continue
                if not stripped:
                    continue
                # 불릿 라인
                base_item = self._base_parser._parse_task_line(stripped, confidence=0.85)
                if base_item:
                    retro_id = self._extract_retro_id(stripped)
                    items.append(
                        RetroActionItem(
                            description=base_item.description,
                            assigned_dept=base_item.assigned_dept,
                            due_date=base_item.due_date,
                            priority=base_item.priority,
                            source_text=stripped,
                            confidence=0.85,
                            retro_id=retro_id,
                            org_emoji=ORG_EMOJI_MAP.get(base_item.assigned_dept or "", ""),
                        )
                    )
        return items

    # ── 섹션 액션 추출 ────────────────────────────────────────────────────

    def _extract_action_items_from_section(
        self,
        text: str,
        assigned_dept: str,
        org_emoji: str = "",
    ) -> list[RetroActionItem]:
        """섹션 텍스트에서 ACTION N: 및 불릿 형식 액션 아이템 추출.

        Args:
            text: 조직 블록 텍스트.
            assigned_dept: 해당 조직 org_id.
            org_emoji: 조직 이모지.

        Returns:
            RetroActionItem 리스트.
        """
        items: list[RetroActionItem] = []

        # ACTION N: 형식 우선
        for m in _ACTION_N_RE.finditer(text):
            desc = m.group(2).strip().strip("*").strip()
            retro_id = self._extract_retro_id(desc)
            desc_clean = _RETRO_ID_RE.sub("", desc).strip()
            if not desc_clean or len(desc_clean) < 3:
                continue
            items.append(
                RetroActionItem(
                    description=desc_clean,
                    assigned_dept=assigned_dept or None,
                    priority=self._base_parser._extract_priority(desc_clean),
                    source_text=m.group(0),
                    confidence=0.95,
                    retro_id=retro_id,
                    org_emoji=org_emoji,
                )
            )

        # 체크박스
        for m in _CHECKBOX_RE.finditer(text):
            desc_raw = m.group(1).strip()
            retro_id = self._extract_retro_id(desc_raw)
            desc = _RETRO_ID_RE.sub("", desc_raw).strip()
            if not desc or len(desc) < 3:
                continue
            items.append(
                RetroActionItem(
                    description=desc,
                    assigned_dept=assigned_dept or self._base_parser._extract_assignee(desc_raw),
                    due_date=self._base_parser._extract_due_date(desc_raw),
                    priority=self._base_parser._extract_priority(desc_raw),
                    source_text=m.group(0),
                    confidence=0.9,
                    retro_id=retro_id,
                    org_emoji=org_emoji,
                )
            )

        # 기본 불릿 (ACTION N 없을 때 보완)
        if not items:
            for line in text.splitlines():
                stripped = line.strip()
                if not stripped or re.match(r"^#{1,4}\s", stripped):
                    continue
                base_item = self._base_parser._parse_task_line(stripped, confidence=0.8)
                if base_item:
                    retro_id = self._extract_retro_id(stripped)
                    items.append(
                        RetroActionItem(
                            description=base_item.description,
                            assigned_dept=assigned_dept or base_item.assigned_dept,
                            due_date=base_item.due_date,
                            priority=base_item.priority,
                            source_text=stripped,
                            confidence=0.8,
                            retro_id=retro_id,
                            org_emoji=org_emoji,
                        )
                    )

        return items

    # ── 추출 헬퍼 ─────────────────────────────────────────────────────────

    def _extract_retro_id(self, text: str) -> str:
        """[RETRO-N] 형식 태그 추출.

        Args:
            text: 검색 대상 텍스트.

        Returns:
            "RETRO-N" 형식 문자열. 없으면 빈 문자열.
        """
        m = _RETRO_ID_RE.search(text)
        if m:
            return f"RETRO-{m.group(1)}"
        return ""

    def _extract_org_from_header(self, header: str) -> tuple[str, str]:
        """조직 헤더에서 (org_id, emoji) 추출.

        Args:
            header: "### ⚙️ 개발실" 같은 헤더 라인.

        Returns:
            (org_id, emoji) 튜플. 조직 헤더가 아니면 ("", "").
        """
        m = _ORG_HEADER_RE.match(header)
        if not m:
            return "", ""
        org_name = m.group("org_name").strip()
        emoji_raw = (m.group("emoji") or "").strip()
        org_id = ORG_NAME_MAP.get(org_name, "")
        emoji = emoji_raw or ORG_EMOJI_MAP.get(org_id, "")
        return org_id, emoji
