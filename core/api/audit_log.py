"""core.api.audit_log — 태스크 작업 감사 로그 (Phase 3-A).

피처 플래그: ENABLE_AUDIT_LOG (기본 false)
포맷: JSONL (한 줄 = 한 이벤트), data/audit.log 저장.

기록 항목: 태스크 생성/삭제 시 timestamp, action, task_id, org_id, api_key, client_ip.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

ENABLE_AUDIT_LOG: bool = os.environ.get("ENABLE_AUDIT_LOG", "false").lower() in ("true", "1")
DEFAULT_AUDIT_LOG_PATH: Path = Path(os.environ.get("AIMESH_AUDIT_LOG_PATH", "data/audit.log"))


def write_audit_event(
    action: str,
    task_id: str,
    org_id: str = "",
    api_key: str = "",
    client_ip: str = "",
    extra: dict | None = None,
    log_path: Path | None = None,
) -> None:
    """감사 이벤트를 JSONL 형식으로 로그 파일에 기록합니다.

    ENABLE_AUDIT_LOG=false 면 즉시 반환합니다.

    Args:
        action: 작업 유형 (task_created, task_deleted, task_not_found 등).
        task_id: 대상 태스크 ID.
        org_id: 담당 조직 ID.
        api_key: 요청에 사용된 API Key (마스킹: 앞 8자만 보존).
        client_ip: 클라이언트 IP 주소.
        extra: 추가 컨텍스트 딕셔너리.
        log_path: 로그 파일 경로 (None이면 DEFAULT_AUDIT_LOG_PATH 사용).
    """
    if not ENABLE_AUDIT_LOG:
        return

    resolved_path = log_path or DEFAULT_AUDIT_LOG_PATH
    resolved_path.parent.mkdir(parents=True, exist_ok=True)

    # API Key 마스킹: 앞 8자만 보존
    masked_key = api_key[:8] + "****" if len(api_key) > 8 else api_key

    event = {
        "timestamp": time.time(),
        "action": action,
        "task_id": task_id,
        "org_id": org_id,
        "api_key_prefix": masked_key,
        "client_ip": client_ip,
    }
    if extra:
        event["extra"] = extra

    with open(resolved_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def read_audit_events(
    log_path: Path | None = None,
    limit: int = 100,
) -> list[dict]:
    """감사 로그 파일에서 최신 이벤트를 읽어 반환합니다.

    Args:
        log_path: 로그 파일 경로.
        limit: 최대 반환 이벤트 수 (최신 N개).

    Returns:
        이벤트 dict 목록 (최신 순).
    """
    resolved_path = log_path or DEFAULT_AUDIT_LOG_PATH
    if not resolved_path.exists():
        return []

    lines = resolved_path.read_text(encoding="utf-8").strip().splitlines()
    events = []
    for line in lines:
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    return list(reversed(events))[-limit:]
