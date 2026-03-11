"""150개 에이전트 중 태스크에 맞는 것 추천 (LLM 없이 키워드 기반)."""
from __future__ import annotations

from pathlib import Path

AGENTS_DIR = Path.home() / ".claude" / "agents"

# 카테고리-키워드 매핑
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "engineering": ["개발", "코드", "구현", "버그", "api", "서버", "백엔드", "프론트", "모바일"],
    "marketing": ["마케팅", "sns", "콘텐츠", "광고", "채널", "캠페인", "브랜드"],
    "design": ["디자인", "ui", "ux", "시각", "브랜딩", "이미지"],
    "testing": ["테스트", "qa", "검증", "버그", "오류"],
    "product": ["기획", "제품", "전략", "로드맵", "피처"],
    "project-management": ["프로젝트", "일정", "관리", "조율"],
    "strategy": ["전략", "분석", "시장", "경쟁"],
    "support": ["지원", "고객", "문의", "응대"],
}


def recommend_agents(task: str, max_agents: int = 3) -> list[str]:
    """태스크 키워드 기반으로 적합한 에이전트 추천."""
    task_lower = task.lower()
    scores: dict[str, int] = {}

    for agent_file in AGENTS_DIR.glob("*.md"):
        name = agent_file.stem
        score = 0

        # 카테고리 매칭
        for category, keywords in CATEGORY_KEYWORDS.items():
            if category in name:
                for kw in keywords:
                    if kw in task_lower:
                        score += 2

        # 에이전트 이름 직접 매칭
        name_parts = name.replace("-", " ").split()
        for part in name_parts:
            if len(part) > 3 and part in task_lower:
                score += 3

        if score > 0:
            scores[name] = score

    if not scores:
        return ["analyst", "executor", "planner"][:max_agents]

    sorted_agents = sorted(scores.items(), key=lambda x: -x[1])
    return [name for name, _ in sorted_agents[:max_agents]]


def list_agents_by_category() -> dict[str, list[str]]:
    """에이전트를 카테고리별로 분류하여 반환."""
    categorized: dict[str, list[str]] = {cat: [] for cat in CATEGORY_KEYWORDS}
    categorized["other"] = []

    for agent_file in sorted(AGENTS_DIR.glob("*.md")):
        name = agent_file.stem
        matched = False
        for category in CATEGORY_KEYWORDS:
            if category in name:
                categorized[category].append(name)
                matched = True
                break
        if not matched:
            categorized["other"].append(name)

    # 빈 카테고리 제거
    return {cat: agents for cat, agents in categorized.items() if agents}
