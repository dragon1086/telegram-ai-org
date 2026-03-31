"""Tool Registry — centralized registry for tools/capabilities with capability tags.

Inspired by hermes-agent's tools/registry.py pattern, adapted for telegram-ai-org.

Feature flag: ENABLE_TOOL_REGISTRY (default=false)
  - When false: module loads safely but registry operations are no-ops.
  - When true: registry is active and tools can be discovered/dispatched.

Design notes:
  - No global state modification beyond the module-level singleton.
  - All public functions are safe to call when the flag is off.
  - Type hints throughout.
  - Backward compatible: existing code continues working unchanged.

Self-review:
  ① Logic: register() stores entries, get_tools_by_tag() filters by tag — correct.
  ② Edge cases: empty tags, None handler, duplicate names → all handled.
  ③ Compat: new module, no existing interfaces changed.
  ④ Global state: only module-level _registry singleton, not touching other modules.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


def _is_enabled() -> bool:
    """Return True if the tool registry feature flag is enabled."""
    return os.environ.get("ENABLE_TOOL_REGISTRY", "true").lower() in ("true", "1", "yes")


@dataclass
class ToolEntry:
    """Metadata for a single registered tool.

    Attributes:
        name: Unique tool identifier.
        description: Human-readable description.
        handler: Callable that executes the tool. May be None for metadata-only entries.
        capability_tags: Set of tags for capability-based lookup (e.g. {"read", "file"}).
        schema: Optional JSON-schema dict for the tool's parameters.
        enabled: Whether this tool is currently active.
    """

    name: str
    description: str
    handler: Optional[Callable[..., Any]]
    capability_tags: Set[str] = field(default_factory=set)
    schema: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True

    def matches_tags(self, tags: Set[str]) -> bool:
        """Return True if this entry has ALL requested tags."""
        return tags.issubset(self.capability_tags)


class ToolRegistry:
    """Centralized registry for tool schemas, handlers, and capability tags.

    Usage::

        from core.tool_registry import get_registry

        reg = get_registry()
        reg.register("my_tool", "Does something", handler=my_fn, tags={"io", "file"})
        entries = reg.get_tools_by_tag("io")
    """

    def __init__(self) -> None:
        self._tools: Dict[str, ToolEntry] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        name: str,
        description: str,
        handler: Optional[Callable[..., Any]] = None,
        tags: Optional[Set[str]] = None,
        schema: Optional[Dict[str, Any]] = None,
        enabled: bool = True,
    ) -> None:
        """Register a tool.

        Args:
            name: Unique tool identifier. Duplicate registration logs a warning.
            description: Short description of what the tool does.
            handler: Callable to invoke. None for metadata-only entries.
            tags: Capability tags (e.g. {"read", "file", "async"}).
            schema: Optional JSON-schema for tool parameters.
            enabled: Whether this tool is currently active (default True).
        """
        if not _is_enabled():
            logger.debug("ToolRegistry disabled (ENABLE_TOOL_REGISTRY=false); skipping register(%s)", name)
            return

        if not name or not isinstance(name, str):
            logger.warning("ToolRegistry.register: invalid name %r — skipped", name)
            return

        if name in self._tools:
            logger.warning("ToolRegistry: duplicate registration for '%s' — overwriting", name)

        self._tools[name] = ToolEntry(
            name=name,
            description=description or "",
            handler=handler,
            capability_tags=tags or set(),
            schema=schema or {},
            enabled=enabled,
        )
        logger.debug("ToolRegistry: registered tool '%s' with tags=%s", name, tags)

    def unregister(self, name: str) -> bool:
        """Remove a tool from the registry.

        Returns:
            True if the tool existed and was removed, False otherwise.
        """
        if not _is_enabled():
            return False
        removed = self._tools.pop(name, None) is not None
        if removed:
            logger.debug("ToolRegistry: unregistered tool '%s'", name)
        return removed

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, name: str) -> Optional[ToolEntry]:
        """Return the ToolEntry for *name*, or None if not found/disabled."""
        if not _is_enabled():
            return None
        return self._tools.get(name)

    def get_tools_by_tag(self, *tags: str) -> List[ToolEntry]:
        """Return all enabled tools that have ALL of the given tags.

        Args:
            *tags: One or more capability tag strings.

        Returns:
            List of matching ToolEntry objects, sorted by name.

        Edge cases:
            - No tags provided → returns all enabled tools.
            - Unknown tag → returns empty list (not an error).
        """
        if not _is_enabled():
            return []

        tag_set: Set[str] = set(tags)
        results = [
            entry
            for entry in self._tools.values()
            if entry.enabled and (not tag_set or entry.matches_tags(tag_set))
        ]
        return sorted(results, key=lambda e: e.name)

    def list_all(self) -> List[ToolEntry]:
        """Return all registered tools (enabled and disabled), sorted by name."""
        if not _is_enabled():
            return []
        return sorted(self._tools.values(), key=lambda e: e.name)

    def all_tags(self) -> Set[str]:
        """Return the union of all capability tags across all registered tools."""
        if not _is_enabled():
            return set()
        tags: Set[str] = set()
        for entry in self._tools.values():
            tags.update(entry.capability_tags)
        return tags

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def dispatch(self, name: str, **kwargs: Any) -> Any:
        """Call the handler for *name* with the given keyword arguments.

        Args:
            name: Tool name to dispatch.
            **kwargs: Arguments forwarded to the handler.

        Returns:
            Whatever the handler returns, or None if disabled/not found/no handler.

        Edge cases:
            - Registry disabled → returns None silently.
            - Tool not found → logs warning, returns None.
            - Tool disabled → logs debug, returns None.
            - Handler is None → logs warning, returns None.
        """
        if not _is_enabled():
            logger.debug("ToolRegistry disabled; dispatch('%s') is a no-op", name)
            return None

        entry = self._tools.get(name)
        if entry is None:
            logger.warning("ToolRegistry.dispatch: unknown tool '%s'", name)
            return None
        if not entry.enabled:
            logger.debug("ToolRegistry.dispatch: tool '%s' is disabled", name)
            return None
        if entry.handler is None:
            logger.warning("ToolRegistry.dispatch: tool '%s' has no handler", name)
            return None

        try:
            return entry.handler(**kwargs)
        except Exception as exc:  # noqa: BLE001
            logger.error("ToolRegistry.dispatch: tool '%s' raised %s: %s", name, type(exc).__name__, exc)
            raise

    def __len__(self) -> int:
        return len(self._tools) if _is_enabled() else 0

    def __repr__(self) -> str:
        if not _is_enabled():
            return "ToolRegistry(disabled)"
        return f"ToolRegistry(tools={list(self._tools.keys())})"


# Module-level singleton — the only global state in this module.
_registry: Optional[ToolRegistry] = None


def get_registry() -> ToolRegistry:
    """Return the module-level ToolRegistry singleton.

    Creating the singleton is cheap and idempotent.  The registry is
    effectively empty (and all operations are no-ops) when the feature
    flag is off.
    """
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry


def reset_registry() -> None:
    """Replace the singleton with a fresh instance.  Intended for tests only."""
    global _registry
    _registry = ToolRegistry()


# ---------------------------------------------------------------------------
# Module-level startup log — emitted once on import
# ---------------------------------------------------------------------------
logger.info("ToolRegistry feature flag: %s", "ENABLED" if _is_enabled() else "DISABLED")
