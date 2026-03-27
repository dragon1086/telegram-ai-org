"""
l2_to_l3_archiver.py — L2 만료 항목 감지 및 L3 아카이브 이관

Phase 3: L2 항목 중 만료 조건에 해당하는 항목을 감지하고,
JSON Lines 형식으로 L3 아카이브 파일에 기록한 뒤
남은 유효 L2 항목 목록을 반환한다.

만료 우선순위:
  1. explicit_expiry — item.expired == True
  2. score_below_min — score < 0.3
  3. ttl_expired     — (today - last_accessed).days > ttl_days
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from loguru import logger

from core.l2_context_filter import L2Item

# ──────────────────────────────────────────────
# 상수
# ──────────────────────────────────────────────

SCORE_MIN: float = 0.3  # score < 0.3 → score_below_min 만료

ArchiveReason = Literal["ttl_expired", "score_below_min", "explicit_expiry"]


# ──────────────────────────────────────────────
# 데이터클래스
# ──────────────────────────────────────────────


@dataclass
class L3ArchiveEntry:
    """L3 아카이브에 기록되는 만료 L2 항목."""

    id: str
    source_l2_id: str
    title: str
    archived_at: str      # ISO date string
    reason: str           # "ttl_expired" | "score_below_min" | "explicit_expiry"
    original_score: float
    original_ttl_days: int


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────


def is_expired(
    item: L2Item,
    today: date | None = None,
) -> tuple[bool, str]:
    """L2Item 의 만료 여부와 이유를 반환한다.

    만료 판정 우선순위:
      1. item.expired == True (명시적 만료) → "explicit_expiry"
      2. item.score < 0.3                   → "score_below_min"
      3. (today - last_accessed).days > ttl_days → "ttl_expired"
      4. 해당 없음 → (False, "")

    Args:
        item:  검사할 L2Item.
        today: 기준 날짜. None 이면 date.today() 사용.

    Returns:
        (is_expired: bool, reason: str)
    """
    if today is None:
        today = date.today()

    # 1) 명시적 만료 플래그 (optional attribute)
    if getattr(item, "expired", False):
        return True, "explicit_expiry"

    # 2) 점수 미달
    if item.score < SCORE_MIN:
        return True, "score_below_min"

    # 3) TTL 초과
    try:
        last_accessed_date = datetime.fromisoformat(item.last_accessed).date()
    except ValueError:
        # 날짜 파싱 실패 시 보수적으로 만료 처리
        logger.warning(
            "[L2→L3] Cannot parse last_accessed '{}' for item {}; treating as ttl_expired",
            item.last_accessed,
            item.id,
        )
        return True, "ttl_expired"

    days_elapsed = (today - last_accessed_date).days
    if days_elapsed > item.ttl_days:
        return True, "ttl_expired"

    return False, ""


def archive_expired_items(
    items: list[L2Item],
    archive_path: Path | None = None,
    today: date | None = None,
) -> tuple[list[L3ArchiveEntry], list[L2Item]]:
    """만료 L2 항목을 L3 아카이브로 이관하고 남은 유효 항목을 반환한다.

    Args:
        items:        검사할 L2Item 리스트.
        archive_path: JSON Lines 아카이브 파일 경로.
                      지정 시 만료 항목을 해당 파일에 추가(append) 기록한다.
        today:        기준 날짜. None 이면 date.today() 사용.

    Returns:
        (archived_entries, remaining_l2_items)
        - archived_entries: 만료되어 아카이브된 L3ArchiveEntry 리스트
        - remaining_l2_items: 유효한 L2Item 리스트 (원래 순서 유지)
    """
    if today is None:
        today = date.today()

    today_str = today.isoformat()

    archived: list[L3ArchiveEntry] = []
    remaining: list[L2Item] = []

    for item in items:
        expired, reason = is_expired(item, today=today)

        if expired:
            # L3ArchiveEntry id: "L3-{source_l2_id}"
            entry = L3ArchiveEntry(
                id=f"L3-{item.id}",
                source_l2_id=item.id,
                title=item.title,
                archived_at=today_str,
                reason=reason,
                original_score=item.score,
                original_ttl_days=item.ttl_days,
            )
            archived.append(entry)

            logger.info(
                "[L2→L3] Archived {}: {} (score={:.2f}, ttl={}d)",
                item.id,
                reason,
                item.score,
                item.ttl_days,
            )
        else:
            remaining.append(item)

    # 아카이브 파일에 기록 (append 모드)
    if archive_path is not None and archived:
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        with archive_path.open("a", encoding="utf-8") as fh:
            for entry in archived:
                fh.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")

    return archived, remaining
