"""Telegram bot command definitions for canonical org bots."""
from __future__ import annotations

from telegram import BotCommand


COMMON_COMMANDS = [
    BotCommand("start", "봇 시작/소개"),
    BotCommand("status", "봇 상태 확인"),
    BotCommand("org", "조직 정체성 조회/설정"),
    BotCommand("pm", "조직 정체성 설정(호환)"),
    BotCommand("prompt", "시스템 프롬프트 조회/수정"),
    BotCommand("team", "현재 팀 전략 확인"),
    BotCommand("agents", "에이전트 목록"),
    BotCommand("sessions", "세션 현황 확인"),
    BotCommand("verbose", "텔레그램 진행 노출 레벨"),
    BotCommand("context_budget", "세션 예산 요약"),
    BotCommand("session_policy", "세션 정책 확인"),
    BotCommand("compact", "세션 압축/정리"),
    BotCommand("reset_session", "세션 메타데이터 초기화"),
    BotCommand("reset", "세션 초기화"),
    BotCommand("help", "명령어 안내"),
]

ORCHESTRATOR_ONLY_COMMANDS = [
    BotCommand("setup", "새 조직 봇 등록 마법사"),
    BotCommand("stop_tasks", "진행 중인 작업 전체 종료"),
    BotCommand("restart", "봇 전체 재시작"),
    BotCommand("set_engine", "엔진 변경 (예: /set_engine claude-code)"),
]


def get_bot_commands(kind: str) -> list[BotCommand]:
    if kind == "orchestrator":
        return [*COMMON_COMMANDS[:2], *ORCHESTRATOR_ONLY_COMMANDS, *COMMON_COMMANDS[2:]]
    return list(COMMON_COMMANDS)
