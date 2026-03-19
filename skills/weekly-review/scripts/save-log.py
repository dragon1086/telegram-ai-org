#!/usr/bin/env python3
"""
save-log.py — Atomic JSONL append for weekly-review logs.

Usage:
    python save-log.py '{"week": "2026-W12", "summary": "..."}'

Appends a single JSON record to skills/weekly-review/data/weekly-log.jsonl
using fcntl.flock for safe concurrent writes.
"""

import fcntl
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: save-log.py '<json string>'", file=sys.stderr)
        sys.exit(1)

    raw = sys.argv[1]

    # Parse input JSON — fail fast if malformed
    try:
        record = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid JSON input: {exc}", file=sys.stderr)
        sys.exit(1)

    # Stamp with saved_at if not already present
    if "saved_at" not in record:
        record["saved_at"] = datetime.now(timezone.utc).isoformat()

    # Resolve data directory relative to this script's location
    script_dir = Path(__file__).parent.resolve()
    data_dir = script_dir.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    log_path = data_dir / "weekly-log.jsonl"

    # Atomic append with exclusive lock
    with open(log_path, "a", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)

    print(f"OK: appended to {log_path}")


if __name__ == "__main__":
    main()
