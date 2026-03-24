"""telegram-ai-org package entry point.

Usage:
    telegram-ai-org          # PyPI 설치 후 CLI 실행
    python -m telegram_ai_org  # 직접 모듈 실행

두 방식 모두 PM 봇(main.py)을 실행합니다.
"""
from __future__ import annotations


def main() -> None:
    """PM 봇 실행 진입점.

    cli.pm() 을 통해 main.py 를 runpy 로 실행합니다.
    PyPI 설치 시 'telegram-ai-org' 명령어의 실제 진입점입니다.
    """
    # cli.py 의 pm() 함수 위임 — flat layout 에서 cli 모듈로 직접 임포트
    from cli import pm  # noqa: PLC0415

    pm()


if __name__ == "__main__":
    main()
