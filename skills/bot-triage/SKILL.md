---
name: bot-triage
description: "Use when a bot is unresponsive, crashed, or behaving abnormally. Runs diagnostic checks (process, logs, API), attempts auto-recovery, and generates an incident report. Triggers: '봇 장애', 'bot down', 'bot triage', '응답 없음', 'bot crash', 'triage', when any bot stops responding"
---

# Bot Triage (봇 장애 진단 런북)

봇 장애 발생 시 체계적 진단 → 복구 → 보고를 자율 수행하는 런북 스킬.

## Step 1: 초기 진단 (자동)

```bash
bash skills/bot-triage/scripts/diagnose.sh
```

diagnose.sh가 수행하는 검사:
1. **프로세스 생존** — `ps aux | grep bot_runner` 로 각 봇 PID 확인
2. **최근 로그** — `tail -50 ~/.ai-org/bot-*.log` 로 에러 패턴 탐지
3. **watchdog 상태** — `/tmp/bot-watchdog.pid` 존재 여부 + 프로세스 생존
4. **디스크/메모리** — `df -h /` + `free -m` 로 리소스 고갈 여부

## Step 2: 근본 원인 분류

diagnose.sh 출력을 기반으로 원인을 분류한다:

| 증상 | 가능한 원인 | 다음 단계 |
|------|------------|----------|
| PID 없음, 로그에 에러 없음 | watchdog 미실행 또는 재시작 한도 초과 | Step 3a |
| PID 없음, NameError/ImportError | 코드 버그 (import 누락 등) | Step 3b |
| PID 있음, 응답 없음 | 이벤트 루프 블로킹 또는 DB 락 | Step 3c |
| 모든 봇 다운 | 글로벌 장애 (환경변수, DB, 네트워크) | Step 3d |

## Step 3a: Watchdog 복구

```bash
# watchdog 재시작
python scripts/bot_watchdog.py --once  # 1회 점검 + 재시작
python scripts/bot_watchdog.py &       # 데몬 모드
```

## Step 3b: 코드 버그 수정

1. 로그에서 traceback 추출
2. 해당 파일의 에러 라인 확인
3. 수정 후 quality-gate 실행
4. error-gotcha 스킬로 gotcha 기록

## Step 3c: 이벤트 루프 블로킹

```bash
# 해당 봇 프로세스 강제 종료 후 재시작
kill -9 <PID>
python scripts/bot_manager.py start <org_id>
```

## Step 3d: 글로벌 장애

1. `.env` 파일 검증 — 필수 토큰/키 존재 확인
2. DB 연결 테스트 — `python -c "import aiosqlite"`
3. 네트워크 확인 — `curl -s https://api.telegram.org`
4. 전체 재시작 — `bash scripts/restart_bots.sh`

## Step 4: 인시던트 보고서 작성

```bash
# 보고서 저장 경로
docs/incidents/YYYY-MM-DD-<요약>.md
```

`skills/bot-triage/templates/incident-report.md` 템플릿 사용.

## Step 5: Rocky에게 보고

Telegram으로 요약 보고:
```
[봇 장애 복구 완료]
- 원인: {근본 원인}
- 영향: {영향 범위}
- 조치: {수행한 조치}
- 보고서: docs/incidents/{파일명}
```

## Step 6: 재발 방지

- 해당 원인에 대한 gotcha를 이 스킬의 gotchas.md에 추가
- 반복 패턴이면 watchdog 로직 강화 검토
