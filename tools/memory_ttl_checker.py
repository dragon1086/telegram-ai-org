#!/usr/bin/env python3
"""
memory_ttl_checker.py — L2 TTL 만료 체크 및 L3 자동 이동 스크립트

실행: python3 /Users/rocky/telegram-ai-org/tools/memory_ttl_checker.py
크론: 매일 00:00 KST (15:00 UTC) 자동 실행

동작:
  1. MEMORY.md 파싱 → L2 항목의 expires_at을 오늘 날짜와 비교
  2. 만료된 항목을 L3 Archive > L3 만료 이동 항목 섹션으로 이동
  3. 이동 내역을 logs/memory_ttl.log에 기록
"""

import re
import sys
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Optional, Dict, List

# ── 경로 설정 ──────────────────────────────────────────────────────────────
MEMORY_MD = Path("/Users/rocky/.claude/projects/-Users-rocky-telegram-ai-org/memory/MEMORY.md")
LOG_DIR   = Path("/Users/rocky/telegram-ai-org/logs")
LOG_FILE  = LOG_DIR / "memory_ttl.log"

# ── 로거 초기화 ────────────────────────────────────────────────────────────
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [TTL-CHECKER] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


# ── 헬퍼 ──────────────────────────────────────────────────────────────────
def parse_date(s: str) -> Optional[date]:
    """YYYY-MM-DD 문자열을 date로 변환. 파싱 실패 시 None."""
    s = s.strip()
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def is_expired(expires_at_str: str, today: date) -> bool:
    """expires_at 문자열이 오늘 이전이면 True (만료)."""
    if expires_at_str.strip().lower() in ("permanent", "session-end", "-", ""):
        return False
    d = parse_date(expires_at_str)
    return d is not None and d < today


# ── L2 완료 태스크 테이블 처리 ─────────────────────────────────────────────
# 헤더: | id | title | created_at | status | resolved_at | layer | expires_at |
TASK_HEADER_PATTERN = re.compile(
    r"\|\s*id\s*\|\s*title\s*\|\s*created_at\s*\|\s*status\s*\|\s*resolved_at\s*\|\s*layer\s*\|\s*expires_at\s*\|"
)

def parse_task_row(line: str) -> Optional[Dict]:
    """테이블 행을 파싱하여 dict 반환. 구분선이면 None."""
    line = line.strip()
    if not line.startswith("|") or re.match(r"\|[-| ]+\|", line):
        return None
    cols = [c.strip() for c in line.strip("|").split("|")]
    if len(cols) < 7:
        return None
    return {
        "id": cols[0],
        "title": cols[1],
        "created_at": cols[2],
        "status": cols[3],
        "resolved_at": cols[4],
        "layer": cols[5],
        "expires_at": cols[6],
        "_raw": line,
    }


def format_task_row(r: dict) -> str:
    return (
        f"| {r['id']} | {r['title']} | {r['created_at']} | "
        f"{r['status']} | {r['resolved_at']} | {r['layer']} | {r['expires_at']} |"
    )


# ── L2 기억 항목 테이블 처리 ───────────────────────────────────────────────
# 헤더: | id | title | created_at | last_accessed | ttl_days | score | layer | expires_at |
MEM_HEADER_PATTERN = re.compile(
    r"\|\s*id\s*\|\s*title\s*\|\s*created_at\s*\|\s*last_accessed\s*\|\s*ttl_days\s*\|\s*score\s*\|\s*layer\s*\|\s*expires_at\s*\|"
)

def parse_mem_row(line: str) -> Optional[Dict]:
    line = line.strip()
    if not line.startswith("|") or re.match(r"\|[-| ]+\|", line):
        return None
    cols = [c.strip() for c in line.strip("|").split("|")]
    if len(cols) < 8:
        return None
    return {
        "id": cols[0],
        "title": cols[1],
        "created_at": cols[2],
        "last_accessed": cols[3],
        "ttl_days": cols[4],
        "score": cols[5],
        "layer": cols[6],
        "expires_at": cols[7],
        "_raw": line,
    }


# ── L3 만료 이동 항목 포맷 ─────────────────────────────────────────────────
# 헤더: | id | title | layer | archived_at | original_expires_at | expires_at |
L3_ARCHIVE_HEADER = "| id | title | layer | archived_at | original_expires_at | expires_at |"
L3_ARCHIVE_SEP    = "|----|-------|-------|-------------|---------------------|------------|"

def format_l3_task_row(r: dict, today: date) -> str:
    archived_at = today.isoformat()
    original_expires = r.get("expires_at", "-")
    # L3 항목은 archived_at + 30일 후 삭제 예정
    from datetime import timedelta
    l3_expires = (today + timedelta(days=30)).isoformat()
    return (
        f"| {r['id']} | {r['title']} | L3 | {archived_at} | {original_expires} | {l3_expires} |"
    )


# ── 메인 처리 ─────────────────────────────────────────────────────────────
def run():
    today = date.today()
    logger.info(f"=== memory_ttl_checker 시작 (기준일: {today}) ===")

    if not MEMORY_MD.exists():
        logger.error(f"MEMORY.md 파일을 찾을 수 없음: {MEMORY_MD}")
        sys.exit(1)

    content = MEMORY_MD.read_text(encoding="utf-8")
    lines   = content.splitlines(keepends=True)

    expired_items: list[dict] = []   # 만료된 항목 수집
    new_lines: list[str]     = []    # 수정된 콘텐츠

    # ── 상태 머신 ────────────────────────────────────────────────────────
    in_l2_task_table = False   # L2 완료 태스크 테이블 내부
    in_l2_mem_table  = False   # L2 기억 항목 테이블 내부
    in_l3_archive    = False   # L3 Archive 섹션 내부
    in_l3_moved_table = False  # L3 만료 이동 항목 테이블 내부
    l3_table_header_written = False

    for raw_line in lines:
        line = raw_line.rstrip("\n")

        # ── 섹션 감지 ────────────────────────────────────────────────────
        if line.startswith("## L2 Mid-term"):
            in_l2_task_table = False
            in_l2_mem_table  = False
            in_l3_archive    = False
            in_l3_moved_table = False
        elif line.startswith("## L3 Archive"):
            in_l2_task_table = False
            in_l2_mem_table  = False
            in_l3_archive    = True
        elif line.startswith("## ") and in_l3_archive:
            # 다른 ## 섹션으로 나가면 L3 종료
            in_l3_archive    = False
            in_l3_moved_table = False

        # ── L3 만료 이동 항목 테이블 감지 ────────────────────────────────
        if in_l3_archive and "L3 만료 이동 항목" in line:
            in_l3_moved_table = True

        # ── L2 완료 태스크 테이블 헤더 감지 ──────────────────────────────
        if TASK_HEADER_PATTERN.search(line) and not in_l3_moved_table:
            in_l2_task_table = True
            in_l2_mem_table  = False
            new_lines.append(raw_line)
            continue

        # ── L2 기억 항목 테이블 헤더 감지 ────────────────────────────────
        if MEM_HEADER_PATTERN.search(line) and not in_l3_moved_table:
            in_l2_mem_table  = True
            in_l2_task_table = False
            new_lines.append(raw_line)
            continue

        # ── 다른 헤더(##, ###)를 만나면 테이블 종료 ─────────────────────
        if line.startswith("#") and (in_l2_task_table or in_l2_mem_table):
            in_l2_task_table = False
            in_l2_mem_table  = False

        # ── L2 완료 태스크 행 처리 ────────────────────────────────────────
        if in_l2_task_table and line.startswith("|"):
            row = parse_task_row(line)
            if row and row["id"] not in ("id",):  # 헤더 스킵
                if is_expired(row["expires_at"], today):
                    logger.info(f"[EXPIRE] L2→L3 이동: {row['id']} ({row['title'][:40]}) expires={row['expires_at']}")
                    expired_items.append({"type": "task", **row})
                    # 이 행은 new_lines에 추가하지 않음 (L2에서 제거)
                    continue
        # ── L2 기억 항목 행 처리 ─────────────────────────────────────────
        elif in_l2_mem_table and line.startswith("|"):
            row = parse_mem_row(line)
            if row and row["id"] not in ("id",):
                if is_expired(row["expires_at"], today):
                    logger.info(f"[EXPIRE] L2→L3 이동 (기억): {row['id']} ({row['title'][:40]}) expires={row['expires_at']}")
                    expired_items.append({"type": "mem", **row})
                    continue

        # ── L3 만료 이동 항목 테이블에 새 행 삽입 ─────────────────────────
        # 테이블 마지막 빈 행(| id | ... | 패턴 다음 구분선 이후)에 새 항목 append
        if in_l3_moved_table and in_l3_archive:
            # 테이블 헤더 행이 아직 안 쓰인 경우 헤더 쓰기
            if L3_ARCHIVE_HEADER in line:
                l3_table_header_written = True
                new_lines.append(raw_line)
                continue
            # 테이블 구분선 다음 빈 마지막 행 뒤에 만료 항목 삽입
            if l3_table_header_written and line.strip() == "" and expired_items:
                # 현재 빈 줄 앞에 만료 항목들 삽입
                for item in expired_items:
                    new_row = format_l3_task_row(item, today)
                    new_lines.append(new_row + "\n")
                    logger.info(f"[ARCHIVE] L3 기록 완료: {item['id']}")
                expired_items_written = True
                # 빈 줄도 유지
                new_lines.append(raw_line)
                expired_items = []  # 중복 방지
                continue

        new_lines.append(raw_line)

    # ── 만료 항목이 아직 남아있으면 L3 섹션 끝에 강제 append ─────────────
    if expired_items:
        # 파일 끝에 추가 (L3 섹션이 파일 마지막인 경우)
        for item in expired_items:
            new_row = format_l3_task_row(item, today)
            new_lines.append(new_row + "\n")
            logger.info(f"[ARCHIVE-APPEND] L3 기록 완료: {item['id']}")

    # ── 파일 저장 ─────────────────────────────────────────────────────────
    new_content = "".join(new_lines)
    MEMORY_MD.write_text(new_content, encoding="utf-8")

    moved_count = sum(1 for line in new_lines if "archived_at" not in line)  # 단순 카운트 대신
    logger.info(f"=== 완료: MEMORY.md 업데이트. 만료 처리 항목 없음 (오늘 기준) ===")
    logger.info(f"=== memory_ttl_checker 종료 ===")
    return 0


if __name__ == "__main__":
    sys.exit(run())
