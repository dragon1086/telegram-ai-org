"""조직 레지스트리 — 멀티 조직 아키텍처 지원."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from loguru import logger


def _resolve_env(value: str) -> str:
    """${VAR_NAME} 형식 환경변수 치환."""
    if value.startswith("${") and value.endswith("}"):
        var_name = value[2:-1]
        return os.environ.get(var_name, "")
    return value


@dataclass
class Organization:
    """AI 조직 단위."""

    name: str
    description: str
    pm_token: str
    group_chat_id: int | None
    workers: list[str]  # worker handle names (e.g. ["cokac", "analyst"])

    @classmethod
    def from_config(cls, cfg: dict) -> "Organization":
        raw_token = cfg.get("pm_token", "")
        token = _resolve_env(raw_token)

        raw_chat_id = cfg.get("group_chat_id", "")
        if isinstance(raw_chat_id, int):
            chat_id: int | None = raw_chat_id
        elif raw_chat_id:
            resolved = _resolve_env(str(raw_chat_id))
            chat_id = int(resolved) if resolved else None
        else:
            chat_id = None

        return cls(
            name=cfg["name"],
            description=cfg.get("description", ""),
            pm_token=token,
            group_chat_id=chat_id,
            workers=cfg.get("workers", []),
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "group_chat_id": self.group_chat_id,
            "workers": self.workers,
        }


class OrgRegistry:
    """organizations.yaml을 로드해 조직 목록을 관리하는 레지스트리."""

    def __init__(self, config_path: str | Path | None = None) -> None:
        self.config_path = Path(config_path or "organizations.yaml")
        self._orgs: dict[str, Organization] = {}

    def load(self) -> list[Organization]:
        """설정 파일에서 조직 목록 로드."""
        if not self.config_path.exists():
            logger.warning(f"organizations.yaml 없음: {self.config_path}")
            return []

        with self.config_path.open(encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

        orgs_cfg = config.get("organizations", [])
        loaded: list[Organization] = []

        for cfg in orgs_cfg:
            try:
                org = Organization.from_config(cfg)
                if not org.pm_token:
                    logger.error(f"조직 '{org.name}' PM 토큰 없음 — 스킵")
                    continue
                self._orgs[org.name] = org
                loaded.append(org)
                logger.info(f"조직 로드: {org.name} (워커: {org.workers})")
            except Exception as e:
                logger.error(f"조직 로드 실패: {cfg.get('name', '?')} — {e}")

        logger.info(f"총 {len(loaded)}개 조직 로드 완료")
        return loaded

    def get_org(self, name: str) -> Organization | None:
        return self._orgs.get(name)

    def list_orgs(self) -> list[dict]:
        return [org.to_dict() for org in self._orgs.values()]

    def get_org_for_worker(self, worker_handle: str) -> Organization | None:
        """특정 워커가 속한 조직 반환."""
        handle = worker_handle.lstrip("@").removesuffix("_bot")
        for org in self._orgs.values():
            if handle in org.workers:
                return org
        return None

    def route_cross_org(self, from_org: str, to_worker: str) -> Organization | None:
        """from_org → to_worker가 속한 대상 조직 반환 (크로스 조직 라우팅)."""
        target_org = self.get_org_for_worker(to_worker)
        if target_org and target_org.name != from_org:
            logger.info(f"크로스 조직 라우팅: {from_org} → {target_org.name} ({to_worker})")
        return target_org
