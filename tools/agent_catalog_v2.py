"""150개 에이전트 중 태스크에 맞는 것 추천 (LLM 기반 + 키워드 fallback)."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from core.pm_decision import PMDecisionClient

AGENTS_DIR = Path.home() / ".claude" / "agents"

# 카테고리-키워드 매핑 (fallback용)
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
    """태스크 키워드 기반으로 적합한 에이전트 추천 (fallback)."""
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
        # 추상 역할명 대신 ~/.claude/agents 실제 페르소나명 사용
        return ["data-analytics-reporter", "engineering-senior-developer", "product-manager"][:max_agents]

    sorted_agents = sorted(scores.items(), key=lambda x: -x[1])
    return [name for name, _ in sorted_agents[:max_agents]]


async def recommend_agents_llm(
    task: str,
    specialties: str,
    max_agents: int = 5,
    *,
    org_id: str = "global",
) -> list[str]:
    """LLM으로 태스크+전문분야 기반 에이전트 추천.
    fallback: 기존 키워드 방식"""
    try:
        # 에이전트 이름 목록만 가져옴 (파일 내용 X, 이름만)
        agent_names = sorted(f.stem for f in AGENTS_DIR.glob("*.md"))
        if not agent_names:
            return recommend_agents(task or specialties, max_agents)

        client = PMDecisionClient(org_id=org_id, engine="auto", session_store=None)

        prompt = (
            f"다음 에이전트 목록에서 주어진 태스크와 전문분야에 가장 적합한 에이전트 {max_agents}개를 선택하세요.\n\n"
            f"에이전트 목록:\n{chr(10).join(agent_names)}\n\n"
            f"태스크: {task}\n"
            f"전문분야: {specialties}\n\n"
            f"응답 형식: JSON 배열만. 예: [\"agent-a\", \"agent-b\"]\n"
            f"반드시 위 목록에 있는 이름만 사용하세요."
        )

        response = await asyncio.wait_for(client.complete(prompt), timeout=12.0)

        # JSON 배열 추출
        text = response.strip()
        start = text.find("[")
        end = text.rfind("]") + 1
        if start >= 0 and end > start:
            candidates = json.loads(text[start:end])
            # 실제 존재하는 에이전트만 필터링
            agent_set = set(agent_names)
            valid = [a for a in candidates if a in agent_set]
            if valid:
                return valid[:max_agents]
    except Exception:
        pass

    return recommend_agents(task or specialties, max_agents)


def recommend_agents_llm_sync(
    task: str,
    specialties: str,
    max_agents: int = 5,
    *,
    org_id: str = "global",
) -> list[str]:
    """recommend_agents_llm의 동기 wrapper."""
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    asyncio.run,
                    recommend_agents_llm(task, specialties, max_agents, org_id=org_id),
                )
                return future.result(timeout=6)
        else:
            return asyncio.run(recommend_agents_llm(task, specialties, max_agents, org_id=org_id))
    except Exception:
        return recommend_agents(task or specialties, max_agents)


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
