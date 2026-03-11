"""공통 키워드 정의 — 인사/작업 분류에 사용."""
from __future__ import annotations

GREETING_KW = ["안녕", "hi", "hello", "ㅎㅇ", "잘 지내", "뭐해", "있어?", "왔어", "반가"]

ACTION_KW = [
    "작성해", "만들어", "분석해", "구현해", "개발해", "조사해", "생성해", "수정해",
    "고쳐", "빌드", "보고서", "리포트", "기획", "설계", "평가", "검토", "요약", "정리",
    "비교", "추천", "제안", "계획", "전략", "조회", "확인해", "알려줘", "해줘",
]


def is_greeting(text: str) -> bool:
    """짧은 인사말이면 True."""
    return any(kw in text for kw in GREETING_KW) and len(text) < 15


def is_action(text: str) -> bool:
    """작업 요청이면 True."""
    return any(kw in text for kw in ACTION_KW) or len(text) > 20
