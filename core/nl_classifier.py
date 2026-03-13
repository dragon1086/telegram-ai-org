"""2-tier 자연어 분류기.

Tier 1: 키워드 프리필터 — 즉시 매칭 (LLM 호출 없음)
Tier 2: 매칭 실패 시 needs_llm 반환 -> 호출 측에서 엔진에 위임

feature flag: USE_NL_CLASSIFIER 환경변수 (기본: true)
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.keywords import GREETING_KW, ACTION_KW


class Intent(Enum):
    GREETING = "greeting"
    TASK = "task"
    STATUS = "status"
    APPROVE = "approve"
    REJECT = "reject"
    CANCEL = "cancel"
    CHAT = "chat"


COMMAND_PATTERNS: dict[Intent, list[str]] = {
    Intent.STATUS: ["상태", "진행", "status", "어떻게 되고 있", "현황"],
    Intent.APPROVE: ["승인", "approve", "ㅇㅋ", "좋아 반영", "확인했어"],
    Intent.REJECT: ["반려", "reject", "다시 해", "수정해줘", "고쳐줘"],
    Intent.CANCEL: ["취소", "cancel", "그만", "중단", "멈춰"],
}


@dataclass
class ClassifyResult:
    intent: Intent | None  # None = needs_llm
    confidence: float
    source: str  # "keyword", "heuristic", "needs_llm"


class NLClassifier:
    """2-tier 자연어 메시지 분류기."""

    def classify(self, text: str) -> ClassifyResult:
        text_stripped = text.strip()

        # 1) greeting (기존 keywords.py 재활용)
        if any(kw in text_stripped for kw in GREETING_KW) and len(text_stripped) < 15:
            return ClassifyResult(Intent.GREETING, 1.0, "keyword")

        # 2) 명령어 키워드 (짧은 텍스트에서만 — 길면 task일 수 있음)
        has_action = any(kw in text_stripped for kw in ACTION_KW)
        if len(text_stripped) < 30 and not has_action:
            for intent, patterns in COMMAND_PATTERNS.items():
                if any(kw in text_stripped for kw in patterns):
                    return ClassifyResult(intent, 0.9, "keyword")

        # 3) 명확한 명령 키워드 있으면 task
        if has_action:
            return ClassifyResult(Intent.TASK, 0.8, "keyword")

        # 4) 나머지 -> LLM에 위임 (길이 기반 휴리스틱 제거)
        return ClassifyResult(None, 0.0, "needs_llm")
