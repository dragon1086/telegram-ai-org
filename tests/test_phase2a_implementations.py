"""tests/test_phase2a_implementations.py — Phase 2a 구현 단위 테스트.

대상:
  - MessageRepository: initialize → save → get_by_task → get_recent (:memory: DB)
  - DispatchService: dispatch / get_dispatch_status / cancel_dispatch (mock 사용)
  - eval_context: inject_eval_context() 반환값 검증
  - run_error_gotcha: 핵심 로직 함수 단위 테스트
  - ENABLE_REPOSITORY_PATTERN=0 시 MessageRepository.save() no-op 확인
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# 프로젝트 루트를 sys.path에 추가
# ─────────────────────────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ─────────────────────────────────────────────────────────────────────────────
# MessageRepository 테스트
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def enable_repo_pattern(monkeypatch):
    """ENABLE_REPOSITORY_PATTERN=1 로 설정."""
    monkeypatch.setenv("ENABLE_REPOSITORY_PATTERN", "1")
    # 모듈 레벨 상수를 직접 패치
    import core.repositories.message_repository as mod
    monkeypatch.setattr(mod, "ENABLE_REPOSITORY_PATTERN", True)
    return mod


@pytest.fixture()
def disable_repo_pattern(monkeypatch):
    """ENABLE_REPOSITORY_PATTERN=0 으로 설정."""
    monkeypatch.setenv("ENABLE_REPOSITORY_PATTERN", "0")
    import core.repositories.message_repository as mod
    monkeypatch.setattr(mod, "ENABLE_REPOSITORY_PATTERN", False)
    return mod


@pytest.mark.asyncio
async def test_message_repo_initialize_and_save(enable_repo_pattern):
    """initialize → save → get_by_task 정상 동작 확인."""
    from core.repositories.message_repository import MessageRepository

    repo = MessageRepository(db_path=":memory:")
    await repo.initialize()

    msg = {
        "task_id": "t-001",
        "content": "테스트 메시지",
        "sender": "bot",
        "timestamp": "2026-03-29T12:00:00",
    }
    await repo.save(msg)

    results = await repo.get_by_task("t-001")
    assert len(results) == 1
    assert results[0]["task_id"] == "t-001"
    assert results[0]["content"] == "테스트 메시지"
    assert results[0]["sender"] == "bot"


@pytest.mark.asyncio
async def test_message_repo_get_recent(enable_repo_pattern):
    """여러 메시지 저장 후 get_recent가 최신순으로 반환하는지 확인."""
    from core.repositories.message_repository import MessageRepository

    repo = MessageRepository(db_path=":memory:")
    await repo.initialize()

    for i in range(5):
        await repo.save(
            {
                "task_id": f"t-{i:03d}",
                "content": f"msg {i}",
                "timestamp": f"2026-03-29T12:00:0{i}",
                "created_at": float(i),
            }
        )

    recent = await repo.get_recent(limit=3)
    assert len(recent) == 3
    # DESC 정렬이므로 created_at이 큰 것부터
    assert recent[0]["content"] == "msg 4"
    assert recent[1]["content"] == "msg 3"


@pytest.mark.asyncio
async def test_message_repo_get_by_task_empty(enable_repo_pattern):
    """존재하지 않는 task_id 조회 시 빈 리스트 반환."""
    from core.repositories.message_repository import MessageRepository

    repo = MessageRepository(db_path=":memory:")
    await repo.initialize()

    results = await repo.get_by_task("nonexistent")
    assert results == []


@pytest.mark.asyncio
async def test_message_repo_disabled_noop(disable_repo_pattern):
    """ENABLE_REPOSITORY_PATTERN=0 일 때 save가 no-op으로 동작하는지 확인."""
    from core.repositories.message_repository import MessageRepository

    repo = MessageRepository(db_path=":memory:")
    # initialize는 no-op (테이블 미생성)
    await repo.initialize()

    # save도 no-op — 예외 없이 반환
    result = await repo.save({"task_id": "t-001", "content": "msg", "timestamp": "2026-03-29"})
    assert result is None  # no-op은 None 반환

    # get_by_task도 빈 리스트
    results = await repo.get_by_task("t-001")
    assert results == []

    # get_recent도 빈 리스트
    recent = await repo.get_recent()
    assert recent == []


# ─────────────────────────────────────────────────────────────────────────────
# DispatchService 테스트
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def mock_task_repo():
    """TaskRepositoryInterface를 모방하는 Mock."""
    repo = MagicMock()
    repo.get = AsyncMock()
    repo.save = AsyncMock()
    return repo


@pytest.fixture()
def mock_telegram():
    """TelegramInterface를 모방하는 Mock."""
    tg = MagicMock()
    tg.send_message = AsyncMock()
    return tg


@pytest.fixture()
def enable_dispatch(monkeypatch):
    """ENABLE_DISPATCH_SERVICE=1 로 설정."""
    monkeypatch.setenv("ENABLE_DISPATCH_SERVICE", "1")
    import core.services.dispatch_service as mod
    monkeypatch.setattr(mod, "ENABLE_DISPATCH_SERVICE", True)


@pytest.mark.asyncio
async def test_dispatch_success(monkeypatch, mock_task_repo, mock_telegram, enable_dispatch):
    """dispatch() — 정상 플로우: 태스크 조회 → Telegram 전송 → 상태 갱신 → True."""
    from core.services.dispatch_service import DispatchService

    monkeypatch.setenv("DEV_BOT_CHAT_ID", "-12345")

    mock_task_repo.get.return_value = {"task_id": "t-001", "status": "pending"}

    service = DispatchService(task_repo=mock_task_repo, telegram=mock_telegram)
    result = await service.dispatch("t-001", "dev", "작업 시작")

    assert result is True
    mock_telegram.send_message.assert_called_once_with(-12345, "[t-001] 작업 시작")
    mock_task_repo.save.assert_called_once()
    saved = mock_task_repo.save.call_args[0][0]
    assert saved["status"] == "dispatched"


@pytest.mark.asyncio
async def test_dispatch_task_not_found(mock_task_repo, mock_telegram, enable_dispatch):
    """dispatch() — 태스크 없으면 False 반환."""
    from core.services.dispatch_service import DispatchService

    mock_task_repo.get.return_value = None

    service = DispatchService(task_repo=mock_task_repo, telegram=mock_telegram)
    result = await service.dispatch("nonexistent", "dev", "msg")

    assert result is False
    mock_telegram.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_get_dispatch_status_dispatched(mock_task_repo, mock_telegram, enable_dispatch):
    """get_dispatch_status() — dispatched 상태 반환 확인."""
    from core.services.dispatch_service import DispatchService

    mock_task_repo.get.return_value = {"task_id": "t-002", "status": "dispatched"}

    service = DispatchService(task_repo=mock_task_repo, telegram=mock_telegram)
    status = await service.get_dispatch_status("t-002")

    assert status == "dispatched"


@pytest.mark.asyncio
async def test_get_dispatch_status_unknown(mock_task_repo, mock_telegram, enable_dispatch):
    """get_dispatch_status() — 태스크 없으면 'unknown' 반환."""
    from core.services.dispatch_service import DispatchService

    mock_task_repo.get.return_value = None

    service = DispatchService(task_repo=mock_task_repo, telegram=mock_telegram)
    status = await service.get_dispatch_status("no-such-task")

    assert status == "unknown"


@pytest.mark.asyncio
async def test_cancel_dispatch_success(mock_task_repo, mock_telegram, enable_dispatch):
    """cancel_dispatch() — dispatched → cancelled 성공."""
    from core.services.dispatch_service import DispatchService

    mock_task_repo.get.return_value = {"task_id": "t-003", "status": "dispatched"}

    service = DispatchService(task_repo=mock_task_repo, telegram=mock_telegram)
    result = await service.cancel_dispatch("t-003")

    assert result is True
    saved = mock_task_repo.save.call_args[0][0]
    assert saved["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_dispatch_not_dispatched(mock_task_repo, mock_telegram, enable_dispatch):
    """cancel_dispatch() — dispatched 아닌 상태는 취소 불가 → False."""
    from core.services.dispatch_service import DispatchService

    mock_task_repo.get.return_value = {"task_id": "t-004", "status": "pending"}

    service = DispatchService(task_repo=mock_task_repo, telegram=mock_telegram)
    result = await service.cancel_dispatch("t-004")

    assert result is False
    mock_task_repo.save.assert_not_called()


@pytest.mark.asyncio
async def test_dispatch_disabled(monkeypatch, mock_task_repo, mock_telegram):
    """ENABLE_DISPATCH_SERVICE=0 일 때 모든 메서드가 기본값 반환."""
    import core.services.dispatch_service as mod
    monkeypatch.setattr(mod, "ENABLE_DISPATCH_SERVICE", False)
    from core.services.dispatch_service import DispatchService

    service = DispatchService(task_repo=mock_task_repo, telegram=mock_telegram)

    assert await service.dispatch("t", "org", "msg") is False
    assert await service.get_dispatch_status("t") == "unknown"
    assert await service.cancel_dispatch("t") is False
    mock_task_repo.get.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# eval_context 테스트
# ─────────────────────────────────────────────────────────────────────────────


def test_inject_eval_context_disabled(monkeypatch):
    """ENABLE_EVAL_CONTEXT=false → 빈 문자열 반환."""
    import core.eval_context as mod
    monkeypatch.setattr(mod, "ENABLE_EVAL_CONTEXT", False)
    from core.eval_context import inject_eval_context

    result = inject_eval_context()
    assert result == ""


def test_inject_eval_context_enabled_no_env(monkeypatch):
    """ENABLE_EVAL_CONTEXT=true 이지만 EVAL_SESSION/IS_EVAL_RUN/EVAL_ALWAYS 미설정 → 빈 문자열."""
    import core.eval_context as mod
    monkeypatch.setattr(mod, "ENABLE_EVAL_CONTEXT", True)
    monkeypatch.delenv("EVAL_SESSION", raising=False)
    monkeypatch.delenv("IS_EVAL_RUN", raising=False)
    monkeypatch.delenv("EVAL_ALWAYS", raising=False)
    from core.eval_context import inject_eval_context

    result = inject_eval_context()
    assert result == ""


def test_inject_eval_context_enabled_with_eval_always(monkeypatch):
    """ENABLE_EVAL_CONTEXT=true + EVAL_ALWAYS=1 → 세션 구분 없이 평가 인지 문구 포함."""
    import core.eval_context as mod
    monkeypatch.setattr(mod, "ENABLE_EVAL_CONTEXT", True)
    monkeypatch.delenv("EVAL_SESSION", raising=False)
    monkeypatch.delenv("IS_EVAL_RUN", raising=False)
    monkeypatch.setenv("EVAL_ALWAYS", "1")
    from core.eval_context import inject_eval_context

    result = inject_eval_context()
    assert "[평가 모드]" in result
    assert "품질 평가" in result


def test_inject_eval_context_enabled_with_eval_session(monkeypatch):
    """ENABLE_EVAL_CONTEXT=true + EVAL_SESSION=1 → 평가 인지 문구 포함."""
    import core.eval_context as mod
    monkeypatch.setattr(mod, "ENABLE_EVAL_CONTEXT", True)
    monkeypatch.setenv("EVAL_SESSION", "1")
    monkeypatch.delenv("IS_EVAL_RUN", raising=False)
    from core.eval_context import inject_eval_context

    result = inject_eval_context()
    assert "[평가 모드]" in result
    assert "품질 평가" in result


def test_inject_eval_context_enabled_with_is_eval_run(monkeypatch):
    """ENABLE_EVAL_CONTEXT=true + IS_EVAL_RUN=1 → 평가 인지 문구 포함."""
    import core.eval_context as mod
    monkeypatch.setattr(mod, "ENABLE_EVAL_CONTEXT", True)
    monkeypatch.delenv("EVAL_SESSION", raising=False)
    monkeypatch.setenv("IS_EVAL_RUN", "1")
    from core.eval_context import inject_eval_context

    result = inject_eval_context()
    assert "[평가 모드]" in result


def test_inject_eval_context_extra_notice(monkeypatch):
    """extra_notice가 결과에 포함되는지 확인."""
    import core.eval_context as mod
    monkeypatch.setattr(mod, "ENABLE_EVAL_CONTEXT", True)
    monkeypatch.setenv("EVAL_SESSION", "1")
    from core.eval_context import inject_eval_context

    result = inject_eval_context(extra_notice="추가 안내 문구")
    assert "추가 안내 문구" in result


# ─────────────────────────────────────────────────────────────────────────────
# run_error_gotcha 핵심 로직 단위 테스트
# ─────────────────────────────────────────────────────────────────────────────


def test_parse_next_gotcha_number_empty():
    """빈 파일 → 1 반환."""
    from tools.run_error_gotcha import parse_next_gotcha_number

    assert parse_next_gotcha_number("") == 1
    assert parse_next_gotcha_number("# Title\n\nSome text\n") == 1


def test_parse_next_gotcha_number_existing():
    """기존 항목 존재 시 max+1 반환."""
    from tools.run_error_gotcha import parse_next_gotcha_number

    content = "## Gotcha 1: 첫 번째\n\n## Gotcha 3: 세 번째\n"
    assert parse_next_gotcha_number(content) == 4


def test_build_gotcha_entry():
    """build_gotcha_entry가 올바른 마크다운을 생성하는지 확인."""
    from tools.run_error_gotcha import build_gotcha_entry

    entry = build_gotcha_entry(
        number=5,
        error="TypeError: int + str",
        file="core/foo.py",
        cause="타입 불일치",
        fix="str() 래핑",
    )
    assert "## Gotcha 5:" in entry
    assert "TypeError: int + str" in entry
    assert "core/foo.py" in entry
    assert "타입 불일치" in entry
    assert "str() 래핑" in entry


def test_append_gotcha_new_file():
    """gotchas.md가 없는 스킬에 새 항목을 추가하는지 확인."""
    from tools.run_error_gotcha import append_gotcha

    with tempfile.TemporaryDirectory() as tmpdir:
        skill_dir = Path(tmpdir) / "my-skill"
        skill_dir.mkdir()
        gotchas_path = skill_dir / "gotchas.md"

        number, saved_path = append_gotcha(
            gotchas_path=gotchas_path,
            error="ValueError",
            file="core/bar.py",
            cause="잘못된 값",
            fix="값 검증 추가",
        )

        assert number == 1
        assert gotchas_path.exists()
        content = gotchas_path.read_text()
        assert "## Gotcha 1:" in content
        assert "ValueError" in content


def test_append_gotcha_existing_file():
    """기존 gotchas.md에 번호 이어서 추가."""
    from tools.run_error_gotcha import append_gotcha

    with tempfile.TemporaryDirectory() as tmpdir:
        skill_dir = Path(tmpdir) / "my-skill"
        skill_dir.mkdir()
        gotchas_path = skill_dir / "gotchas.md"
        gotchas_path.write_text("# My Skill — Gotchas\n\n## Gotcha 1: 기존 항목\n\n- 내용\n")

        number, _ = append_gotcha(
            gotchas_path=gotchas_path,
            error="KeyError",
            file="",
            cause="키 없음",
            fix="키 존재 확인",
        )

        assert number == 2
        content = gotchas_path.read_text()
        assert "## Gotcha 2:" in content
        assert "KeyError" in content


# ─────────────────────────────────────────────────────────────────────────────
# run_pm_progress 핵심 로직 단위 테스트
# ─────────────────────────────────────────────────────────────────────────────


def test_parse_goals_empty():
    """목표 블록 없는 파일 → 빈 리스트."""
    from tools.run_pm_progress import parse_goals

    assert parse_goals("# PM Guide\n\n## 목표 목록\n") == []


def test_parse_goals_single():
    """단일 목표 파싱."""
    from tools.run_pm_progress import parse_goals

    content = (
        "### GOAL-001: 오픈소스화\n"
        "- 담당부서: 개발실\n"
        "- 시작일: 2026-03-24\n"
        "- 완료조건: setup.sh 실행 후 봇 응답\n"
        "- 현재상태: IN_PROGRESS\n"
    )
    goals = parse_goals(content)
    assert len(goals) == 1
    assert goals[0]["goal_id"] == "GOAL-001"
    assert goals[0]["status"] == "IN_PROGRESS"
    assert goals[0]["dept"] == "개발실"


def test_next_goal_id_empty():
    """빈 목록 → GOAL-001."""
    from tools.run_pm_progress import next_goal_id

    assert next_goal_id([]) == "GOAL-001"


def test_next_goal_id_existing():
    """기존 GOAL-003 → GOAL-004."""
    from tools.run_pm_progress import next_goal_id

    goals = [{"goal_id": "GOAL-001"}, {"goal_id": "GOAL-003"}]
    assert next_goal_id(goals) == "GOAL-004"


def test_action_register_creates_file():
    """action_register → pm_progress_guide.md 에 목표 추가."""
    from tools.run_pm_progress import action_register

    with tempfile.TemporaryDirectory() as tmpdir:
        guide_path = Path(tmpdir) / "memory" / "pm_progress_guide.md"
        guide_path.parent.mkdir(parents=True)

        rc = action_register(guide_path, "새 목표", "개발실", "완료 조건 명시")
        assert rc == 0
        content = guide_path.read_text()
        assert "GOAL-001" in content
        assert "새 목표" in content
        assert "IN_PROGRESS" in content


def test_action_update_changes_status():
    """action_update → 상태 변경 확인."""
    from tools.run_pm_progress import action_register, action_update

    with tempfile.TemporaryDirectory() as tmpdir:
        guide_path = Path(tmpdir) / "memory" / "pm_progress_guide.md"
        guide_path.parent.mkdir(parents=True)

        action_register(guide_path, "테스트 목표", "기획실", "E2E PASS")
        rc = action_update(guide_path, "GOAL-001", "DONE")
        assert rc == 0
        content = guide_path.read_text()
        assert "현재상태: DONE" in content


# ─────────────────────────────────────────────────────────────────────────────
# SessionStore eval_mode 테스트
# ─────────────────────────────────────────────────────────────────────────────


def test_session_store_eval_mode():
    """update_runtime(eval_mode=True) → is_eval_mode() == True."""
    from core.session_store import SessionStore

    with tempfile.TemporaryDirectory() as tmpdir:
        import core.session_store as ss_mod
        original_dir = ss_mod.SESSION_DIR
        ss_mod.SESSION_DIR = Path(tmpdir)

        try:
            store = SessionStore("test-eval")
            store.path = Path(tmpdir) / "pm_test-eval.json"

            assert store.is_eval_mode() is False

            store.update_runtime(eval_mode=True)
            assert store.is_eval_mode() is True

            store.update_runtime(eval_mode=False)
            assert store.is_eval_mode() is False
        finally:
            ss_mod.SESSION_DIR = original_dir
