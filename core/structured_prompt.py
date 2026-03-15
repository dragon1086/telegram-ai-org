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

from core.constants import KNOWN_DEPTS, DEPT_ROLES
from core.pm_decision import DecisionClientProtocol


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
        templates = _DEFAULT_PHASES.get(dept, _DEFAULT_PHASES["_default"])
        phase_templates = templates.get(complexity.value, templates["simple"])

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


# ── 부서별 기본 Phase 템플릿 ──────────────────────────────────

_DEFAULT_PHASES: dict[str, dict[str, list[dict]]] = {
    "aiorg_product_bot": {
        "simple": [
            {"name": "분석 및 기획", "instructions": "요청을 분석하고 핵심 요구사항을 정리하세요.",
             "deliverables": ["요구사항 정리 문서"]},
        ],
        "moderate": [
            {"name": "요구사항 분석", "instructions": "요청의 배경과 목표를 분석하고 핵심 요구사항을 도출하세요.",
             "deliverables": ["요구사항 목록"]},
            {"name": "기획서 작성", "instructions": "도출된 요구사항을 바탕으로 구체적인 기획서를 작성하세요.",
             "deliverables": ["기획서/PRD"]},
            {"name": "검토", "instructions": "기획서의 완성도와 실현 가능성을 검토하세요.",
             "deliverables": ["검토 의견"]},
        ],
        "complex": [
            {"name": "현황 분석", "instructions": "현재 상태와 문제점을 분석하세요.",
             "deliverables": ["현황 분석 보고서"]},
            {"name": "요구사항 정의", "instructions": "기능/비기능 요구사항을 체계적으로 정의하세요.",
             "deliverables": ["요구사항 명세서"]},
            {"name": "기획서 작성", "instructions": "상세 기획서와 로드맵을 작성하세요.",
             "deliverables": ["상세 기획서", "로드맵"]},
            {"name": "리스크 분석", "instructions": "구현 시 예상되는 리스크와 대응 방안을 정리하세요.",
             "deliverables": ["리스크 분석 보고서"]},
        ],
    },
    "aiorg_engineering_bot": {
        "simple": [
            {"name": "구현", "instructions": "요청사항을 분석하고 코드를 구현하세요.",
             "deliverables": ["구현 코드"]},
        ],
        "moderate": [
            {"name": "기술 분석", "instructions": "기술적 접근 방법을 분석하고 구현 계획을 수립하세요.",
             "deliverables": ["기술 분석 문서"]},
            {"name": "구현", "instructions": "계획에 따라 코드를 구현하세요.",
             "deliverables": ["구현 코드"]},
            {"name": "테스트 및 검증", "instructions": "구현된 코드를 테스트하고 검증하세요.",
             "deliverables": ["테스트 결과"]},
        ],
        "complex": [
            {"name": "아키텍처 설계", "instructions": "시스템 아키텍처와 컴포넌트 구조를 설계하세요.",
             "deliverables": ["아키텍처 문서"]},
            {"name": "핵심 구현", "instructions": "핵심 로직과 데이터 모델을 구현하세요.",
             "deliverables": ["핵심 코드"]},
            {"name": "통합 구현", "instructions": "외부 연동과 API를 구현하세요.",
             "deliverables": ["통합 코드"]},
            {"name": "테스트", "instructions": "단위/통합 테스트를 작성하고 실행하세요.",
             "deliverables": ["테스트 코드", "테스트 결과"]},
        ],
    },
    "aiorg_design_bot": {
        "simple": [
            {"name": "디자인", "instructions": "요청에 맞는 UI/UX 디자인안을 제시하세요.",
             "deliverables": ["디자인안"]},
        ],
        "moderate": [
            {"name": "사용자 분석", "instructions": "대상 사용자와 사용 시나리오를 분석하세요.",
             "deliverables": ["사용자 분석"]},
            {"name": "와이어프레임", "instructions": "화면 구조와 인터랙션을 설계하세요.",
             "deliverables": ["와이어프레임"]},
            {"name": "디자인 시안", "instructions": "최종 디자인 시안을 제작하세요.",
             "deliverables": ["디자인 시안"]},
        ],
        "complex": [
            {"name": "UX 리서치", "instructions": "사용자 니즈와 경쟁사를 분석하세요.",
             "deliverables": ["UX 리서치 보고서"]},
            {"name": "정보 구조 설계", "instructions": "정보 계층과 네비게이션을 설계하세요.",
             "deliverables": ["IA 문서"]},
            {"name": "와이어프레임", "instructions": "주요 화면의 와이어프레임을 작성하세요.",
             "deliverables": ["와이어프레임"]},
            {"name": "디자인 시스템", "instructions": "일관된 디자인 시스템과 최종 시안을 제작하세요.",
             "deliverables": ["디자인 시스템", "최종 시안"]},
        ],
    },
    "aiorg_growth_bot": {
        "simple": [
            {"name": "분석 및 전략", "instructions": "요청에 대한 성장/마케팅 분석과 전략을 제시하세요.",
             "deliverables": ["전략 보고서"]},
        ],
        "moderate": [
            {"name": "시장 분석", "instructions": "시장 현황과 경쟁 환경을 분석하세요.",
             "deliverables": ["시장 분석"]},
            {"name": "전략 수립", "instructions": "성장 전략과 실행 계획을 수립하세요.",
             "deliverables": ["성장 전략서"]},
            {"name": "KPI 설정", "instructions": "성과 측정을 위한 KPI를 정의하세요.",
             "deliverables": ["KPI 대시보드"]},
        ],
        "complex": [
            {"name": "현황 진단", "instructions": "현재 성장 지표와 문제점을 진단하세요.",
             "deliverables": ["현황 진단 보고서"]},
            {"name": "시장/경쟁사 분석", "instructions": "시장 트렌드와 경쟁사를 심층 분석하세요.",
             "deliverables": ["시장 분석 보고서"]},
            {"name": "전략 수립", "instructions": "단계별 성장 전략을 수립하세요.",
             "deliverables": ["성장 전략서", "실행 로드맵"]},
            {"name": "측정 체계", "instructions": "성과 측정 체계와 A/B 테스트 계획을 수립하세요.",
             "deliverables": ["측정 체계", "실험 계획"]},
        ],
    },
    "aiorg_ops_bot": {
        "simple": [
            {"name": "운영 계획", "instructions": "요청에 대한 운영/배포 계획을 수립하세요.",
             "deliverables": ["운영 계획"]},
        ],
        "moderate": [
            {"name": "인프라 분석", "instructions": "현재 인프라 상태를 분석하세요.",
             "deliverables": ["인프라 분석"]},
            {"name": "배포 계획", "instructions": "배포 전략과 절차를 수립하세요.",
             "deliverables": ["배포 계획서"]},
            {"name": "모니터링", "instructions": "모니터링 및 롤백 계획을 수립하세요.",
             "deliverables": ["모니터링 계획"]},
        ],
        "complex": [
            {"name": "인프라 아키텍처", "instructions": "인프라 아키텍처를 설계/검토하세요.",
             "deliverables": ["인프라 아키텍처 문서"]},
            {"name": "CI/CD 파이프라인", "instructions": "빌드/배포 파이프라인을 설계하세요.",
             "deliverables": ["CI/CD 설계서"]},
            {"name": "배포 실행", "instructions": "단계별 배포 절차를 수립하세요.",
             "deliverables": ["배포 절차서"]},
            {"name": "운영 안정화", "instructions": "모니터링, 알림, 롤백 계획을 수립하세요.",
             "deliverables": ["운영 매뉴얼"]},
        ],
    },
    "_default": {
        "simple": [
            {"name": "실행", "instructions": "요청사항을 분석하고 실행하세요.",
             "deliverables": ["실행 결과"]},
        ],
        "moderate": [
            {"name": "분석", "instructions": "요청사항을 분석하세요.",
             "deliverables": ["분석 결과"]},
            {"name": "실행", "instructions": "분석 결과를 바탕으로 실행하세요.",
             "deliverables": ["실행 결과"]},
            {"name": "검증", "instructions": "실행 결과를 검증하세요.",
             "deliverables": ["검증 보고서"]},
        ],
        "complex": [
            {"name": "현황 분석", "instructions": "현재 상태를 분석하세요.",
             "deliverables": ["현황 분석"]},
            {"name": "계획 수립", "instructions": "상세 실행 계획을 수립하세요.",
             "deliverables": ["실행 계획서"]},
            {"name": "실행", "instructions": "계획에 따라 실행하세요.",
             "deliverables": ["실행 결과"]},
            {"name": "검증 및 보고", "instructions": "결과를 검증하고 보고서를 작성하세요.",
             "deliverables": ["최종 보고서"]},
        ],
    },
}
