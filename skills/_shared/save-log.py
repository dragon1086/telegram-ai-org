#!/usr/bin/env python3
"""
save-log.py — Shared atomic JSONL append utility for skill logs.

Usage:
    python skills/_shared/save-log.py '{"key": "value"}' <output_path>

Examples:
    python skills/_shared/save-log.py '{"week": "2026-W12"}' skills/weekly-review/data/weekly-log.jsonl
    python skills/_shared/save-log.py '{"sprint": "S3"}' skills/retro/data/retro-log.jsonl

Appends a single JSON record to the specified JSONL file
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
        print(
            "Usage: save-log.py '<json string>' [output_path]",
            file=sys.stderr,
        )
        sys.exit(1)

    raw = sys.argv[1]
    output_path = Path(sys.argv[2]) if len(sys.argv) >= 3 else Path("skills/weekly-review/data/weekly-log.jsonl")

    # Parse input JSON — fail fast if malformed
    try:
        record = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid JSON input: {exc}", file=sys.stderr)
        sys.exit(1)

    # Stamp with saved_at if not already present
    if "saved_at" not in record:
        record["saved_at"] = datetime.now(timezone.utc).isoformat()

    # Ensure data directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Atomic append with exclusive lock
    with open(output_path, "a", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)

    print(f"OK: appended to {output_path}")


if __name__ == "__main__":
    main()
