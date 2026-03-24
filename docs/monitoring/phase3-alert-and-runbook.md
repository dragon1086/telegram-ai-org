# Phase 3: 모니터링 알림 임계값 + 정기 점검 운영 절차서

작성일: 2026-03-23
작성팀: 운영실 (aiorg_ops_bot)

---

## 1. 알림 임계값 정의

| Alert 이름 | 조건 | 심각도 | 알림 채널 | 대응 행동 |
|---|---|---|---|---|
| **AgentTimeout_Working** | 타임아웃 + `heartbeat N회 — 작업 중 잘렸을 가능성` | Warning | Telegram (현재 구현됨) | 재시도. 반복 시 타임아웃 증가 검토 |
| **AgentTimeout_Stuck** | 타임아웃 + `heartbeat 0회 — 작업 시작 전 stuck` | Critical | Telegram 즉시 알림 | 봇 상태 점검 → health_check.py 실행 |
| **AgentTimeout_LLMWait** | 타임아웃 + `heartbeat N회 — LLM 응답 대기 중` | Warning | Telegram | 5~10분 대기 후 재시도 |
| **BotProcessDown** | health_check.py 결과에 DOWN 봇 존재 | Critical | 수동 감지 (자동화 미적용) | 즉시 `bash scripts/request_restart.sh --reason "봇 다운"` |
| **MonitorDaemonDown** | `ps aux | grep agent_monitor` 결과 없음 | Warning | 수동 감지 | `python scripts/agent_monitor.py --daemon` 재시작 |
| **HeartbeatGap** | Telegram 진행 메시지 60초 이상 업데이트 없음 + 작업 중 상태 | Warning | Telegram 관찰 | 로그 확인: `tail -f logs/claude_sessions.log` |

### 알림 운영 원칙

- **Warning**: 운영 채널 통보, 즉각 대응 불필요, 다음 작업 사이클에 점검
- **Critical**: 즉시 대응, health_check.py 실행 후 결과에 따라 재기동 요청
- 동일 봇에서 같은 Alert가 3회 이상 반복 시: 태스크 복잡도 재검토 또는 타임아웃 값 조정

---

## 2. 현재 알림 채널 현황

| 알림 방식 | 구현 상태 | 담당 컴포넌트 |
|---|---|---|
| Telegram 타임아웃 진단 메시지 | ✅ 구현됨 | `core/telegram_relay.py` |
| Telegram 실시간 heartbeat 진행 표시 | ✅ 구현됨 | `core/telegram_relay.py` |
| agent_monitor.py → Telegram stuck 알림 | ✅ 구현됨 | `scripts/agent_monitor.py` |
| health_check.py 자동 크론 | ❌ 미적용 (수동만) | 추후 크론 등록 권장 |
| bot_watchdog.py 프로세스 감시 | ✅ 구현됨 (PID 85020) | `scripts/bot_watchdog.py` |
| 외부 알림 (Slack, 이메일) | ❌ 미적용 | 추후 필요 시 추가 |

### 추천 개선 사항 (우선순위순)

1. **health_check.py 크론 자동화**: 5분마다 실행 + DOWN 감지 시 request_restart.sh 자동 호출
2. **agent_monitor.py STUCK Alert 자동 에스컬레이션**: 동일 봇 3회 이상 stuck 감지 시 별도 Telegram 메시지
3. **로그 집계 대시보드**: `logs/claude_sessions.log`에서 타임아웃 케이스별 통계 weekly 집계

---

## 3. 정기 점검 운영 절차서

### 매일 (09:00)

```bash
# 1. 봇 전체 상태 확인
cd /Users/rocky/telegram-ai-org
python scripts/health_check.py

# 2. 오늘 타임아웃 발생 확인
grep "무응답\|timeout" logs/claude_sessions.log | grep $(date +%Y-%m-%d) | wc -l

# 3. agent_monitor 데몬 확인
ps aux | grep agent_monitor | grep -v grep
```

**기대 결과**:
- 모든 봇 UP
- 타임아웃 발생 0~2건 (정상 범위)
- agent_monitor 실행 중

### 매주 월요일 (09:30)

```bash
# 지난주 타임아웃 케이스별 집계
grep "heartbeat.*작업 중 잘렸을" logs/claude_sessions.log | wc -l
grep "heartbeat.*LLM 응답 대기" logs/claude_sessions.log | wc -l
grep "heartbeat 0회.*작업 시작 전 stuck" logs/claude_sessions.log | wc -l

# agent_monitor stuck 감지 이벤트 집계
grep "STUCK\|stuck" ~/.ai-org/agent-monitor.log | tail -50
```

**판단 기준**:
- `작업 중 잘림` 주 10건 이상 → 타임아웃 증가 검토
- `작업 시작 전 stuck` 주 3건 이상 → 봇 안정성 점검 필요

### 월 1회 (매월 첫째 주 화요일)

1. `BOT_IDLE_TIMEOUT_SEC` 적정성 검토 (현재 300s)
   - 작업 완료 평균 시간 대비 여유 있는가?
   - 불필요하게 긴 대기가 발생하지 않는가?

2. `BOT_HB_INTERVAL_SEC` 적정성 검토 (현재 30s)
   - Telegram 메시지 너무 잦으면 60s로 조정 가능

3. `agent_monitor.py` STUCK_THRESHOLD 검토 (현재 300s)
   - BOT_IDLE_TIMEOUT_SEC와 항상 일치해야 함

4. 테스트 스위트 재실행:
   ```bash
   python -m pytest tests/test_thinking_heartbeat.py -v
   ```

---

## 4. 롤백 & 에스컬레이션 매트릭스

| 상황 | 1차 대응 | 2차 대응 | 에스컬레이션 |
|---|---|---|---|
| 봇 1개 DOWN | `request_restart.sh` 실행 | 5분 후 재확인 | 운영팀 → 개발팀 |
| 봇 3개 이상 DOWN | 전체 재기동 요청 | 로그 분석 | 즉시 개발팀 에스컬레이션 |
| 타임아웃 연속 5회 이상 (동일 봇) | 태스크 중단 + 봇 상태 점검 | `BOT_IDLE_TIMEOUT_SEC` 증가 | 운영팀 검토 |
| agent_monitor 다운 | 수동 재시작 | PID 파일 확인 | 자동화 크론 검토 |
| heartbeat 완전 멈춤 (전체 봇) | Claude API 상태 확인 | 봇 전체 재기동 요청 | 개발팀 에스컬레이션 |

### 재기동 시 절대 규칙

```bash
# ✅ 올바른 방법
bash scripts/request_restart.sh --reason "이유 설명"

# ❌ 절대 금지
bash scripts/restart_bots.sh
bash scripts/bot_control.sh restart
kill $(pgrep -f main.py)
```

---

## 5. 설정 변경 이력

| 일시 | 변경 항목 | 변경 전 | 변경 후 | 변경자 |
|---|---|---|---|---|
| 2026-03-22 | BOT_IDLE_TIMEOUT_SEC (.env) | ~120s | 300s | Engineering (255dd02) |
| 2026-03-22 | BOT_HB_INTERVAL_SEC (.env) | 없음(60s 하드코딩) | 30s | Engineering (255dd02) |
| 2026-03-23 | agent_monitor.py STUCK_THRESHOLD | 180s | 300s | 운영실 |
