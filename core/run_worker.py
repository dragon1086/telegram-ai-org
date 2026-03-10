"""워커 봇 실행 엔트리포인트.

사용법: python -m core.run_worker --name <worker_name>
"""
from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="워커 봇 실행")
    parser.add_argument("--name", required=True, help="workers.yaml에 등록된 워커 이름")
    parser.add_argument(
        "--workers-yaml",
        default="workers.yaml",
        help="workers.yaml 경로 (기본값: ./workers.yaml)",
    )
    args = parser.parse_args()

    # 설정 로드
    config_file = Path.home() / ".ai-org" / "config.yaml"
    if config_file.exists():
        import re
        text = config_file.read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

    from dotenv import load_dotenv
    load_dotenv()

    from core.worker_registry import WorkerRegistry

    registry = WorkerRegistry(config_path=args.workers_yaml)
    registry.load()

    bot = registry.get_worker(args.name)
    if bot is None:
        raise SystemExit(f"❌ 워커 '{args.name}'를 찾을 수 없음. workers.yaml을 확인하세요.")

    group_chat_id = int(os.environ["TELEGRAM_GROUP_CHAT_ID"])
    asyncio.run(bot.run(group_chat_id))


if __name__ == "__main__":
    main()
