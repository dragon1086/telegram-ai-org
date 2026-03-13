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
            "direction": self._parse_field(core_section, "방향성"),
            "default_handler": self.org_id == "global" or "어떤 PM도 자신없을 때 기본 담당" in core_section or "default_handler: true" in core_section,
        }
        logger.debug(f"PM 정체성 로드: {self.org_id} → {self._data['role']}")
        return self._data

    def get_specialty_text(self) -> str:
        """전문분야 텍스트 반환 (confidence scoring용)."""
        if not self._data:
            self.load()
        specialties = self._data.get("specialties", [])
        return ", ".join(specialties)

    def _load_team_config(self) -> dict:
        """봇 yaml의 team_config 섹션 로드. 없으면 빈 dict."""
        try:
            import yaml  # type: ignore
            bot_yaml = Path(__file__).parent.parent / "bots" / f"{self.org_id}.yaml"
            if bot_yaml.exists():
                with bot_yaml.open(encoding="utf-8") as f:
                    cfg = yaml.safe_load(f) or {}
                return cfg.get("team_config", {})
        except Exception:
            pass
        return {}

    def _load_colleagues(self) -> list[dict]:
        """동료 팀 목록 로드 (self.org_id 제외, global은 모두 포함)."""
        colleagues = []
        is_global = self._data.get("default_handler", False)
        for path in sorted(self.MEMORY_DIR.glob("pm_*.md")):
            # 자신 제외
            candidate_org = path.stem[len("pm_"):]
            if candidate_org == self.org_id:
                continue
            try:
                text = path.read_text(encoding="utf-8")
                core = self._extract_core_section(text)
                bot_name = self._parse_field(core, "봇명")
                role = self._parse_field(core, "역할")
                specialties = self._parse_specialties(core)
                default_handler = (
                    candidate_org == "global"
                    or "어떤 PM도 자신없을 때 기본 담당" in core
                    or "default_handler: true" in core
                )
                # global 봇은 모든 동료 포함, 조직봇은 global 제외
                if not is_global and default_handler:
                    continue
                if not bot_name and not role:
                    continue
                colleagues.append({
                    "org_id": candidate_org,
                    "bot_name": bot_name or f"@{candidate_org}_bot",
                    "role": role,
                    "specialties": specialties,
                })
            except Exception:
                pass
        return colleagues

    def build_system_prompt(self) -> str:
        """Claude --append-system-prompt에 주입할 전체 시스템 프롬프트."""
        if not self._data:
            self.load()

        data = self._data
        org = data.get("org_id", "global")
        role = data.get("role", "")
        specialties = data.get("specialties", [])
        spec_text = ", ".join(specialties)

        from tools.team_strategy import detect_strategy

        strategy_name = detect_strategy()
        strategy_desc = {
            "omc": "omc /team (강력)",
            "native": "native agents",
            "solo": "단독 실행",
        }

        # 전문분야 기반 추천 에이전트 (최대 5개)
        recommend_line = ""
        try:
            from tools.agent_catalog_v2 import recommend_agents
            recommended = recommend_agents(spec_text, max_agents=5)
            if recommended:
                recommend_line = f"\n추천 (전문분야 기반): {', '.join(recommended)}"
        except Exception:
            pass

        direction = data.get("direction", "")
        direction_line = f"- 방향성: {direction}" if direction else "- 방향성: 조직의 정체성에 맞게 판단"

        # 팀 구성 설정 (bots/{org_id}.yaml team_config 섹션)
        team_cfg = self._load_team_config()
        team_config_section = ""
        if team_cfg:
            preferred = team_cfg.get("preferred_agents", [])
            avoid = team_cfg.get("avoid_agents", [])
            max_size = team_cfg.get("max_team_size", 5)
            escalate = team_cfg.get("escalate_to", "")
            guidance = team_cfg.get("guidance", "")
            lines = []
            if preferred:
                lines.append(f"- 선호 에이전트: {', '.join(preferred)}")
            if avoid:
                lines.append(f"- 제외 에이전트: {', '.join(avoid)}")
            if max_size:
                lines.append(f"- 최대 팀 크기: {max_size}명")
            if escalate:
                lines.append(f"- 에스컬레이션: {escalate} (태스크가 너무 크면 위임)")
            if guidance:
                lines.append(f"- 지침: {guidance}")
            if lines:
                team_config_section = "\n## 팀 구성 설정 (config 기반)\n" + "\n".join(lines)

        # 동료 팀 섹션
        colleagues = self._load_colleagues()
        if colleagues:
            colleague_lines = "\n".join(
                f"• {c['bot_name']} — {', '.join(c['specialties']) or c['role']}"
                for c in colleagues
            )
            colleague_section = f"""
## 동료 팀 (협업 가능)
{colleague_lines}
→ 위 팀이 더 적합한 업무가 있으면 [COLLAB:태스크|맥락:ctx] 태그로 위임 요청
"""
        else:
            colleague_section = ""

        return f"""당신은 {org} 조직의 PM입니다.

## 조직 정체성
- 역할: {role}
- 전문 분야: {spec_text}
{direction_line}

## 팀 구성 전략: {strategy_desc.get(strategy_name, strategy_name)}

## 에이전트
전체 목록: ~/.claude/agents/ (팀 구성 전 ls로 확인 후 실제 존재하는 에이전트만 사용){recommend_line}
{colleague_section}{team_config_section}
## 팀 구성 원칙 (필수 준수)

기본 판단 기준: **실행이 수반되는가?**

### 협업 원칙
- 동료 팀의 전문분야와 겹치는 작업은 단독 처리보다 협업 우선
- 복합 태스크(예: 분석+구현, 설계+마케팅)는 반드시 관련 팀에 [COLLAB:] 요청
- 혼자 처리해도 되지만 다른 팀이 더 잘할 수 있으면 적극 위임


### 팀 구성 생략 (PM 직접 답변)
→ 첫 줄에 반드시: "💬 PM 직접 답변"
- 인사/안부
- 방향 안내, 순서 설명, 단계별 가이드
- 개념/기술 설명
- 단순 추천 (도구, 방법론 등)
- 사실 질문

### 팀 구성 필수
⚠️ **무조건 응답 맨 첫 줄에 [TEAM:...] 태그 작성. 빠뜨리면 시스템 오류.**
→ 응답 첫 줄에 반드시 [TEAM:에이전트1,에이전트2,...] 태그 포함:
  예: [TEAM:backend-engineer, ux-designer, data-analyst]
  팀원 없이 혼자 처리하면: [TEAM:solo]
  (에이전트 호출해도 solo이면 [TEAM:solo] 작성)
→ 그 다음 팀 구성 발표:
🏗️ 팀 구성
• [에이전트A]: [담당 역할]
• [에이전트B]: [담당 역할]
이유: [선택 이유 한 줄]
(예: executor: 코드 구현 / analyst: 요구사항 분석)
- 실제 코드 작성/수정/구현
- 파일·시스템·DB 변경
- 보고서·문서 직접 작성
- 전략 기획 (실행 계획 포함)
- 배포·인프라 작업
- 데이터 분석 및 결과 도출

---

## 협업 요청
작업 중 다른 조직의 도움이 필요할 때:
→ 응답에 [COLLAB:구체적 작업 설명|맥락: 현재 작업 요약] 태그를 포함하세요
→ 예: [COLLAB:출시 홍보 카피 3개 필요|맥락: Python JWT 로그인 라이브러리 v1.0, B2B 타겟]
→ 태그는 한 번에 최대 1개, 정말 필요할 때만 사용
→ 협업 결과는 채팅방에서 자동으로 전달됩니다

## 응답 언어
한국어로 소통. 기술 용어는 영어 허용."""

    # ── 파싱 헬퍼 ───────────────────────────────────────────────────────────

    def _extract_core_section(self, text: str) -> str:
        """[CORE] 섹션 추출."""
        match = re.search(r"## \[CORE\] PM 정체성(.*?)(?=## |\Z)", text, re.DOTALL)
        return match.group(1) if match else text

    def _parse_field(self, text: str, field: str) -> str:
        """'- 필드명: 값' 형식 파싱."""
        match = re.search(rf"- \*?\*?{field}\*?\*?: (.+)", text)
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

    def update(self, new_data: dict) -> None:
        """정체성 업데이트 후 파일 저장."""
        self._data.update(new_data)
        from pathlib import Path
        import re
        identity_file = Path.home() / ".ai-org" / "memory" / f"pm_{self.org_id}.md"
        existing = identity_file.read_text(encoding="utf-8") if identity_file.exists() else ""
        # 방향성 줄 업데이트
        for key, label in [("role", "역할"), ("direction", "방향성")]:
            if key in new_data:
                val = new_data[key]
                if f"- {label}:" in existing:
                    existing = re.sub(f"- {label}:.*", f"- {label}: {val}", existing)
                else:
                    existing += f"\n- {label}: {val}"
        if "specialties" in new_data:
            specs = ", ".join(new_data["specialties"])
            if "- 전문분야:" in existing:
                existing = re.sub(r"- 전문분야:.*", f"- 전문분야: {specs}", existing)
            else:
                existing += f"\n- 전문분야: {specs}"
        identity_file.write_text(existing, encoding="utf-8")
