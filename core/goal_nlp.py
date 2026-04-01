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
당신은 장기목표 등록 전문가입니다.

**1단계: 의도 판단**
사용자 입력이 새로운 장기목표를 "설정/등록/추가/시작"하려는 의도인지 먼저 판단하세요.
아래 경우에는 반드시 {"is_goal": false}만 반환하세요 (다른 내용 없이):
- 질문 (기존 목표 조회, 상태 확인, "됐어?", "어떻게 됐어?" 등)
- 단순 대화, 인사, 감사
- 명령/지시 (특정 작업 수행 요청)
- 기존 목표에 대한 피드백/코멘트

**2단계: 목표 구조화 (is_goal=true인 경우만)**
반드시 아래 JSON 형식으로만 응답하세요 (다른 텍스트 없이):
{
  "is_goal": true,
  "title": "간결한 목표 제목 (20자 이내)",
  "description": "구체적 설명 (목표, 배경, 기대 결과 포함, 2~4문장)",
  "success_criteria": "이 조건이 충족되면 목표 달성으로 본다 (1~2문장, 측정 가능하게)"
}

규칙:
- title: 핵심을 한 줄로. "~하기", "~ 구축" 형태 권장.
- description: 사용자가 언급한 배경·맥락·기대 결과를 포함해 2~4문장으로 정리.
- success_criteria: 언제 "완료"로 볼 수 있는지 구체적이고 측정 가능하게 기술.
- 사용자가 여러 목표를 언급하면 가장 핵심 하나만 추출.
- 불분명한 내용은 합리적으로 추론하되 과도한 해석 금지.
"""


@dataclass
class ParsedGoal:
    title: str
    description: str
    success_criteria: str = ""


async def parse_goal_from_text(
    text: str,
    decision_client: "PMDecisionClient",
) -> ParsedGoal | None:
    """자연어 텍스트에서 장기목표 title/description/success_criteria 추출.

    Returns None if text is not a goal-setting intent or parsing fails.
    """
    prompt = f"사용자 입력:\n{text}\n\n위 내용이 장기목표 등록 요청인지 판단하고 JSON으로 응답하세요."

    raw = ""
    try:
        raw = await decision_client.complete(prompt, system_prompt=_SYSTEM_PROMPT)
        raw = raw.strip()

        # JSON 블록 추출 (```json ... ``` 또는 raw JSON)
        if "```" in raw:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            raw = raw[start:end]

        parsed = json.loads(raw)

        # 의도 게이트: is_goal=false면 등록하지 않음
        if not parsed.get("is_goal", True):
            logger.info(f"[GoalNLP] 목표 등록 의도 아님 — 패스: {text[:80]!r}")
            return None

        title = parsed.get("title", "").strip()
        description = parsed.get("description", "").strip()
        success_criteria = parsed.get("success_criteria", "").strip()

        if not title:
            logger.warning(f"[GoalNLP] title 비어있음: {raw}")
            return None

        return ParsedGoal(
            title=title,
            description=description or title,
            success_criteria=success_criteria,
        )

    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.error(f"[GoalNLP] JSON 파싱 실패: {e} | raw={raw!r:.200}")
        return None
    except Exception as e:
        logger.error(f"[GoalNLP] LLM 호출 실패: {e}")
        return None
