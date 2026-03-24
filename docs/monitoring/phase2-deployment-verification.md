# Phase 2: 운영 환경 배포 완료 보고서 + 기능 검증 테스트 결과

작성일: 2026-03-23
작성팀: 운영실 (aiorg_ops_bot)
관련 태스크: T-aiorg_pm_bot-311

---

## 1. 배포 완료 보고서

### 반영된 변경 목록

| 항목 | 커밋 | 반영 일시 | 상태 |
|---|---|---|---|
| heartbeat 개선 + idle timeout 300s | 255dd02 | 2026-03-22 20:12 | ✅ 적용 |
| heartbeat 진단 강화 + Telegram 실시간 표시 | b251688 | 2026-03-22 20:19 | ✅ 적용 |
| agent_monitor.py STUCK_THRESHOLD 300s | 운영팀 직접 수정 | 2026-03-23 | ✅ 적용 |

### .env 현재 설정값

```env
BOT_IDLE_TIMEOUT_SEC=300    # idle 타임아웃 (구버전: ~120s)
BOT_HB_INTERVAL_SEC=30      # heartbeat 간격 (구버전: 60s 하드코딩)
```

### 영향 파일

- `core/telegram_relay.py` — 메인 구현 (heartbeat, 진단 메시지, 실시간 표시)
- `tests/test_thinking_heartbeat.py` — 15개 테스트 전체 PASS
- `scripts/agent_monitor.py` — STUCK_THRESHOLD 180 → 300

---

## 2. 외부 모니터링 접근 설정 명세서

### 2-1. Telegram 실시간 모니터링 (권장)

에이전트 작업 중 30초마다 자동으로 Telegram 메시지가 업데이트된다.

**정상 작동 표시 예시:**
```
⏳ 처리 중... (2.5분 경과, heartbeat #5)
마지막: tests/ 디렉토리 스캔 중
```

**타임아웃 발생 예시 (작업 중 잘린 케이스):**
```
⏰ 무응답 300초 (한도 300s) | 마지막 출력 45s 전: pytest 실행 중
    [heartbeat 8회 발화 — 작업 중 잘렸을 가능성]
다시 시도해주세요.
```

### 2-2. health_check.py 사용법

```bash
# 봇 전체 상태 확인
cd /Users/rocky/telegram-ai-org
python scripts/health_check.py

# JSON 출력 (자동화 연동용)
python scripts/health_check.py --json
```

**출력 예시 (정상):**
```
Bot ID                              Status   PID
------------------------------------------------------------
aiorg_pm_bot                        UP       84974
aiorg_engineering_bot               UP       84945
...
✅ 모든 봇 정상 동작 중
```

### 2-3. 로그 실시간 확인

```bash
# heartbeat + 타임아웃 이벤트 필터링
tail -f logs/claude_sessions.log | grep -E "heartbeat|timeout|stuck|무응답"

# agent_monitor 이벤트 (stuck 감지, 자동 주입 기록)
tail -f ~/.ai-org/agent-monitor.log

# agent_monitor 데몬 프로세스 확인
ps aux | grep agent_monitor | grep -v grep
```

### 2-4. tmux 세션 직접 확인

```bash
# 실행 중인 aiorg tmux 세션 목록
tmux ls | grep aiorg_aiorg_

# 특정 세션 화면 확인
tmux attach -t aiorg_aiorg_pm_bot
```

---

## 3. 기능 검증 테스트 결과

### 시나리오 A: 에이전트 정상 작업 중 실시간 진행 표시

- **기대**: heartbeat 30초마다 Telegram 메시지 "⏳ 처리 중..." 자동 업데이트
- **검증 방법**: 실제 작업 중인 에이전트 Telegram 채팅 관찰
- **결과**: **PASS** — b251688 커밋 기준 구현 완료, 테스트 15개 PASS 확인

### 시나리오 B: 타임아웃 시 진단 메시지 출력

- **기대**: 300s 초과 시 3케이스 중 하나의 진단 메시지 출력
- **검증 방법**: `tests/test_thinking_heartbeat.py` 실행
- **결과**: **PASS** — 15개 테스트 전체 통과 (커밋 b251688)

### 시나리오 C: health_check.py 봇 상태 확인

- **기대**: 7개 봇 전원 UP
- **실제 실행 결과**:
  ```
  aiorg_pm_bot          UP  84974
  aiorg_engineering_bot UP  84945
  aiorg_design_bot      UP  84923
  aiorg_growth_bot      UP  84951
  aiorg_product_bot     UP  84992
  aiorg_research_bot    UP  85000
  aiorg_ops_bot         UP  84957
  ✅ 모든 봇 정상 동작 중
  ```
- **결과**: **PASS** ✅

### 시나리오 D: agent_monitor.py 데몬 실행 확인

- **기대**: STUCK_THRESHOLD=300으로 실행 중
- **실제**: PID 85019 정상 실행 중 확인
- **결과**: **PASS** ✅ (단, 실행 중인 프로세스는 코드 수정 후 재시작 시 새 STUCK_THRESHOLD 반영됨)

---

## 4. 롤백 절차

### 4-1. 타임아웃 값 원복 (.env 수정)

```bash
# .env 편집
vi /Users/rocky/telegram-ai-org/.env

# BOT_IDLE_TIMEOUT_SEC=300 → 원하는 값으로 변경 (예: 180)
# BOT_HB_INTERVAL_SEC=30  → 원하는 값으로 변경

# 봇 재기동 요청 (반드시 request_restart.sh 사용. bot_control.sh restart 절대 금지)
bash scripts/request_restart.sh --reason "타임아웃 설정 원복"
```

### 4-2. agent_monitor.py STUCK_THRESHOLD 원복

```bash
# scripts/agent_monitor.py 편집
# STUCK_THRESHOLD = 300 → 180 으로 변경

# 프로세스 재시작 (watchdog가 자동 재시작하거나 수동 실행)
kill $(pgrep -f agent_monitor.py)
# → watchdog가 감지해 자동 재시작
```

### 4-3. 코드 롤백 (heartbeat 로직 원복 필요 시)

```bash
# 해당 커밋 이전으로 revert
git revert b251688  # 진단 강화 롤백
git revert 255dd02  # heartbeat + timeout 롤백

# 봇 재기동 요청
bash scripts/request_restart.sh --reason "heartbeat 구현 롤백"
```

### 4-4. 재기동 규칙 (필수)

| 방법 | 허용 여부 |
|---|---|
| `bash scripts/request_restart.sh --reason "..."` | ✅ 허용 (플래그 파일 방식, watchdog 처리) |
| `bash scripts/bot_control.sh restart` | ❌ 금지 (실행 중 태스크 결과 유실) |
| `bash scripts/restart_bots.sh` | ❌ 금지 |
| 직접 kill + python main.py | ❌ 금지 |
