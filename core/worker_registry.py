"""Worker Registry — workers.yaml에서 워커 봇 동적 로드."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from loguru import logger

if TYPE_CHECKING:
    from core.worker_bot import WorkerBot


def _resolve_env(value: str) -> str:
    """${VAR_NAME} 패턴을 환경변수로 치환."""
    def replacer(m: re.Match) -> str:
        var = m.group(1)
        val = os.environ.get(var, "")
        if not val:
            logger.warning(f"환경변수 미설정: {var}")
        return val
    return re.sub(r"\$\{(\w+)\}", replacer, value)


class WorkerRegistry:
    """workers.yaml을 읽어서 WorkerBot 인스턴스 동적 생성."""

    def __init__(self, config_path: str | Path | None = None) -> None:
        self.config_path = Path(config_path or "workers.yaml")
        self._workers: dict[str, "WorkerBot"] = {}

    def load(self) -> list["WorkerBot"]:
        """설정 파일에서 워커 목록 로드."""
        from core.worker_bot import WorkerBot

        if not self.config_path.exists():
            logger.warning(f"workers.yaml 없음: {self.config_path}")
            return []

        with self.config_path.open(encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

        workers_cfg = config.get("workers", [])
        loaded: list[WorkerBot] = []

        for cfg in workers_cfg:
            name: str = cfg["name"]
            token_raw: str = cfg["token"]
            engine: str = cfg.get("engine", "claude-code")
            description: str = cfg.get("description", "")

            token = _resolve_env(token_raw)
            if not token:
                logger.error(f"워커 '{name}' 토큰 없음 — 스킵")
                continue

            handle = f"@{name}_bot"
            bot = WorkerBot(handle=handle, token=token, engine=engine, description=description)
            self._workers[name] = bot
            loaded.append(bot)
            logger.info(f"워커 로드: {handle} (engine={engine})")

        logger.info(f"총 {len(loaded)}개 워커 로드 완료")
        return loaded

    def get_worker(self, name: str) -> "WorkerBot | None":
        return self._workers.get(name)

    def list_workers(self) -> list[dict]:
        """PM이 팀 현황 파악용 — 워커 메타 목록 반환."""
        return [
            {
                "name": name,
                "handle": bot.handle,
                "engine": bot.engine,
                "description": bot.description,
            }
            for name, bot in self._workers.items()
        ]
