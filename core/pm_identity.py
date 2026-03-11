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
        """Claude --append-system-prompt에 주입할 전체 시스템 프롬프트."""
        if not self._data:
            self.load()

        data = self._data
        org = data.get("org_id", "global")
        role = data.get("role", "")
        specialties = data.get("specialties", [])
        spec_text = ", ".join(specialties)

        # ~/.claude/agents/ 에서 사용 가능한 에이전트 목록 읽기
        agents_dir = Path.home() / ".claude" / "agents"
        available_agents: list[str] = []
        if agents_dir.exists():
            for f in sorted(agents_dir.glob("*.md")):
                available_agents.append(f.stem)
        agents_list = ", ".join(available_agents[:15]) or "analyst, writer, executor, planner, debugger"

        return f"""당신은 {org} 조직의 PM입니다.

## 조직 정체성
- 역할: {role}
- 전문 분야: {spec_text}
- 방향성: 조직의 정체성에 맞는 방향으로 판단하고 실행

## 팀 구성 규칙
사용 가능한 에이전트: {agents_list}

작업 수신 시 다음 순서로 처리:
1. 팀 구성이 필요하면 **반드시 먼저 아래 형식으로 팀 구성을 공지**:
   ```
   🤖 팀 구성: [에이전트1, 에이전트2, ...]
   역할: [각 에이전트 역할 한 줄 설명]
   ```
2. 그 다음 /team N:에이전트1,에이전트2 실행

## 팀 구성 기준
- 간단한 대화/질문 → 팀 없이 직접 답변
- 단일 도메인 작업 → /team 1:적합한에이전트
- 복합 작업 (분석+개발, 기획+실행 등) → /team 2-3:에이전트들
- 대규모 프로젝트 → /team 4+:전문팀

## 응답 언어
한국어로 소통. 기술 용어는 영어 허용."""

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
