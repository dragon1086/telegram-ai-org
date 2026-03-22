"""공유 상수 — bots/*.yaml에서 동적 로드 + fallback.

봇 설정 YAML에 dept_name, role, instruction, engine 필드를 두면
코드 수정 없이 부서를 추가/변경할 수 있다.
"""
from __future__ import annotations

from pathlib import Path

from loguru import logger

# bots/ 디렉토리 위치
_BOTS_DIR = Path(__file__).parent.parent / "bots"

_FALLBACK_ENGINES: dict[str, str] = {
    "aiorg_engineering_bot": "codex",
    "aiorg_design_bot": "codex",
    "aiorg_product_bot": "claude-code",
    "aiorg_growth_bot": "claude-code",
    "aiorg_ops_bot": "claude-code",
}

_FALLBACK_ROLES: dict[str, str] = {
    "aiorg_product_bot": "기획/요구사항 분석/PRD 작성",
    "aiorg_engineering_bot": "개발/코딩/API 구현/버그 수정",
    "aiorg_design_bot": "UI/UX 디자인/와이어프레임/프로토타입",
    "aiorg_growth_bot": "성장 전략/마케팅/지표 분석",
    "aiorg_ops_bot": "운영/배포/인프라/모니터링",
}

_FALLBACK_INSTRUCTIONS: dict[str, str] = {
    "aiorg_product_bot": "다음 요청에 대해 기획/요구사항 관점에서 분석하고 PRD 또는 스펙 문서를 작성하세요",
    "aiorg_engineering_bot": "다음 요청에 대해 기술적 관점에서 분석하고 코드 구현 계획 또는 구현을 수행하세요",
    "aiorg_design_bot": "다음 요청에 대해 UI/UX 관점에서 분석하고 디자인 방안을 제시하세요",
    "aiorg_growth_bot": "다음 요청에 대해 성장/마케팅 관점에서 분석하고 전략을 수립하세요",
    "aiorg_ops_bot": "다음 요청에 대해 운영/인프라 관점에서 분석하고 배포 및 모니터링 계획을 수립하세요",
}


def _load_bot_configs(bots_dir: Path | None = None) -> list[dict]:
    """bots/*.yaml 파일들을 로드하여 봇 설정 딕셔너리 리스트 반환.

    Bot Loading Flow:
        1. bots/ 디렉토리의 모든 .yaml 파일을 스캔
        2. 각 YAML에서 org_id, dept_name, engine, role, instruction 추출
        3. KNOWN_DEPTS, BOT_ENGINE_MAP, DEPT_ROLES, DEPT_INSTRUCTIONS 딕셔너리 구성
        4. workers.yaml은 레거시 파일로, 현재 런타임에서 사용하지 않음
        5. ~/.claude/agents/는 봇 내부 Claude Code sub-agent 위임용 (조직 봇 정의 아님)

    Returns:
        list[dict]: 각 봇 설정 딕셔너리 (org_id, dept_name, engine 등 포함)
    """
    target = bots_dir or _BOTS_DIR
    if not target.is_dir():
        return []

    configs: list[dict] = []
    try:
        import yaml
    except ImportError:
        logger.debug("[constants] PyYAML 없음 — fallback 사용")
        return []

    for yaml_file in sorted(target.glob("*.yaml")):
        try:
            cfg = yaml.safe_load(yaml_file.read_text()) or {}
            if cfg.get("org_id"):
                configs.append(cfg)
        except Exception as e:
            logger.warning(f"[constants] {yaml_file.name} 로드 실패: {e}")

    return configs


def load_known_depts(bots_dir: Path | None = None) -> dict[str, str]:
    """부서 봇 목록 로드 (PM 제외). {org_id: dept_name}

    bots/*.yaml 로드 실패 시 빈 dict 반환 (플랫폼 이식성 보장).
    """
    configs = _load_bot_configs(bots_dir)
    if not configs:
        return {}

    depts: dict[str, str] = {}
    for cfg in configs:
        org_id = cfg["org_id"]
        if cfg.get("is_pm"):
            continue
        dept_name = cfg.get("dept_name", org_id)
        depts[org_id] = dept_name

    return depts


def load_bot_engines(bots_dir: Path | None = None) -> dict[str, str]:
    """봇별 엔진 매핑 로드. {org_id: engine}"""
    configs = _load_bot_configs(bots_dir)
    if not configs:
        return dict(_FALLBACK_ENGINES)

    engines: dict[str, str] = {}
    for cfg in configs:
        org_id = cfg["org_id"]
        if cfg.get("is_pm"):
            continue
        engines[org_id] = cfg.get("engine", "claude-code")

    return engines or dict(_FALLBACK_ENGINES)


def load_dept_roles(bots_dir: Path | None = None) -> dict[str, str]:
    """부서별 역할 설명 로드. {org_id: role}"""
    configs = _load_bot_configs(bots_dir)
    if not configs:
        return dict(_FALLBACK_ROLES)

    roles: dict[str, str] = {}
    for cfg in configs:
        org_id = cfg["org_id"]
        if cfg.get("is_pm"):
            continue
        role = cfg.get("role", "")
        if role:
            roles[org_id] = role

    return roles or dict(_FALLBACK_ROLES)


def load_dept_instructions(bots_dir: Path | None = None) -> dict[str, str]:
    """부서별 지시문 로드. {org_id: instruction}"""
    configs = _load_bot_configs(bots_dir)
    if not configs:
        return dict(_FALLBACK_INSTRUCTIONS)

    instructions: dict[str, str] = {}
    for cfg in configs:
        org_id = cfg["org_id"]
        if cfg.get("is_pm"):
            continue
        instruction = cfg.get("instruction", "")
        if instruction:
            instructions[org_id] = instruction

    return instructions or dict(_FALLBACK_INSTRUCTIONS)


def load_default_phases(bots_dir: Path | None = None) -> dict[str, dict[str, list[dict]]]:
    """부서별 phase 템플릿 로드. {org_id: {complexity: [phases]}}

    로드 우선순위:
      1. 각 bots/*.yaml 의 phase_templates 필드
      2. bots/default_phases.yaml 의 _default 키
      3. 위 모두 실패 시 빈 dict 반환 (호출자가 인라인 기본값 사용)
    """
    target = bots_dir or _BOTS_DIR
    result: dict[str, dict[str, list[dict]]] = {}

    try:
        import yaml  # noqa: PLC0415
    except ImportError:
        logger.debug("[constants] PyYAML 없음 — default_phases 로드 불가")
        return result

    # 봇별 phase_templates 로드
    configs = _load_bot_configs(bots_dir)
    for cfg in configs:
        org_id = cfg.get("org_id")
        templates = cfg.get("phase_templates")
        if org_id and isinstance(templates, dict):
            result[org_id] = templates

    # _default 는 별도 파일에서 로드
    default_file = target / "default_phases.yaml"
    if default_file.exists():
        try:
            data = yaml.safe_load(default_file.read_text()) or {}
            if "_default" in data:
                result["_default"] = data["_default"]
        except Exception as e:
            logger.warning(f"[constants] default_phases.yaml 로드 실패: {e}")

    return result


# 모듈 로드 시 한 번만 실행 (캐싱)
KNOWN_DEPTS: dict[str, str] = load_known_depts()
BOT_ENGINE_MAP: dict[str, str] = load_bot_engines()
DEPT_ROLES: dict[str, str] = load_dept_roles()
DEPT_INSTRUCTIONS: dict[str, str] = load_dept_instructions()
DEFAULT_PHASES: dict[str, dict[str, list[dict]]] = load_default_phases()
