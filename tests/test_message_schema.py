"""OrgMessage 스키마 테스트."""
import pytest
from pydantic import ValidationError

from core.message_schema import OrgMessage


def test_basic_message_creation():
    msg = OrgMessage(
        to="@dev_bot",
        from_="@pm_bot",
        task_id="T001",
        msg_type="assign",
        content="파이썬 웹서버 코드 작성",
    )
    assert msg.to == "@dev_bot"
    assert msg.task_id == "T001"
    assert msg.attachments == []


def test_broadcast_message():
    msg = OrgMessage(
        to="ALL",
        from_="@pm_bot",
        task_id="T002",
        msg_type="broadcast",
        content="전체 공지",
    )
    assert msg.is_addressed_to("@dev_bot")
    assert msg.is_addressed_to("@analyst_bot")


def test_multi_recipient():
    msg = OrgMessage(
        to=["@dev_bot", "@analyst_bot"],
        from_="@pm_bot",
        task_id="T003",
        msg_type="assign",
        content="병렬 작업",
    )
    assert msg.is_addressed_to("@dev_bot")
    assert msg.is_addressed_to("@analyst_bot")
    assert not msg.is_addressed_to("@docs_bot")


def test_invalid_handle():
    with pytest.raises(ValidationError):
        OrgMessage(
            to="dev_bot",  # @ 없음
            from_="@pm_bot",
            task_id="T001",
            msg_type="assign",
            content="테스트",
        )


def test_invalid_task_id():
    with pytest.raises(ValidationError):
        OrgMessage(
            to="@dev_bot",
            from_="@pm_bot",
            task_id="001",  # T 접두사 없음 — 잘못된 형식
            msg_type="assign",
            content="테스트",
        )


def test_telegram_text_roundtrip():
    original = OrgMessage(
        to="@dev_bot",
        from_="@pm_bot",
        task_id="T001",
        msg_type="assign",
        content="파이썬 웹서버 코드 작성해줘",
        context_ref="T001_request",
    )
    text = original.to_telegram_text()
    parsed = OrgMessage.parse_telegram_text(text)

    assert parsed is not None
    assert parsed.to == original.to
    assert parsed.from_ == original.from_
    assert parsed.task_id == original.task_id
    assert parsed.msg_type == original.msg_type
    assert parsed.context_ref == original.context_ref


def test_parse_fails_on_non_org_message():
    result = OrgMessage.parse_telegram_text("안녕하세요! 일반 메시지입니다.")
    assert result is None


def test_is_addressed_to_single():
    msg = OrgMessage(
        to="@dev_bot",
        from_="@pm_bot",
        task_id="T001",
        msg_type="assign",
        content="작업",
    )
    assert msg.is_addressed_to("@dev_bot")
    assert not msg.is_addressed_to("@analyst_bot")


def test_namespaced_task_id_valid():
    """T-pm-001 형식의 네임스페이스 태스크 ID 허용."""
    msg = OrgMessage(
        to="@bot1",
        from_="@pm_bot",
        task_id="T-pm-001",
        msg_type="assign",
        content="test",
    )
    assert msg.task_id == "T-pm-001"


def test_namespaced_task_id_with_dept():
    """T-eng-003 형식도 허용."""
    msg = OrgMessage(
        to="@bot1",
        from_="@pm_bot",
        task_id="T-eng-003",
        msg_type="assign",
        content="test",
    )
    assert msg.task_id == "T-eng-003"
