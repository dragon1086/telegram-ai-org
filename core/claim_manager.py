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
    CLAIM_TTL = int(os.environ.get("CLAIM_TTL_SEC", "600"))  # 기본 10분 후 만료 (환경변수로 조정 가능)
    TEXT_HASH_TTL = int(os.environ.get("TEXT_HASH_TTL_SEC", "86400"))  # text_hash 중복 방지: 24시간

    def __init__(self) -> None:
        self.CLAIM_FILE_DIR.mkdir(parents=True, exist_ok=True)

    def try_claim_text_hash(self, text_hash: str, org_id: str) -> bool:
        """text_hash 기반 원자적 선점. O_CREAT|O_EXCL로 race condition 방지.
        성공하면 True (최초 선점), 이미 선점됐으면 False.
        """
        hash_lock = self.CLAIM_FILE_DIR / f"hash_{text_hash}.lock"
        payload = json.dumps({"claimed_by": org_id, "ts": time.time()})
        try:
            fd = os.open(str(hash_lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            with os.fdopen(fd, "w") as f:
                f.write(payload)
            return True
        except FileExistsError:
            # 만료 여부 확인 — TTL 초과 시 삭제 후 재선점
            try:
                data = json.loads(hash_lock.read_text(encoding="utf-8"))
                owner = data.get("claimed_by", "unknown")
                age = time.time() - data.get("ts", 0)
                if age > self.TEXT_HASH_TTL:
                    hash_lock.unlink(missing_ok=True)
                    logger.info(f"[claim] text_hash {text_hash[:8]} 만료 ({age:.0f}초 경과, TTL={self.TEXT_HASH_TTL}s) — 재선점 허용")
                    # 재귀 호출로 재시도
                    return self.try_claim_text_hash(text_hash, org_id)
            except Exception:
                owner = "unknown"
                hash_lock.unlink(missing_ok=True)
                return self.try_claim_text_hash(text_hash, org_id)
            logger.debug(f"[claim] 중복 내용 감지 — 이미 {owner}이 처리 중 (text_hash={text_hash[:8]}, {age:.0f}초 경과)")
            return False

    def try_claim(self, message_id: str, org_id: str, text_hash: str | None = None) -> bool:
        """원자적 claim 시도. 성공하면 True, 이미 claimed이면 False.

        os.open O_CREAT|O_EXCL 플래그로 파일 생성 뮤텍스 구현.
        text_hash가 주어지면 hash lock으로 race condition까지 방지.
        """
        # text_hash 기반 원자적 선점 (race condition 방지)
        if text_hash:
            if not self.try_claim_text_hash(text_hash, org_id):
                return False

        claim_path = self.CLAIM_FILE_DIR / f"{message_id}.json"
        payload = json.dumps({"claimed_by": org_id, "ts": time.time(), "text_hash": text_hash or ""})

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

    def submit_bid(self, text_hash: str, org_id: str, score: int) -> None:
        """입찰 파일 저장. bid_{text_hash}_{org_id}.json"""
        bid_path = self.CLAIM_FILE_DIR / f"bid_{text_hash}_{org_id}.json"
        bid_path.write_text(json.dumps({"org_id": org_id, "score": score, "ts": time.time()}))

    def get_winner(self, text_hash: str) -> str | None:
        """모든 bid 파일 읽어서 최고 score org_id 반환. bid 없으면 None."""
        bids = []
        for f in self.CLAIM_FILE_DIR.glob(f"bid_{text_hash}_*.json"):
            try:
                d = json.loads(f.read_text())
                bids.append(d)
            except Exception:
                pass
        if not bids:
            return None
        return max(bids, key=lambda x: x["score"])["org_id"]

    def cleanup_old_claims(self) -> None:
        """TTL 초과 claim/bid/hash-lock 파일 삭제."""
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
        # hash lock 파일은 TEXT_HASH_TTL 적용 (재시작 시 동일 메시지 재처리 방지)
        for lock_file in self.CLAIM_FILE_DIR.glob("*.lock"):
            try:
                data = json.loads(lock_file.read_text(encoding="utf-8"))
                if now - data.get("ts", 0) > self.TEXT_HASH_TTL:
                    lock_file.unlink()
                    removed += 1
            except (json.JSONDecodeError, OSError):
                lock_file.unlink(missing_ok=True)
                removed += 1
        if removed:
            logger.debug(f"[claim] 오래된 claim/bid {removed}개 삭제")
