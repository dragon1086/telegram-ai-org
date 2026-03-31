"""goal_nlp.py — 자연어 → 장기목표 구조화 LLM 레이어.

사용자가 주절주절 말해도 title + description으로 정리.
PMDecisionClient를 재활용해 LLM 호출.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from core.pm_decision import PMDecisionClient

_SYSTEM_PROMPT = """\
당신은 장기목표 정리 전문가입니다.
사용자의 자연어 입력을 분석해 장기목표로 구조화하세요.

반드시 아래 JSON 형식으로만 응답하세요 (다른 텍스트 없이):
{"title": "간결한 목표 제목 (20자 이내)", "description": "구체적 설명 (목표, 배경, 성공 기준 포함)"}

규칙:
- title: 핵심을 한 줄로. "~하기", "~ 구축" 형태 권장.
- description: 사용자가 언급한 배경·맥락·기대 결과를 포함해 2~4문장으로 정리.
- 사용자가 여러 목표를 언급하면 가장 핵심 하나만 추출 (나머지는 description에 언급).
- 불분명한 내용은 합리적으로 추론하되 과도한 해석 금지.
"""


@dataclass
class ParsedGoal:
    title: str
    description: str


async def parse_goal_from_text(
    text: str,
    decision_client: "PMDecisionClient",
) -> ParsedGoal | None:
    """자연어 텍스트에서 장기목표 title/description 추출.

    Returns None if parsing fails.
    """
    prompt = f"사용자 입력:\n{text}\n\n위 내용을 장기목표로 정리해 JSON으로 응답하세요."

    try:
        raw = await decision_client.complete(prompt, system_prompt=_SYSTEM_PROMPT)
        raw = raw.strip()

        # JSON 블록 추출 (```json ... ``` 또는 raw JSON)
        if "```" in raw:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            raw = raw[start:end]

        parsed = json.loads(raw)
        title = parsed.get("title", "").strip()
        description = parsed.get("description", "").strip()

        if not title:
            logger.warning(f"[GoalNLP] title 비어있음: {raw}")
            return None

        return ParsedGoal(title=title, description=description or title)

    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.error(f"[GoalNLP] JSON 파싱 실패: {e} | raw={raw!r:.200}")
        return None
    except Exception as e:
        logger.error(f"[GoalNLP] LLM 호출 실패: {e}")
        return None
