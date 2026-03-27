#!/usr/bin/env bash
# =============================================================================
# scripts/create_release.sh — GitHub Release v1.0.0 생성 스크립트
#
# 사전 조건:
#   1. gh auth login 완료
#   2. 이 스크립트 실행: bash scripts/create_release.sh
#
# 동작:
#   - v1.0.0 태그 기반 GitHub Release 생성
#   - docs/RELEASE_NOTES_v1.0.0.md 릴리스 노트 사용
#   - dist/ 빌드 산출물 첨부 (whl + tar.gz)
# =============================================================================

set -euo pipefail

REPO="dragon1086/telegram-ai-org"
TAG="v1.0.0"
NOTES_FILE="docs/RELEASE_NOTES_v1.0.0.md"

# 1. gh auth 확인
echo "▶ GitHub CLI 인증 확인..."
if ! gh auth status &>/dev/null; then
  echo "❌ gh auth login이 필요합니다."
  echo "   실행: gh auth login"
  exit 1
fi
echo "  ✅ 인증 확인됨"

# 2. 릴리스 노트 파일 확인
echo "▶ 릴리스 노트 확인: $NOTES_FILE"
if [ ! -f "$NOTES_FILE" ]; then
  echo "❌ $NOTES_FILE 파일을 찾을 수 없습니다."
  exit 1
fi
echo "  ✅ 릴리스 노트 확인됨"

# 3. dist 산출물 확인
ASSETS=()
if ls dist/*.whl &>/dev/null; then
  for f in dist/*.whl; do ASSETS+=("$f"); done
fi
if ls dist/*.tar.gz &>/dev/null; then
  for f in dist/*.tar.gz; do ASSETS+=("$f"); done
fi

echo "▶ 첨부 산출물: ${#ASSETS[@]}개"
for a in "${ASSETS[@]}"; do echo "  - $a"; done

# 4. 기존 릴리스 확인 (중복 방지)
echo "▶ 기존 릴리스 확인..."
if gh release view "$TAG" --repo "$REPO" &>/dev/null; then
  echo "⚠️  $TAG 릴리스가 이미 존재합니다."
  echo "   기존 릴리스를 확인하려면: gh release view $TAG --repo $REPO"
  echo "   삭제 후 재생성: gh release delete $TAG --repo $REPO --yes"
  exit 0
fi

# 5. GitHub Release 생성
echo "▶ GitHub Release $TAG 생성 중..."

gh release create "$TAG" \
  "${ASSETS[@]}" \
  --repo "$REPO" \
  --title "telegram-ai-org $TAG" \
  --notes-file "$NOTES_FILE" \
  --verify-tag

echo ""
echo "✅ GitHub Release $TAG 생성 완료!"
echo "   https://github.com/$REPO/releases/tag/$TAG"
