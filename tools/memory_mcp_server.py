#!/usr/bin/env python3
"""
stdio MCP 서버 — ContextDB + BM25 메모리 검색을 Claude Code에 노출.

실행 방법:
  python tools/memory_mcp_server.py

환경변수:
  DB_PATH  — ContextDB sqlite 파일 경로 (필수)
  BOT_ID   — 봇 식별자 (선택, 로깅용)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcp.server.fastmcp import FastMCP  # noqa: E402

DB_PATH = os.environ.get("DB_PATH", str(Path.home() / ".ai-org" / "context.db"))
BOT_ID = os.environ.get("BOT_ID", "unknown")

mcp = FastMCP(f"memory-{BOT_ID}")


def _get_context_db():
    """ContextDB 인스턴스 반환."""
    from core.context_db import ContextDB
    return ContextDB(DB_PATH)


def _get_memory_manager():
    """MemoryManager 인스턴스 반환 (scope=BOT_ID)."""
    from core.memory_manager import MemoryManager
    mm = MemoryManager(scope=BOT_ID)
    mm._context_db = _get_context_db()
    return mm


@mcp.tool()
async def search_memories(query: str, top_k: int = 5) -> str:
    """
    BM25로 관련 기억을 검색한다 (MemoryManager LOG + 대화 이력 통합).

    Args:
        query: 검색 쿼리 (자연어)
        top_k: 반환할 최대 결과 수

    Returns:
        관련 기억 목록 (줄바꿈 구분)
    """
    try:
        mm = _get_memory_manager()
        results = await mm.search_memories(query=query, top_k=top_k)
        if not results:
            return "관련 기억 없음"
        return "\n---\n".join(results)
    except Exception as e:
        return f"검색 오류: {e}"


@mcp.tool()
async def get_recent_conversation(limit: int = 10, human_only: bool = True) -> str:
    """
    최근 대화 이력을 반환한다.

    Args:
        limit: 반환할 최대 메시지 수
        human_only: True면 사람 메시지만 (봇 메시지 제외)

    Returns:
        최근 대화 목록 (시간순)
    """
    try:
        db = _get_context_db()
        is_bot = False if human_only else None
        rows = await db.get_conversation_messages(is_bot=is_bot, limit=limit)
        if not rows:
            return "대화 이력 없음"
        lines = []
        for r in reversed(rows):  # 오래된 것부터
            ts = r.get("timestamp", "")[:16]
            role = "봇" if r.get("is_bot") else "사용자"
            content = r.get("content", "")[:300]
            lines.append(f"[{ts}] {role}: {content}")
        return "\n".join(lines)
    except Exception as e:
        return f"조회 오류: {e}"


@mcp.tool()
async def get_bot_context(scope: str = "CORE") -> str:
    """
    봇의 저장된 메모리 컨텍스트를 반환한다.

    Args:
        scope: 메모리 스코프 (CORE, SUMMARY, LOG) — 현재 build_context()에 반영됨

    Returns:
        해당 스코프의 메모리 내용
    """
    try:
        mm = _get_memory_manager()
        context = mm.build_context()
        if not context:
            return "저장된 컨텍스트 없음"
        return context[:3000]
    except Exception as e:
        return f"컨텍스트 조회 오류: {e}"


@mcp.tool()
async def remember(content: str, scope: str = "LOG") -> str:
    """
    새 기억을 MemoryManager에 저장한다.

    Args:
        content: 저장할 내용
        scope: 저장할 스코프 (LOG, SUMMARY, CORE)

    Returns:
        저장 완료 메시지
    """
    try:
        mm = _get_memory_manager()
        if scope.upper() == "CORE":
            mm.add_core(content)
            return "기억 저장 완료 (scope=CORE)"
        else:
            importance = await mm.add_log(content)
            return f"기억 저장 완료 (scope={scope}, importance={importance})"
    except Exception as e:
        return f"저장 오류: {e}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
