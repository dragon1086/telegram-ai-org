"""PM 정체성 로더 — memory/pm_{org}.md [CORE] 섹션 파싱."""
from __future__ import annotations

import re
from pathlib import Path

from loguru import logger
from core.orchestration_config import load_orchestration_config
from core.builtin_surfaces import recommend_builtin_surfaces


class PMIdentity:
    """PM 정체성 로더 — memory/pm_{org}.md [CORE] 파싱."""

    MEMORY_DIR = Path.home() / ".ai-org" / "memory"

    def __init__(self, org_id: str) -> None:
        self.org_id = org_id
        self.path = self.MEMORY_DIR / f"pm_{org_id}.md"
        self._data: dict = {}

    def load(self) -> dict:
        """정체성 로드. {"role": ..., "specialties": [...], "bot_name": ...}"""
        cfg = None
        try:
            cfg = load_orchestration_config().get_org(self.org_id)
        except Exception:
            cfg = None

        file_data = self._load_file_overrides()

        if cfg is not None:
            self._data = {
                "org_id": self.org_id,
                "bot_name": f"@{cfg.username}" if cfg.username and not cfg.username.startswith("@") else cfg.username,
                "role": cfg.role,
                "specialties": cfg.specialties,
                "direction": cfg.direction,
                "preferred_agents": list(cfg.team.get("preferred_agents", [])),
                "default_handler": cfg.default_handler,
            }
            self._apply_file_overrides(file_data)
            return self._data

        if not self.path.exists():
            logger.warning(f"PM 정체성 파일 없음: {self.path}")
            return self._defaults()

        self._data = {
            "org_id": self.org_id,
            **file_data,
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
            cfg = load_orchestration_config().get_org(self.org_id)
            if cfg is not None:
                return {
                    "preferred_agents": list(cfg.team.get("preferred_agents", [])),
                    "avoid_agents": list(cfg.team.get("avoid_agents", [])),
                    "preferred_skills": list(cfg.team.get("preferred_skills", [])),
                    "max_team_size": cfg.team.get("max_team_size", 3),
                    "guidance": cfg.team.get("guidance", ""),
                }
        except Exception:
            pass
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
        try:
            cfg = load_orchestration_config()
            current = cfg.get_org(self.org_id)
            if current is not None:
                colleagues = []
                for org in cfg.list_orgs():
                    if org.id == self.org_id:
                        continue
                    if not current.default_handler and org.default_handler:
                        continue
                    colleagues.append({
                        "org_id": org.id,
                        "bot_name": f"@{org.username}" if org.username and not org.username.startswith("@") else org.username,
                        "role": org.role,
                        "specialties": org.specialties,
                    })
                if colleagues:
                    return colleagues
        except Exception:
            pass
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

    def get_team_preferences(self) -> dict:
        """실행 엔진/팀 구성에 필요한 조직 선호값 반환."""
        if not self._data:
            self.load()
        team_cfg = self._load_team_config()
        return {
            "role": self._data.get("role", ""),
            "specialties": self._data.get("specialties", []),
            "direction": self._data.get("direction", ""),
            "preferred_agents": self._data.get("preferred_agents", []),
            "preferred_skills": team_cfg.get("preferred_skills", []),
            "avoid_agents": team_cfg.get("avoid_agents", []),
            "max_team_size": team_cfg.get("max_team_size", 3),
            "guidance": team_cfg.get("guidance", ""),
        }

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

        # 전문분야 기반 추천 에이전트 (최대 5개, LLM 기반)
        recommend_line = ""
        try:
            from tools.agent_catalog_v2 import recommend_agents_llm_sync
            recommended = recommend_agents_llm_sync(role, spec_text, max_agents=5, org_id=org)
            if recommended:
                recommend_line = f"\n추천 (태스크+전문분야 기반): {', '.join(recommended)}"
        except Exception:
            pass
        preferred_agents = data.get("preferred_agents", [])
        preferred_line = (
            f"\n우선 고려할 에이전트: {', '.join(preferred_agents)}"
            if preferred_agents else ""
        )

        direction = data.get("direction", "")
        direction_line = f"- 방향성: {direction}" if direction else "- 방향성: 조직의 정체성에 맞게 판단"

        # 팀 구성 설정 (bots/{org_id}.yaml team_config 섹션)
        team_cfg = self._load_team_config()
        team_config_section = ""
        preferred_skills = team_cfg.get("preferred_skills", [])
        if team_cfg:
            avoid = team_cfg.get("avoid_agents", [])
            max_size = team_cfg.get("max_team_size", 5)
            escalate = team_cfg.get("escalate_to", "")
            guidance = team_cfg.get("guidance", "")
            lines = []
            if avoid:
                lines.append(f"- 제외 에이전트: {', '.join(avoid)}")
            if max_size:
                lines.append(f"- 최대 팀 크기: {max_size}명")
            if escalate:
                lines.append(f"- 에스컬레이션: {escalate} (태스크가 너무 크면 위임)")
            if guidance:
                lines.append(f"- 지침: {guidance}")
            if preferred_skills:
                lines.append(f"- 선호 스킬/워크플로: {', '.join(preferred_skills)}")
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
→ 위 팀이 더 적합한 업무가 있으면 아래 "협업 요청" 규칙의 COLLAB 태그로 위임 요청
"""
        else:
            colleague_section = ""

        builtin_surfaces = recommend_builtin_surfaces(f"{role} {' '.join(specialties)} {direction}", org_id=org)
        builtin_lines = "\n".join(
            f"- `{surface.command}`: {surface.purpose}"
            for surface in builtin_surfaces
        )

        return f"""당신은 {org} 조직의 PM입니다.

## 조직 정체성
- 역할: {role}
- 전문 분야: {spec_text}
{direction_line}

## 팀 구성 전략: {strategy_desc.get(strategy_name, strategy_name)}

## 에이전트
전체 목록: ~/.claude/agents/ (팀 구성 전 ls로 확인 후 실제 존재하는 에이전트만 사용){recommend_line}{preferred_line}
- 에이전트 선택 원칙:
  태스크 수신 시 ~/.claude/agents/ 를 ls로 확인 후,
  태스크에 가장 적합한 에이전트 파일만 개별 Read해서 팀 구성.
  전체 목록을 한번에 읽지 말 것 (토큰 낭비).

## 내장 Control Surface 우선 사용
- 이 리포지토리에 이미 있는 scripts/tools/CLI를 먼저 검토하고 재사용할 것
- ad-hoc 스크립트 작성보다 기존 제어면을 우선 사용하고, 정말 없을 때만 새 코드를 만들 것
{builtin_lines}
{colleague_section}{team_config_section}
## 팀 구성 원칙 (필수 준수)

## 텔레그램 전달 규칙
- 텔레그램 Bot API를 직접 호출하는 임시 스크립트를 만들지 말 것
- 임의의 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 환경변수를 사용해 외부 채팅방으로 전송하지 말 것
- 최종 사용자는 텔레그램만 본다고 가정할 것. 로컬 내부 문서 경로나 파일시스템 링크만으로 설명을 대신하지 말 것
- 사용자에게 전달할 산출물이 있으면 파일을 생성하되, 본문에는 핵심 내용을 먼저 설명하고 경로는 런타임 첨부를 위한 힌트로만 사용할 것
- 여러 조직 문서를 취합했다면 조직별 원문 나열 대신 총괄 PM 관점의 통합 전달본을 새로 만들어 설명할 것
- 텔레그램 첨부/업로드는 PM 런타임이 처리한다고 가정할 것

## 최종 사용자 응답 검증 루프
- 답변 초안이 로컬 문서 위치 안내 위주인지 스스로 점검할 것
- 첫 문단에서 사용자 질문/불만에 직접 답했는지 확인할 것
- 첨부 파일이 있다면 첨부만 언급하지 말고, 그 안의 핵심 결과를 본문에서 먼저 설명할 것
- 각 조직 산출물을 그대로 던지지 말고, 사용자 기준의 하나의 통합 결과물로 재구성할 것

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

    def _parse_list_field(self, text: str, field: str) -> list[str]:
        raw = self._parse_field(text, field)
        if not raw:
            return []
        return [item.strip() for item in raw.split(",") if item.strip()]

    def _defaults(self) -> dict:
        return {
            "org_id": self.org_id,
            "bot_name": f"@{self.org_id}_bot",
            "role": "일반 PM",
            "specialties": [],
            "preferred_agents": [],
            "default_handler": self.org_id == "global",
        }

    def _load_file_overrides(self) -> dict:
        """pm_{org}.md 값을 읽어 config 위에 덮어쓸 override를 만든다."""
        if not self.path.exists():
            return self._defaults()

        text = self.path.read_text(encoding="utf-8")
        core_section = self._extract_core_section(text)
        return {
            "org_id": self.org_id,
            "bot_name": self._parse_field(core_section, "봇명"),
            "role": self._parse_field(core_section, "역할"),
            "specialties": self._parse_specialties(core_section),
            "direction": self._parse_field(core_section, "방향성"),
            "preferred_agents": self._parse_list_field(core_section, "선호 에이전트"),
            "default_handler": (
                self.org_id == "global"
                or "어떤 PM도 자신없을 때 기본 담당" in core_section
                or "default_handler: true" in core_section
            ),
        }

    def _apply_file_overrides(self, file_data: dict) -> None:
        """config 기반 기본값 위에 사용자가 /org 로 저장한 값을 덮어쓴다."""
        for key in ("bot_name", "role", "direction"):
            if file_data.get(key):
                self._data[key] = file_data[key]

        if file_data.get("specialties"):
            self._data["specialties"] = file_data["specialties"]

        if file_data.get("preferred_agents"):
            self._data["preferred_agents"] = file_data["preferred_agents"]

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
