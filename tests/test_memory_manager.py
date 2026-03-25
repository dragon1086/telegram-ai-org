"""MemoryManager BM25 검색 테스트."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.memory_manager import MemoryManager


@pytest.mark.asyncio
async def test_search_memories_returns_relevant_results(tmp_path, monkeypatch):
    """BM25 검색이 관련 결과를 반환하는지"""
    # MemoryManager의 MEMORY_DIR을 tmp_path로 교체
    import core.memory_manager as mm_module
    monkeypatch.setattr(mm_module, "MEMORY_DIR", tmp_path / "memory")

    mm = MemoryManager(scope="test_scope")
    # LOG에 항목 삽입
    await mm.add_log("Python asyncio 비동기 프로그래밍 기초")
    await mm.add_log("JavaScript 프론트엔드 React 컴포넌트")
    await mm.add_log("asyncio event loop 활용 방법")

    results = await mm.search_memories("asyncio 비동기", top_k=2)
    assert isinstance(results, list)
    assert len(results) <= 2
    assert any("asyncio" in r for r in results)


@pytest.mark.asyncio
async def test_search_memories_bm25_finds_relevant(tmp_path, monkeypatch):
    """BM25 검색이 관련 결과를 더 잘 찾는지"""
    import core.memory_manager as mm_module
    monkeypatch.setattr(mm_module, "MEMORY_DIR", tmp_path / "memory")

    mm = MemoryManager(scope="test_scope")
    await mm.add_log("Python asyncio 비동기 프로그래밍")
    await mm.add_log("Django REST API 서버 구축")
    await mm.add_log("Flask 웹 프레임워크 기초")

    results = await mm.search_memories("Python asyncio", top_k=3)
    assert isinstance(results, list)
    # asyncio 관련 항목이 결과에 포함돼야 함
    assert any("asyncio" in r or "Python" in r for r in results)


@pytest.mark.asyncio
async def test_search_memories_empty_corpus(tmp_path, monkeypatch):
    """항목 없을 때 빈 리스트 반환"""
    import core.memory_manager as mm_module
    monkeypatch.setattr(mm_module, "MEMORY_DIR", tmp_path / "memory")

    mm = MemoryManager(scope="test_scope")
    results = await mm.search_memories("asyncio 비동기", top_k=2)
    assert results == []


@pytest.mark.asyncio
async def test_search_memories_includes_conversation_entries(tmp_path, monkeypatch):
    """BM25 검색이 _context_db conversation_messages도 포함하는지"""
    from unittest.mock import AsyncMock

    import core.memory_manager as mm_module
    monkeypatch.setattr(mm_module, "MEMORY_DIR", tmp_path / "memory")

    mm = MemoryManager(scope="test_scope")
    mm._context_db = AsyncMock()
    mm._context_db.get_conversation_messages = AsyncMock(
        return_value=[{"content": "Django REST API 구축 완료"}]
    )
    await mm.add_log("Flask 웹 프레임워크 기초")
    await mm.add_log("Python 기초 문법 학습")

    results = await mm.search_memories("REST API Django", top_k=2)
    assert any("Django" in r for r in results)
