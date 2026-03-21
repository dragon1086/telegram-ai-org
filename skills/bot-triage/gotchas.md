# Bot Triage — Gotchas

## Gotcha 1: watchdog PID 파일이 있지만 프로세스가 죽은 경우 (stale PID)

- **상황**: `/tmp/bot-watchdog.pid`에 PID가 기록되어 있으나 해당 프로세스가 이미 종료됨
- **증상**: watchdog가 실행 중으로 보이지만 봇 재시작이 안 됨
- **해결**: PID 파일의 프로세스가 실제 살아있는지 `kill -0 $PID`로 확인. stale이면 PID 파일 삭제 후 watchdog 재시작

## Gotcha 2: MAX_RESTART_PER_BOT 초과 후 자동 복구 불가

- **상황**: 봇이 5회 연속 재시작 실패하면 watchdog가 해당 봇 재시작을 중단함
- **증상**: watchdog는 실행 중이지만 특정 봇만 계속 죽어있음
- **해결**: 근본 원인(코드 버그, 환경변수 등) 수정 후 watchdog 재시작으로 카운터 리셋. 10분(RESTART_COUNT_RESET_AFTER) 대기해도 리셋됨

## Gotcha 3: 봇 프로세스 PID는 있지만 실제로 응답 안 하는 경우

- **상황**: `ps`에는 봇 프로세스가 보이지만 Telegram 메시지에 반응 없음
- **증상**: 이벤트 루프 블로킹, DB 락, 또는 네트워크 타임아웃
- **해결**: `kill -9`로 강제 종료 후 재시작. 로그에서 마지막 처리 중인 작업 확인
