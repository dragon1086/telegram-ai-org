"""GoalConversationEngine — 자연어 → 구조화 OKR 변환 엔진.

PM 봇 내부 모듈. 사용자의 자연어 목표 설명을 받아
LLM을 활용하여 측정 가능한 OKR(Objective → KR → Initiative) 구조로 변환한다.

사용 흐름:
    1. 사용자가 자연어로 목표 기술 (예: "이번 분기 MAU 10만 달성하자")
    2. GoalConversationEngine.parse_goal()이 LLM 호출
    3. 구조화된 OKR dict 반환
    4. GoalTracker의 create_objective/create_key_result/create_initiative로 등록
"""
from __future__ import annotations

import json
import re

from loguru import logger

# LLM 프롬프트 — 자연어 목표를 OKR JSON으로 변환
OKR_PARSE_PROMPT = """당신은 OKR(Objectives and Key Results) 전문가입니다.
사용자의 목표 설명을 분석하여 구조화된 OKR로 변환하세요.

## 규칙
1. Objective: 정성적이고 영감을 주는 목표 (1개)
2. Key Results: 측정 가능한 핵심 결과 (1~3개)
   - 각 KR에는 kpi_metric, kpi_target, kpi_unit, deadline, weight 포함
3. Initiatives: KR 달성을 위한 구체적 실행 계획 (각 KR당 0~2개)

## 출력 형식 (JSON)
```json
{
  "objective": {
    "title": "...",
    "description": "...",
    "deadline": "YYYY-MM-DD"
  },
  "key_results": [
    {
      "title": "...",
      "description": "...",
      "kpi_metric": "...",
      "kpi_target": 숫자,
      "kpi_unit": "...",
      "deadline": "YYYY-MM-DD",
      "weight": 0.0~1.0,
      "initiatives": [
        {"title": "...", "description": "...", "deadline": "YYYY-MM-DD"}
      ]
    }
  ]
}
```

weight 합계는 1.0이 되어야 합니다.
deadline이 명시되지 않으면 분기 말(3/6/9/12월 말일)로 설정하세요.
KPI가 불분명하면 합리적인 지표를 제안하세요.

## 사용자 목표 설명:
{user_input}
"""

# KR이 없거나 불완전한 경우 후속 질문
FOLLOWUP_QUESTIONS = {
    "no_metric": "이 목표의 성공을 어떻게 측정할 수 있을까요? (예: 매출, 사용자 수, 완료율 등)",
    "no_deadline": "이 목표의 마감 기한은 언제인가요? (예: 이번 분기, 6월 말, 연말 등)",
    "no_target": "목표 수치는 어느 정도인가요? (예: 10만명, 50%, 100건 등)",
}


class GoalConversationEngine:
    """자연어 목표를 OKR 구조로 변환하는 엔진.

    LLM 의존적 파싱과 규칙 기반 파싱 모두 지원.
    """

    def __init__(self, llm_func=None):
        """초기화.

        Args:
            llm_func: LLM 호출 함수. async (prompt: str) -> str.
                      None이면 규칙 기반 파싱만 사용.
        """
        self._llm = llm_func

    async def parse_goal(self, user_input: str) -> dict:
        """자연어 목표 → 구조화 OKR 변환.

        LLM 사용 가능하면 LLM 파싱, 아니면 규칙 기반 파싱.

        Args:
            user_input: 사용자 자연어 목표 설명.

        Returns:
            OKR 구조 dict:
            {
                "objective": {"title", "description", "deadline"},
                "key_results": [{"title", "kpi_metric", "kpi_target", ...}],
                "needs_followup": bool,
                "followup_questions": [str],
            }
        """
        if self._llm:
            return await self._parse_with_llm(user_input)
        return self._parse_with_rules(user_input)

    async def _parse_with_llm(self, user_input: str) -> dict:
        """LLM 기반 OKR 파싱."""
        prompt = OKR_PARSE_PROMPT.replace("{user_input}", user_input)
        try:
            response = await self._llm(prompt)
            parsed = self._extract_json(response)
            if parsed:
                parsed["needs_followup"] = False
                parsed["followup_questions"] = []
                return parsed
        except Exception as e:
            logger.warning(f"[GoalConversationEngine] LLM 파싱 실패: {e}")

        # LLM 실패 → 규칙 기반 폴백
        return self._parse_with_rules(user_input)

    def _parse_with_rules(self, user_input: str) -> dict:
        """규칙 기반 OKR 파싱 (LLM 없이).

        자연어에서 숫자, 날짜, 키워드를 추출하여 기본 OKR 구조 생성.
        """
        title = user_input.strip()[:80]
        description = user_input.strip()

        # 날짜 추출 (숫자 추출보다 먼저 — 날짜를 제거한 후 숫자 추출)
        dates = re.findall(r'(\d{4}[-./]\d{1,2}[-./]\d{1,2})', user_input)
        # 날짜/분기를 제거한 텍스트에서 숫자 추출 (KPI target 후보)
        text_clean = re.sub(r'\d{4}[-./]\d{1,2}[-./]\d{1,2}', '', user_input)
        text_clean = re.sub(r'Q[1-4]', '', text_clean)
        numbers = re.findall(r'(\d[\d,.]*)\s*(만|천|억|명|%|건|개|원)?', text_clean)
        # 분기 추출
        quarter = re.findall(r'(Q[1-4]|[1-4]분기|이번\s*분기|다음\s*분기)', user_input)

        deadline = dates[0].replace('/', '-').replace('.', '-') if dates else None
        if not deadline and quarter:
            deadline = self._quarter_to_date(quarter[0])

        followup_questions = []
        kpi_target = None
        kpi_unit = None

        if numbers:
            raw_num, unit = numbers[0]
            kpi_target = self._parse_korean_number(raw_num, unit)
            kpi_unit = unit or "건"
        else:
            followup_questions.append(FOLLOWUP_QUESTIONS["no_target"])

        if not deadline:
            followup_questions.append(FOLLOWUP_QUESTIONS["no_deadline"])

        # KPI 지표 추론
        kpi_metric = self._infer_metric(user_input)
        if not kpi_metric:
            followup_questions.append(FOLLOWUP_QUESTIONS["no_metric"])
            kpi_metric = "completion_rate"

        result = {
            "objective": {
                "title": title,
                "description": description,
                "deadline": deadline or "2026-12-31",
            },
            "key_results": [
                {
                    "title": f"{title} 달성",
                    "description": f"{title} KR",
                    "kpi_metric": kpi_metric,
                    "kpi_target": kpi_target or 100,
                    "kpi_unit": kpi_unit or "%",
                    "deadline": deadline or "2026-12-31",
                    "weight": 1.0,
                    "initiatives": [],
                },
            ],
            "needs_followup": len(followup_questions) > 0,
            "followup_questions": followup_questions,
        }
        return result

    def _extract_json(self, text: str) -> dict | None:
        """LLM 응답에서 JSON 추출."""
        # ```json ... ``` 블록 찾기
        match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        # 직접 JSON 파싱 시도
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # { ... } 블록 찾기
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return None

    def _quarter_to_date(self, q: str) -> str:
        """분기 표현 → 마감일."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        year = now.year

        if "1" in q or "Q1" in q:
            return f"{year}-03-31"
        if "2" in q or "Q2" in q:
            return f"{year}-06-30"
        if "3" in q or "Q3" in q:
            return f"{year}-09-30"
        if "4" in q or "Q4" in q:
            return f"{year}-12-31"
        # "이번 분기" → 현재 분기 말
        month = now.month
        if month <= 3:
            return f"{year}-03-31"
        if month <= 6:
            return f"{year}-06-30"
        if month <= 9:
            return f"{year}-09-30"
        return f"{year}-12-31"

    def _parse_korean_number(self, raw: str, unit: str | None) -> float:
        """한국어 숫자 파싱 (10만 → 100000)."""
        num = float(raw.replace(',', '').replace('.', ''))
        if unit == "만":
            num *= 10000
        elif unit == "천":
            num *= 1000
        elif unit == "억":
            num *= 100000000
        return num

    def _infer_metric(self, text: str) -> str | None:
        """텍스트에서 KPI 지표 추론."""
        metric_keywords = {
            "mau": ["MAU", "mau", "월간활성", "월활"],
            "dau": ["DAU", "dau", "일간활성", "일활"],
            "revenue": ["매출", "수익", "revenue", "매출액"],
            "signups": ["가입", "신규가입", "회원가입", "signup"],
            "downloads": ["다운로드", "설치", "download"],
            "retention": ["리텐션", "retention", "잔존율", "유지율"],
            "nps": ["NPS", "nps", "추천지수"],
            "conversion": ["전환율", "conversion", "CVR", "전환"],
        }
        for metric, keywords in metric_keywords.items():
            for kw in keywords:
                if kw in text:
                    return metric
        return None


async def register_parsed_okr(
    tracker,
    parsed: dict,
    chat_id: int = 0,
) -> dict:
    """파싱된 OKR 구조를 GoalTracker에 등록.

    Args:
        tracker: GoalTracker 인스턴스.
        parsed: GoalConversationEngine.parse_goal() 반환값.
        chat_id: Telegram 채팅방 ID.

    Returns:
        {"objective_id": str, "kr_ids": [str], "initiative_ids": [str]}
    """
    obj_data = parsed["objective"]
    obj_id = await tracker.create_objective(
        title=obj_data["title"],
        description=obj_data.get("description", ""),
        deadline=obj_data["deadline"],
        chat_id=chat_id,
    )

    kr_ids = []
    initiative_ids = []

    for kr_data in parsed.get("key_results", []):
        kr_id = await tracker.create_key_result(
            title=kr_data["title"],
            description=kr_data.get("description", ""),
            parent_objective_id=obj_id,
            deadline=kr_data.get("deadline", obj_data["deadline"]),
            kpi_metric=kr_data.get("kpi_metric"),
            kpi_target=kr_data.get("kpi_target"),
            kpi_unit=kr_data.get("kpi_unit"),
            weight=kr_data.get("weight", 1.0),
        )
        kr_ids.append(kr_id)

        for init_data in kr_data.get("initiatives", []):
            init_id = await tracker.create_initiative(
                title=init_data["title"],
                description=init_data.get("description", ""),
                parent_kr_id=kr_id,
                deadline=init_data.get("deadline"),
            )
            initiative_ids.append(init_id)

    return {
        "objective_id": obj_id,
        "kr_ids": kr_ids,
        "initiative_ids": initiative_ids,
    }
