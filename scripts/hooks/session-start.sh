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


# 목표 진척률 체크 (pm_progress_guide.md)
PROGRESS_GUIDE="$HOME/.claude/projects/-Users-rocky-telegram-ai-org/memory/pm_progress_guide.md"
if [ -f "$PROGRESS_GUIDE" ]; then
    echo ""
    echo "--- 목표 진척률 ---"
    ACTIVE_GOALS=$(grep -c "현재상태: IN_PROGRESS\|현재상태: TODO" "$PROGRESS_GUIDE" 2>/dev/null || echo 0)
    DONE_TASKS=$(grep -c "상태: DONE" "$PROGRESS_GUIDE" 2>/dev/null || echo 0)
    TODO_TASKS=$(grep -c "상태: TODO" "$PROGRESS_GUIDE" 2>/dev/null || echo 0)
    echo "활성 목표: ${ACTIVE_GOALS}개 | 완료 서브태스크: ${DONE_TASKS}개 | 대기 TODO: ${TODO_TASKS}개"
    LAST_ITER=$(grep "날짜:" "$PROGRESS_GUIDE" | tail -1 | grep -oE "[0-9]{4}-[0-9]{2}-[0-9]{2}" 2>/dev/null || echo "")
    if [ -n "$LAST_ITER" ]; then
        echo "마지막 iter: ${LAST_ITER}"
    fi
    if [ "$TODO_TASKS" -gt 0 ]; then
        echo "⚠️  TODO 서브태스크 ${TODO_TASKS}개 — pm-progress-tracker 스킬로 자율 재개 권장"
    fi
fi

# COLLAB 활성도 (로그 기반)
COLLAB_COUNT=$(grep -r "COLLAB_PREFIX\|🙋 도와줄\|\[COLLAB:" "$HOME/.ai-org/runs/" 2>/dev/null | wc -l | tr -d ' ')
echo ""
echo "COLLAB 활성도: ${COLLAB_COUNT}회 $([ "${COLLAB_COUNT:-0}" -lt 4 ] && echo '⚠️ 낮음 — 이번 iter에서 [COLLAB:...] 태그 적극 활용' || echo '✅')"

echo ""
echo "=== 컨텍스트 로드 완료 ==="

exit 0
