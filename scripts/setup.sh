#!/usr/bin/env bash
set -euo pipefail

echo "=== telegram-ai-org 초기 설정 ==="

# Python 버전 확인
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python: $python_version"

# uv 설치 확인
if ! command -v uv &>/dev/null; then
    echo "uv 설치 중..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi

# 의존성 설치
echo "의존성 설치 중..."
uv pip install -e ".[dev]"

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
echo "다음 단계: .env 파일에 Telegram 봇 토큰을 입력하고 ./scripts/start_all.sh 실행"
