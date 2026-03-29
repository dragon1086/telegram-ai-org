"""Platform Adapter — abstract base + Telegram implementation.

Inspired by hermes-agent's ACP adapter pattern.  Separates platform-specific
message handling from core business logic.

Feature flag: ENABLE_PLATFORM_ADAPTER (default=false)
  - When false: TelegramPlatformAdapter falls back to pass-through stubs.
  - When true: full adapter routing is active.

Design notes:
  - PlatformAdapter is an abstract base class; new platforms add new subclasses.
  - No modification to telegram_relay.py — adapter is opt-in via feature flag.
  - Backward compatible: all existing code continues working unchanged.
  - No global state beyond module-level _adapters registry dict.

Self-review:
  ① Logic: abstract interface forces all subclasses to implement the same contract.
  ② Edge cases: None message, missing chat_id, disabled flag → all handled.
  ③ Compat: new standalone module; existing telegram_relay.py untouched.
  ④ Global state: _adapters dict is module-level but never touched by other modules.
"""
from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _is_enabled() -> bool:
    """Return True if the platform adapter feature flag is enabled."""
    return os.environ.get("ENABLE_PLATFORM_ADAPTER", "false").lower() in ("true", "1", "yes")


# ---------------------------------------------------------------------------
# Data transfer objects
# ---------------------------------------------------------------------------


@dataclass
class InboundMessage:
    """Normalised inbound message from any platform.

    Attributes:
        platform: Platform identifier (e.g. "telegram", "slack").
        message_id: Platform-native message identifier (string for portability).
        chat_id: Chat/channel/room identifier.
        sender_id: Sender's platform user identifier.
        text: Plain-text content of the message (may be empty for media-only).
        raw: Original platform-specific object, kept for escape-hatch access.
        metadata: Arbitrary extra fields (e.g. reply_to, thread_id).
    """

    platform: str
    message_id: str
    chat_id: str
    sender_id: str
    text: str
    raw: Any = field(default=None, repr=False)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OutboundMessage:
    """Normalised outbound message to send via a platform.

    Attributes:
        chat_id: Destination chat/channel/room identifier.
        text: Message body.
        reply_to_message_id: If set, the message is a reply.
        parse_mode: Formatting mode (e.g. "HTML", "Markdown").
        metadata: Arbitrary extra fields for platform-specific options.
    """

    chat_id: str
    text: str
    reply_to_message_id: Optional[str] = None
    parse_mode: str = "HTML"
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Abstract base class
# ---------------------------------------------------------------------------


class PlatformAdapter(ABC):
    """Abstract base for platform-specific message adapters.

    Subclasses must implement:
      - platform_name: property returning a short string identifier.
      - normalize_inbound: convert a raw platform event to InboundMessage.
      - send_message: deliver an OutboundMessage to the platform.

    Optional overrides:
      - can_handle: returns True if this adapter should process the given raw event.
      - on_startup / on_shutdown: lifecycle hooks.
    """

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Short identifier, e.g. 'telegram', 'slack'."""

    @abstractmethod
    def normalize_inbound(self, raw_event: Any) -> Optional[InboundMessage]:
        """Convert a raw platform event into a normalised InboundMessage.

        Args:
            raw_event: Platform-native event object.

        Returns:
            InboundMessage, or None if the event should be ignored.
        """

    @abstractmethod
    def send_message(self, message: OutboundMessage) -> bool:
        """Deliver an outbound message.

        Args:
            message: The normalised message to send.

        Returns:
            True on success, False on failure.
        """

    def can_handle(self, raw_event: Any) -> bool:
        """Return True if this adapter should process *raw_event*.

        Default: always True.  Override to add filtering logic.
        """
        return True

    def on_startup(self) -> None:
        """Called when the adapter is activated.  Default is a no-op."""
        logger.debug("PlatformAdapter[%s]: startup", self.platform_name)

    def on_shutdown(self) -> None:
        """Called when the adapter is deactivated.  Default is a no-op."""
        logger.debug("PlatformAdapter[%s]: shutdown", self.platform_name)


# ---------------------------------------------------------------------------
# Telegram adapter implementation
# ---------------------------------------------------------------------------


class TelegramPlatformAdapter(PlatformAdapter):
    """Telegram-specific platform adapter.

    Converts python-telegram-bot Update objects to/from the normalised DTOs.
    When ENABLE_PLATFORM_ADAPTER=false the adapter is instantiatable but its
    methods are safe no-ops so existing code is never broken.

    Args:
        bot_sender: Optional callable(chat_id, text, **kwargs) for sending.
                    If None, send_message() logs a warning and returns False.
    """

    def __init__(self, bot_sender: Optional[Any] = None) -> None:
        self._bot_sender = bot_sender

    @property
    def platform_name(self) -> str:
        return "telegram"

    def normalize_inbound(self, raw_event: Any) -> Optional[InboundMessage]:
        """Normalise a python-telegram-bot Update into InboundMessage.

        Args:
            raw_event: A telegram.Update object.

        Returns:
            InboundMessage on success, None if the update has no message or text.
        """
        if not _is_enabled():
            logger.debug("TelegramPlatformAdapter: disabled; normalize_inbound is no-op")
            return None

        if raw_event is None:
            logger.debug("TelegramPlatformAdapter.normalize_inbound: raw_event is None")
            return None

        try:
            # Tolerate both real Update objects and simple dict-like mocks.
            if hasattr(raw_event, "effective_message"):
                msg = raw_event.effective_message
            elif hasattr(raw_event, "message"):
                msg = raw_event.message
            else:
                logger.debug("TelegramPlatformAdapter: unrecognised event type %s", type(raw_event))
                return None

            if msg is None:
                return None

            chat_id = str(getattr(getattr(msg, "chat", None), "id", "") or "")
            sender_id = str(getattr(getattr(msg, "from_user", None), "id", "") or "")
            message_id = str(getattr(msg, "message_id", "") or "")
            text = getattr(msg, "text", "") or ""

            if not chat_id:
                logger.debug("TelegramPlatformAdapter: missing chat_id in event")
                return None

            return InboundMessage(
                platform=self.platform_name,
                message_id=message_id,
                chat_id=chat_id,
                sender_id=sender_id,
                text=text,
                raw=raw_event,
                metadata={},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("TelegramPlatformAdapter.normalize_inbound error: %s", exc)
            return None

    def send_message(self, message: OutboundMessage) -> bool:
        """Send a message via the injected bot_sender callable.

        Args:
            message: The normalised outbound message.

        Returns:
            True if sent, False otherwise.
        """
        if not _is_enabled():
            logger.debug("TelegramPlatformAdapter: disabled; send_message is no-op")
            return False

        if not message.chat_id:
            logger.warning("TelegramPlatformAdapter.send_message: missing chat_id")
            return False

        if not message.text:
            logger.warning("TelegramPlatformAdapter.send_message: empty text for chat_id=%s", message.chat_id)
            return False

        if self._bot_sender is None:
            logger.warning(
                "TelegramPlatformAdapter.send_message: no bot_sender configured; "
                "message to chat_id=%s dropped",
                message.chat_id,
            )
            return False

        try:
            self._bot_sender(
                chat_id=message.chat_id,
                text=message.text,
                parse_mode=message.parse_mode,
                reply_to_message_id=message.reply_to_message_id,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("TelegramPlatformAdapter.send_message failed: %s", exc)
            return False

    def can_handle(self, raw_event: Any) -> bool:
        """Return True if the event looks like a Telegram Update."""
        if raw_event is None:
            return False
        return hasattr(raw_event, "effective_message") or hasattr(raw_event, "message")


# ---------------------------------------------------------------------------
# Adapter registry
# ---------------------------------------------------------------------------

_adapters: Dict[str, PlatformAdapter] = {}


def register_adapter(adapter: PlatformAdapter) -> None:
    """Register a platform adapter globally.

    Args:
        adapter: The adapter instance to register.
    """
    if not isinstance(adapter, PlatformAdapter):
        logger.warning("register_adapter: argument is not a PlatformAdapter — ignored")
        return
    _adapters[adapter.platform_name] = adapter
    logger.debug("Platform adapter registered: %s", adapter.platform_name)


def get_adapter(platform_name: str) -> Optional[PlatformAdapter]:
    """Retrieve a registered adapter by platform name.

    Returns None if not registered or feature flag is off.
    """
    if not _is_enabled():
        return None
    return _adapters.get(platform_name)


def list_adapters() -> List[str]:
    """Return a list of registered platform names."""
    if not _is_enabled():
        return []
    return list(_adapters.keys())
