"""메시지별 담당 PM claim 관리 — 파일 기반 원자적 뮤텍스."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from loguru import logger


class ClaimManager:
    """메시지별 담당 PM claim 관리 (파일 기반 뮤텍스).

    ~/.ai-org/claims/{message_id}.json → {"claimed_by": "pm_global", "ts": ...}
    """

    CLAIM_FILE_DIR = Path.home() / ".ai-org" / "claims"
    CLAIM_TIMEOUT = 3.0   # 3초 내 claim 없으면 기본 PM 담당
    CLAIM_TTL = 3600       # 1시간 후 자동 삭제

    def __init__(self) -> None:
        self.CLAIM_FILE_DIR.mkdir(parents=True, exist_ok=True)

    def try_claim(self, message_id: str, org_id: str) -> bool:
        """원자적 claim 시도. 성공하면 True, 이미 claimed이면 False.

        os.open O_CREAT|O_EXCL 플래그로 파일 생성 뮤텍스 구현.
        """
        claim_path = self.CLAIM_FILE_DIR / f"{message_id}.json"
        payload = json.dumps({"claimed_by": org_id, "ts": time.time()})

        try:
            fd = os.open(
                str(claim_path),
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o644,
            )
            with os.fdopen(fd, "w") as f:
                f.write(payload)
            logger.info(f"[claim] {org_id} → message {message_id} claim 성공")
            return True
        except FileExistsError:
            existing = self.get_claimer(message_id)
            logger.debug(f"[claim] message {message_id} 이미 {existing}이 claim함")
            return False
        except OSError as e:
            logger.error(f"[claim] claim 실패: {e}")
            return False

    def get_claimer(self, message_id: str) -> str | None:
        """현재 claim한 org_id 반환. 없으면 None."""
        claim_path = self.CLAIM_FILE_DIR / f"{message_id}.json"
        if not claim_path.exists():
            return None
        try:
            data = json.loads(claim_path.read_text(encoding="utf-8"))
            return data.get("claimed_by")
        except (json.JSONDecodeError, OSError):
            return None

    def cleanup_old_claims(self) -> None:
        """TTL 초과 claim 파일 삭제."""
        now = time.time()
        removed = 0
        for claim_file in self.CLAIM_FILE_DIR.glob("*.json"):
            try:
                data = json.loads(claim_file.read_text(encoding="utf-8"))
                if now - data.get("ts", 0) > self.CLAIM_TTL:
                    claim_file.unlink()
                    removed += 1
            except (json.JSONDecodeError, OSError):
                claim_file.unlink(missing_ok=True)
                removed += 1
        if removed:
            logger.debug(f"[claim] 오래된 claim {removed}개 삭제")
