#!/usr/bin/env bash
# SessionStart 세션 컨텍스트 로드 훅
# 세션 시작 시 유용한 프로젝트 상태 정보를 stdout으로 출력한다.

PROJECT_DIR="/Users/rocky/telegram-ai-org"

echo "=== 세션 컨텍스트 ==="

# 현재 날짜/시간
echo "현재 시각: $(date '+%Y-%m-%d %H:%M:%S')"

# 최근 3개 git 커밋
echo ""
echo "--- 최근 커밋 ---"
git -C "$PROJECT_DIR" log --oneline -3 2>/dev/null || echo "(git 정보 없음)"

# 실행 중인 봇 프로세스 수
BOT_COUNT=$(pgrep -f "bot_runner|bot_manager|bot_watchdog" 2>/dev/null | wc -l | tr -d ' ')
echo ""
echo "실행 중 봇 프로세스: ${BOT_COUNT}개"

# 미완료 TODO 수
TODO_COUNT=$(grep -r "TODO\|FIXME" "$PROJECT_DIR/core/" --include="*.py" -l 2>/dev/null | wc -l | tr -d ' ')
echo "TODO/FIXME 파일 수: ${TODO_COUNT}개"

# 마지막 pytest 결과
echo ""
echo "--- 최근 pytest 결과 ---"
tail -3 "$PROJECT_DIR/logs/pytest_last.log" 2>/dev/null || echo "(pytest 로그 없음)"

echo ""
echo "=== 컨텍스트 로드 완료 ==="

exit 0
