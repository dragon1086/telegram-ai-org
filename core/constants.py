"""공유 상수 — bots/*.yaml에서 동적 로드 + fallback.

봇 설정 YAML에 dept_name, role, instruction, engine 필드를 두면
코드 수정 없이 부서를 추가/변경할 수 있다.
"""
from __future__ import annotations

from pathlib import Path

from loguru import logger

# bots/ 디렉토리 위치
_BOTS_DIR = Path(__file__).parent.parent / "bots"

# 하드코딩 fallback (bots/ 디렉토리 없거나 파싱 실패 시)
_FALLBACK_DEPTS: dict[str, str] = {
    "aiorg_product_bot": "기획실",
    "aiorg_engineering_bot": "개발실",
    "aiorg_design_bot": "디자인실",
    "aiorg_growth_bot": "성장실",
    "aiorg_ops_bot": "운영실",
}

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
    """bots/*.yaml 파일들을 로드. 실패 시 빈 리스트."""
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
    """부서 봇 목록 로드 (PM 제외). {org_id: dept_name}"""
    configs = _load_bot_configs(bots_dir)
    if not configs:
        return dict(_FALLBACK_DEPTS)

    depts: dict[str, str] = {}
    for cfg in configs:
        org_id = cfg["org_id"]
        if cfg.get("is_pm"):
            continue
        dept_name = cfg.get("dept_name", org_id)
        depts[org_id] = dept_name

    return depts or dict(_FALLBACK_DEPTS)


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


# 모듈 로드 시 한 번만 실행 (캐싱)
KNOWN_DEPTS: dict[str, str] = load_known_depts()
BOT_ENGINE_MAP: dict[str, str] = load_bot_engines()
DEPT_ROLES: dict[str, str] = load_dept_roles()
DEPT_INSTRUCTIONS: dict[str, str] = load_dept_instructions()
