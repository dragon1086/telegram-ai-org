"""구조화 프롬프트 생성기 — 복잡도 기반 Phase별 프롬프트.

엔진 무관 (Claude Code, Codex, Antigravity 등 어떤 엔진이든 동작):
- /team, /ralph 등 특정 엔진 명령어 사용 금지
- 일반적인 단계별 지시문으로 구성

복잡도 판단 → Phase별 프롬프트 자동 생성.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum

from loguru import logger

from core.constants import KNOWN_DEPTS, DEPT_ROLES, DEFAULT_PHASES
from core.pm_decision import DecisionClientProtocol

# LLM 없이 _template_generate() 가 호출됐을 때 _default 도 로드 실패한 경우의
# 최소 인라인 fallback (플랫폼 무관 범용 템플릿).
_INLINE_FALLBACK_PHASE: dict[str, list[dict]] = {
    "simple": [{"name": "실행", "instructions": "요청사항을 분석하고 실행하세요.", "deliverables": ["실행 결과"]}],
    "moderate": [
        {"name": "분석", "instructions": "요청사항을 분석하세요.", "deliverables": ["분석 결과"]},
        {"name": "실행", "instructions": "분석 결과를 바탕으로 실행하세요.", "deliverables": ["실행 결과"]},
        {"name": "검증", "instructions": "실행 결과를 검증하세요.", "deliverables": ["검증 보고서"]},
    ],
    "complex": [
        {"name": "현황 분석", "instructions": "현재 상태를 분석하세요.", "deliverables": ["현황 분석"]},
        {"name": "계획 수립", "instructions": "상세 실행 계획을 수립하세요.", "deliverables": ["실행 계획서"]},
        {"name": "실행", "instructions": "계획에 따라 실행하세요.", "deliverables": ["실행 결과"]},
        {"name": "검증 및 보고", "instructions": "결과를 검증하고 보고서를 작성하세요.", "deliverables": ["최종 보고서"]},
    ],
}


class TaskComplexity(str, Enum):
    """태스크 복잡도."""
    SIMPLE = "simple"       # 단일 작업 — 1 phase
    MODERATE = "moderate"   # 중간 — 2-3 phases
    COMPLEX = "complex"     # 복잡 — 4+ phases


@dataclass
class Phase:
    """작업 단계."""
    name: str
    instructions: str
    deliverables: list[str] = field(default_factory=list)
    order: int = 0


@dataclass
class StructuredPrompt:
    """구조화된 프롬프트."""
    complexity: TaskComplexity
    phases: list[Phase] = field(default_factory=list)
    context: str = ""
    constraints: list[str] = field(default_factory=list)

    def render(self) -> str:
        """엔진 무관 텍스트 프롬프트로 변환."""
        parts: list[str] = []

        if self.context:
            parts.append(f"[배경]\n{self.context}")

        if self.constraints:
            parts.append("[제약]\n" + "\n".join(f"- {c}" for c in self.constraints))

        for phase in sorted(self.phases, key=lambda p: p.order):
            header = f"=== Phase {phase.order}: {phase.name} ==="
            body = phase.instructions
            deliverables = ""
            if phase.deliverables:
                deliverables = "\n산출물: " + ", ".join(phase.deliverables)
            parts.append(f"{header}\n{body}{deliverables}")

        return "\n\n".join(parts)


# ── 복잡도 키워드 ────────────────────────────────────────────

_COMPLEX_KEYWORDS = [
    "아키텍처", "시스템 설계", "마이그레이션", "리팩토링", "통합",
    "architecture", "system design", "migration", "integration",
    "전체", "전반적", "대규모", "플랫폼",
]

_MODERATE_KEYWORDS = [
    "분석", "구현", "설계", "테스트", "검증", "배포",
    "implement", "design", "test", "deploy", "analyze",
    "개선", "최적화",
]


class StructuredPromptGenerator:
    """복잡도 기반 구조화 프롬프트 생성기."""

    def __init__(self, decision_client: DecisionClientProtocol | None = None) -> None:
        self._decision_client = decision_client

    def detect_complexity(self, description: str) -> TaskComplexity:
        """태스크 복잡도 감지 (키워드 기반)."""
        desc_lower = description.lower()
        word_count = len(description.split())

        # 복잡: 키워드 + 긴 설명
        if any(kw in desc_lower for kw in _COMPLEX_KEYWORDS) or word_count > 50:
            return TaskComplexity.COMPLEX

        # 중간: 키워드 or 중간 길이
        if any(kw in desc_lower for kw in _MODERATE_KEYWORDS) or word_count > 20:
            return TaskComplexity.MODERATE

        return TaskComplexity.SIMPLE

    async def generate(
        self, description: str, dept: str, context: str = "",
    ) -> StructuredPrompt:
        """구조화 프롬프트 생성. LLM 실패 시 템플릿 fallback."""
        complexity = self.detect_complexity(description)

        prompt = await self._llm_generate(description, dept, complexity, context)
        if prompt is not None:
            return prompt

        return self._template_generate(description, dept, complexity, context)

    _LLM_PROMPT = (
        "You are creating a structured work plan for a department.\n"
        "Department: {dept_name} ({dept_role})\n"
        "Task: {description}\n"
        "Complexity: {complexity}\n\n"
        "Create a phased work plan. Reply in this EXACT format (one line per phase):\n"
        "PHASE:<phase name>|INSTRUCTIONS:<detailed instructions>|DELIVERABLES:<comma-separated>\n\n"
        "Rules:\n"
        "- Write in Korean\n"
        "- NO engine-specific commands (no /team, /ralph, no CLI-specific syntax)\n"
        "- Each phase produces concrete deliverables\n"
        "- SIMPLE: 1 phase, MODERATE: 2-3 phases, COMPLEX: 4+ phases\n"
        "- Instructions should be actionable and specific\n"
    )

    async def _llm_generate(
        self, description: str, dept: str,
        complexity: TaskComplexity, context: str,
    ) -> StructuredPrompt | None:
        """LLM 기반 프롬프트 생성."""
        if self._decision_client is None:
            return None

        dept_name = KNOWN_DEPTS.get(dept, dept)
        dept_role = DEPT_ROLES.get(dept, "담당 부서")

        prompt = self._LLM_PROMPT.format(
            dept_name=dept_name,
            dept_role=dept_role,
            description=description[:500],
            complexity=complexity.value,
        )

        try:
            response = await asyncio.wait_for(
                self._decision_client.complete(prompt),
                timeout=35.0,
            )
            phases = self._parse_phases(response)
            if not phases:
                return None

            return StructuredPrompt(
                complexity=complexity,
                phases=phases,
                context=context,
                constraints=["엔진 특화 명령어 사용 금지", "단계별 산출물 명시"],
            )
        except Exception as e:
            logger.warning(f"[StructuredPrompt] LLM 생성 실패, fallback: {e}")
            return None

    @staticmethod
    def _parse_phases(response: str) -> list[Phase]:
        """LLM 응답에서 Phase 파싱."""
        phases: list[Phase] = []
        order = 1
        for line in response.strip().split("\n"):
            line = line.strip()
            if "PHASE:" not in line.upper():
                continue

            parts: dict[str, str] = {}
            for segment in line.split("|"):
                if ":" in segment:
                    key, val = segment.split(":", 1)
                    parts[key.strip().upper()] = val.strip()

            name = parts.get("PHASE", "")
            instructions = parts.get("INSTRUCTIONS", "")
            deliverables_str = parts.get("DELIVERABLES", "")

            if not name or not instructions:
                continue

            deliverables = [d.strip() for d in deliverables_str.split(",") if d.strip()]

            phases.append(Phase(
                name=name,
                instructions=instructions,
                deliverables=deliverables,
                order=order,
            ))
            order += 1

        return phases

    def _template_generate(
        self, description: str, dept: str,
        complexity: TaskComplexity, context: str,
    ) -> StructuredPrompt:
        """템플릿 기반 프롬프트 생성 (LLM fallback)."""
        templates = DEFAULT_PHASES.get(dept) or DEFAULT_PHASES.get("_default") or _INLINE_FALLBACK_PHASE
        phase_templates = templates.get(complexity.value) or templates.get("simple") or _INLINE_FALLBACK_PHASE["simple"]

        phases: list[Phase] = []
        for i, tmpl in enumerate(phase_templates, 1):
            phases.append(Phase(
                name=tmpl["name"],
                instructions=f"{tmpl['instructions']}\n\n대상 작업: {description[:200]}",
                deliverables=tmpl["deliverables"],
                order=i,
            ))

        return StructuredPrompt(
            complexity=complexity,
            phases=phases,
            context=context,
            constraints=["엔진 특화 명령어 사용 금지"],
        )


# _DEFAULT_PHASES 하드코딩 제거 완료 (T-aiorg_pm_bot-252).
# 부서별 phase 템플릿은 bots/*.yaml 의 phase_templates 필드와
# bots/default_phases.yaml (_default 키) 로 이동.
# core.constants.DEFAULT_PHASES 로 모듈 로드 시 한 번 캐싱됨.
