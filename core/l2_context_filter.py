"""
l2_context_filter.py — L2 중기 기억 항목 필터링 및 컨텍스트 직렬화

Phase 2: L2 항목을 점수 기준으로 필터링하고,
세션 시작 시 컨텍스트 주입(inject)에 사용할 마크다운 형식으로 직렬화한다.

주의: 이 모듈의 score 스케일은 0.0~1.0 (MEMORY.md 기준).
      core/scoring_rules.py 의 0~100 스케일과 다름 — 임포트 금지.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class L2Item:
    """L2 중기 기억 계층 항목."""

    id: str
    title: str
    created_at: str        # ISO date string, e.g. "2026-03-27"
    last_accessed: str     # ISO date string, e.g. "2026-03-27"
    ttl_days: int
    score: float           # 0.0 ~ 1.0


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────


def filter_l2_items(
    items: list[L2Item],
    threshold: float = 0.5,
    top_n: int = 10,
) -> list[L2Item]:
    """threshold 이상의 score를 가진 항목을 score 내림차순으로 반환한다.

    Args:
        items:     L2Item 리스트.
        threshold: 최소 score (이상인 항목만 통과). 기본값 0.5.
        top_n:     반환 최대 개수. 0이면 제한 없음. 기본값 10.

    Returns:
        필터링·정렬된 L2Item 리스트.
        동점(score 동일) 시 id 내림차순(문자열 역순)으로 정렬하여 결정론적 순서 보장.
    """
    if not items:
        return []

    passed = [item for item in items if item.score >= threshold]
    if not passed:
        return []

    # score 내림차순 정렬; 동점 시 id 내림차순(역순)으로 안정적 결정론적 순서
    passed.sort(key=lambda item: (item.score, item.id), reverse=True)

    if top_n > 0:
        return passed[:top_n]
    return passed


def serialize_context(items: list[L2Item]) -> str:
    """L2Item 리스트를 마크다운 컨텍스트 주입 형식으로 직렬화한다.

    Args:
        items: 직렬화할 L2Item 리스트 (이미 필터링·정렬 완료된 것으로 가정).

    Returns:
        마크다운 문자열. 항목이 없으면 빈 문자열 반환.
    """
    if not items:
        return ""

    lines: list[str] = [
        "## L2 중기 기억 컨텍스트",
        "",
        "| id | title | last_accessed | ttl_days | score |",
        "|----|-------|---------------|----------|-------|",
    ]
    for item in items:
        lines.append(
            f"| {item.id} | {item.title} | {item.last_accessed}"
            f" | {item.ttl_days} | {item.score:.2f} |"
        )

    return "\n".join(lines)


def inject_l2_context(
    items: list[L2Item],
    threshold: float = 0.5,
    top_n: int = 10,
) -> str:
    """filter_l2_items + serialize_context 를 한 번에 호출하는 편의 함수.

    Args:
        items:     L2Item 리스트.
        threshold: filter_l2_items 에 전달할 최소 score. 기본값 0.5.
        top_n:     filter_l2_items 에 전달할 최대 반환 개수. 기본값 10.

    Returns:
        마크다운 컨텍스트 문자열. 조건을 충족하는 항목이 없으면 빈 문자열.
    """
    filtered = filter_l2_items(items, threshold=threshold, top_n=top_n)
    return serialize_context(filtered)
