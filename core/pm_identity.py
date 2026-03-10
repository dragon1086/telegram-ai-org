"""PM 정체성 로더 — memory/pm_{org}.md [CORE] 섹션 파싱."""
from __future__ import annotations

import re
from pathlib import Path

from loguru import logger


class PMIdentity:
    """PM 정체성 로더 — memory/pm_{org}.md [CORE] 파싱."""

    MEMORY_DIR = Path.home() / ".ai-org" / "memory"

    def __init__(self, org_id: str) -> None:
        self.org_id = org_id
        self.path = self.MEMORY_DIR / f"pm_{org_id}.md"
        self._data: dict = {}

    def load(self) -> dict:
        """정체성 로드. {"role": ..., "specialties": [...], "bot_name": ...}"""
        if not self.path.exists():
            logger.warning(f"PM 정체성 파일 없음: {self.path}")
            return self._defaults()

        text = self.path.read_text(encoding="utf-8")
        core_section = self._extract_core_section(text)

        self._data = {
            "org_id": self.org_id,
            "bot_name": self._parse_field(core_section, "봇명"),
            "role": self._parse_field(core_section, "역할"),
            "specialties": self._parse_specialties(core_section),
            "default_handler": "어떤 PM도 자신없을 때 기본 담당" in core_section,
        }
        logger.debug(f"PM 정체성 로드: {self.org_id} → {self._data['role']}")
        return self._data

    def get_specialty_text(self) -> str:
        """전문분야 텍스트 반환 (confidence scoring용)."""
        if not self._data:
            self.load()
        specialties = self._data.get("specialties", [])
        return ", ".join(specialties)

    def build_system_prompt(self) -> str:
        """tmux Claude 세션 시작 시 주입할 시스템 프롬프트."""
        if not self._data:
            self.load()

        # 글로벌 컨텍스트 로드
        global_path = self.MEMORY_DIR / "global.md"
        global_ctx = ""
        if global_path.exists():
            global_ctx = global_path.read_text(encoding="utf-8")

        return (
            f"# PM 정체성: {self._data.get('org_id', self.org_id)}\n\n"
            f"**봇명**: {self._data.get('bot_name', '')}\n"
            f"**역할**: {self._data.get('role', '')}\n"
            f"**전문분야**: {self.get_specialty_text()}\n\n"
            f"## 글로벌 컨텍스트\n{global_ctx}"
        )

    # ── 파싱 헬퍼 ───────────────────────────────────────────────────────────

    def _extract_core_section(self, text: str) -> str:
        """[CORE] 섹션 추출."""
        match = re.search(r"## \[CORE\] PM 정체성(.*?)(?=## |\Z)", text, re.DOTALL)
        return match.group(1) if match else text

    def _parse_field(self, text: str, field: str) -> str:
        """'- 필드명: 값' 형식 파싱."""
        match = re.search(rf"- {field}: (.+)", text)
        return match.group(1).strip() if match else ""

    def _parse_specialties(self, text: str) -> list[str]:
        """전문분야 콤마 분리 파싱."""
        raw = self._parse_field(text, "전문분야")
        if not raw:
            return []
        return [s.strip() for s in raw.split(",") if s.strip()]

    def _defaults(self) -> dict:
        return {
            "org_id": self.org_id,
            "bot_name": f"@{self.org_id}_bot",
            "role": "일반 PM",
            "specialties": [],
            "default_handler": self.org_id == "global",
        }
