# Phase 1: Engineering 구현 결과 검토 보고서 + 운영 환경 인프라 현황

작성일: 2026-03-23
작성팀: 운영실 (aiorg_ops_bot)
관련 태스크: T-aiorg_pm_bot-311

---

## 1. 검토 요약

### 변경 전/후 비교

| 항목 | 변경 전 | 변경 후 |
|---|---|---|
| idle 타임아웃 | 120s (코드 기본값) / 실질 ~183s | 300s (.env BOT_IDLE_TIMEOUT_SEC=300) |
| heartbeat 간격 | 60s (하드코딩) | 30s (.env BOT_HB_INTERVAL_SEC=30) |
| 타임아웃 메시지 | `⏰ 무응답 183초 (한도 180s)` | 케이스별 진단 메시지 (3종) |
| 실시간 진행 표시 | 없음 | 30s마다 Telegram "⏳ 처리 중... (X.X분 경과, heartbeat #N)" |
| stuck vs 작업 중 구분 | 불가 | heartbeat 횟수 + 마지막 출력 라인으로 자동 판별 |
| agent_monitor STUCK_THRESHOLD | 180s | 300s (운영팀 수정 완료) |

---

## 2. Engineering 구현 상세

### 커밋 255dd02: heartbeat 개선 + active/stuck 판별 + idle timeout 300s

**파일**: `core/telegram_relay.py`

**핵심 변경 1 — progress_snapshot**
```python
_progress_snapshot: list[tuple[float, str]] = []  # [(timestamp, line), ...]
_SNAPSHOT_MAX = 5
```
실제 출력 라인 최대 5개를 타임스탬프와 함께 저장. 에이전트가 일하고 있으면 이 리스트가 채워진다.

**핵심 변경 2 — 타임아웃 메시지 진단**
```python
# 출력 있음 (일하다 잘림)
snap_hint = f" | 마지막 출력 {since_last:.0f}s 전: {last_line[:80]}"

# 출력 없음 (stuck 또는 LLM 대기)
diagnosis = "작업 시작 전 stuck" if _hb_count == 0 else "LLM 응답 대기 중"
snap_hint = f" | 실행 중 출력 없음 [{hb_hint} — {diagnosis}]"
```

**핵심 변경 3 — heartbeat 카운터 + env 설정**
```
BOT_IDLE_TIMEOUT_SEC=300   # .env
BOT_HB_INTERVAL_SEC=30     # .env
```
heartbeat 발화 횟수(_hb_count)를 누적 추적. 0회이면 시작도 못 한 stuck.

### 커밋 b251688: heartbeat 진단 강화 + Telegram 실시간 표시

**파일**: `core/telegram_relay.py`, `tests/test_thinking_heartbeat.py`

**핵심 변경 1 — Telegram 실시간 업데이트**
heartbeat loop에서 Telegram 진행 메시지를 직접 편집:
```python
hb_status = f"⏳ 처리 중... ({elapsed_min:.1f}분 경과, heartbeat #{_hb_count})"
if _progress_snapshot:
    _, last_snap_line = _progress_snapshot[-1]
    hb_status += f"\n마지막: {last_snap_line[:100]}"
await self.display.edit_progress(progress_msg, hb_status, ...)
```

**핵심 변경 2 — heartbeat 로그 debug→info**
프로덕션 로그(`logs/claude_sessions.log`)에서 heartbeat 가시성 확보:
```
[aiorg_pm_bot] heartbeat #3 (elapsed=90s, idle=30s)
```

**테스트**: `tests/test_thinking_heartbeat.py` 15개 전체 PASS

---

## 3. 타임아웃 진단 케이스 3가지

타임아웃 발생 시 Telegram에 다음 3가지 중 하나의 메시지가 표시된다.

| 케이스 | 메시지 패턴 | 의미 | PM 대응 |
|---|---|---|---|
| **작업 중 잘림** | `무응답 300초 \| 마지막 출력 40s 전: tests/ 디렉토리 스캔 중 [heartbeat 8회 — 작업 중 잘렸을 가능성]` | 에이전트가 열심히 일하다 타임아웃으로 잘린 것 | 태스크 재시도. 타임아웃이 반복되면 타임아웃 값 증가 검토 |
| **LLM 대기** | `무응답 300초 \| 실행 중 출력 없음 [heartbeat 5회 — LLM 응답 대기 중]` | Claude API 응답이 느린 것. 프로세스는 살아있음 | 잠시 후 재시도. Claude API 상태 확인 |
| **작업 시작 전 stuck** | `무응답 300초 \| 실행 중 출력 없음 [heartbeat 0회 — 작업 시작 전 stuck]` | 태스크가 시작조차 못 한 진짜 stuck | 태스크 재배정 또는 봇 상태 점검 |

---

## 4. 현재 운영 환경 인프라 현황

### 봇 프로세스 상태 (2026-03-23 기준)

```
aiorg_pm_bot          UP  PID 84974
aiorg_engineering_bot UP  PID 84945
aiorg_design_bot      UP  PID 84923
aiorg_growth_bot      UP  PID 84951
aiorg_product_bot     UP  PID 84992
aiorg_research_bot    UP  PID 85000
aiorg_ops_bot         UP  PID 84957
```

### 모니터링 데몬 상태

| 프로세스 | PID | 역할 |
|---|---|---|
| `scripts/agent_monitor.py` | 85019 | tmux 세션 30s 폴링 + stuck 감지 + 자동 응답 주입 |
| `scripts/bot_watchdog.py` | 85020 | 봇 프로세스 생존 감시 |

### 핵심 설정값 (.env)

```env
BOT_IDLE_TIMEOUT_SEC=300
BOT_HB_INTERVAL_SEC=30
```

### 로그 경로

| 로그 | 경로 | 내용 |
|---|---|---|
| 봇 실행 로그 | `logs/claude_sessions.log` | heartbeat, 에러, 타임아웃 메시지 |
| agent_monitor 로그 | `~/.ai-org/agent-monitor.log` | stuck 감지 이벤트, 주입 기록 |

---

## 5. 운영 적용 설계안

### 로그 수집 경로

```
[에이전트 실행] → core/telegram_relay.py (heartbeat + progress_snapshot)
     ↓
logs/claude_sessions.log  ← INFO 레벨 이상 (heartbeat 포함)
     ↓
~/.ai-org/agent-monitor.log ← agent_monitor.py 감시 이벤트
```

### 상태 노출 방식

1. **Telegram 실시간 (이미 구현됨)**: heartbeat마다 메시지 편집 → 가장 즉각적
2. **로컬 로그 tail**: `tail -f logs/claude_sessions.log | grep -E "heartbeat|timeout|stuck"`
3. **health_check.py**: `python scripts/health_check.py` → PID 생존 여부

### 접근 권한 범위

- Telegram 채팅: PM/사용자 직접 확인 (현재 구현됨)
- 로컬 로그: 서버 직접 접근 필요 (Mac Mini 로컬 환경)
- health_check: 로컬 실행 (원격 접근 불필요)

---

## 6. 갭 발견 및 조치 완료

| 항목 | 발견 | 조치 | 상태 |
|---|---|---|---|
| `agent_monitor.py` STUCK_THRESHOLD | 180s (구버전 기준) | 300s로 수정 (BOT_IDLE_TIMEOUT_SEC 정렬) | ✅ 완료 |
| `bot_watchdog.py` 실행 여부 | 확인 필요 | PID 85020 확인 → 정상 | ✅ 확인 |
| heartbeat 로그 가시성 | debug 레벨로 프로덕션 로그 미기록 | info 레벨로 변경 (커밋 b251688) | ✅ 완료 |
