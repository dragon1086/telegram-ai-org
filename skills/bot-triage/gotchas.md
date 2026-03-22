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

## Gotcha 4: infra 역할 조직이 아닌 부서가 Step 3c/3d(재시작/push) 직접 실행 — 스콥 오버

- **상황**: 개발실·리서치실 등 infra 역할이 없는 부서가 bot-triage를 사용하다 Step 3c(kill) 또는 Step 3d(restart/push)를 직접 실행
- **사고 사례**: T-238 이전 작업에서 개발실·리서치실이 재기동 및 git push를 직접 수행 → PM 지시 스콥 초과
- **원인**: `bot-triage`가 `common_skills`로 전 부서에 배포되어 있으나, Step 3c/3d 실행 권한 경계가 명시되지 않았음
- **규칙**: bot-triage Step 3c/3d는 **infra 역할 조직 전용** (`organizations.yaml`에서 `capabilities: [infra]`인 조직). 타 부서는 Step 1~3b까지만 진단 후 아래와 같이 위임:
  ```
  [COLLAB: 봇 재시작 필요 — 진단 완료, 글로벌 장애 확인 | 맥락: bot-triage Step 3d 진입 필요]
  ```
- **git push/머지도 동일**: 코드 수정은 개발실, 커밋은 개발실까지. push/merge/재기동은 infra 역할 조직 태스크로 분리.
