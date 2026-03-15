#!/usr/bin/env bash
set -euo pipefail

echo "=== telegram-ai-org 초기 설정 ==="

VENV_DIR=".venv"
VENV_PYTHON="$VENV_DIR/bin/python"

# Python 버전 확인
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python: $python_version"

# 가상환경 생성
if [ ! -x "$VENV_PYTHON" ]; then
    echo "가상환경 생성 중..."
    python3 -m venv "$VENV_DIR"
fi

# 의존성 설치
echo "의존성 설치 중..."
if command -v uv &>/dev/null; then
    uv pip install --python "$VENV_PYTHON" -e ".[dev]"
else
    "$VENV_PYTHON" -m pip install --upgrade pip
    "$VENV_PYTHON" -m pip install -e ".[dev]"
fi

# .env 파일 생성
if [ ! -f .env ]; then
    cp .env.example .env
    echo ".env 파일 생성됨. 토큰을 입력하세요."
fi

# 컨텍스트 DB 디렉토리 생성
mkdir -p ~/.ai-org/workspace
echo "컨텍스트 DB 디렉토리: ~/.ai-org/"

echo ""
echo "✅ 설정 완료!"
echo "다음 단계: .env 파일에 Telegram 봇 토큰을 입력하고 ./.venv/bin/python scripts/setup_wizard.py 실행"
