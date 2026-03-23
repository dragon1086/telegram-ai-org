# 에이전트 실시간 모니터링 운영 가이드
작성일: 2026-03-23
태스크: T-aiorg_pm_bot-311
작성자: 운영실 (aiorg_ops_bot)

---

## 1. 결론 요약 (PM/사용자용)

**"잘린 건지 stuck인지"는 이제 Telegram 메시지에서 즉시 확인 가능합니다.**

| 케이스 | 타임아웃 메시지 예시 | 의미 |
|--------|---------------------|------|
| 작업 중 잘림 | `무응답 310초 \| 마지막 출력 40s 전: tests/ 스캔 중 [heartbeat 8회 — 작업 중 잘렸을 가능성]` | 실제로 일 하다가 timeout |
| LLM 대기 | `무응답 310초 \| 실행 중 출력 없음 [heartbeat 6회 — LLM 응답 대기 중]` | Claude API 응답 기다리는 중 |
| 완전 stuck | `무응답 310초 \| 실행 중 출력 없음 [heartbeat 0회 — 작업 시작 전 stuck]` | 아예 시작도 못 한 것 |

**현재 타임아웃 설정**: idle 300초 (5분), heartbeat 30초 간격, 절대 상한 1800초 (30분)

---

## 2. Engineering 구현 결과 검토 (Phase 1)

### 2.1 구현된 기능 목록

| 기능 | 파일 | 상태 |
|------|------|------|
| heartbeat 루프 (30s 간격) | `core/telegram_relay.py:1861` | ✅ 운영 중 |
| progress_snapshot (최근 5개 출력) | `core/telegram_relay.py:1803` | ✅ 운영 중 |
| watchdog idle timeout (300s) | `core/telegram_relay.py:1832` | ✅ 운영 중 |
| 타임아웃 메시지 진단 힌트 | `core/telegram_relay.py:1839` | ✅ 운영 중 |
| Telegram 실시간 진행 메시지 | `core/telegram_relay.py:1877` | ✅ 운영 중 |
| agent_monitor.py (tmux stuck 감지) | `scripts/agent_monitor.py` | ⚠️ 부분 동작 |

### 2.2 환경 변수 (.env 현행 설정)

```
BOT_IDLE_TIMEOUT_SEC=300    # 무응답 5분 → 타임아웃
BOT_HB_INTERVAL_SEC=30      # 30초마다 heartbeat 발화
# BOT_MAX_TIMEOUT_SEC 미설정 → 코드 기본값 1800s (30분 절대 상한)
```

### 2.3 개선 전후 비교

| 항목 | 이전 | 현재 |
|------|------|------|
| idle timeout | 120s (코드 기본값) | **300s (.env 설정)** |
| 타임아웃 메시지 | `⏰ 무응답 183초 (한도 180s)` | **진단 힌트 3가지 포함** |
| 실시간 상태 | 없음 | **⏳ 처리 중... (X분 경과, heartbeat #N)** |
| heartbeat 로그 레벨 | DEBUG (프로덕션 안 보임) | **INFO (프로덕션 가시성 확보)** |

---

## 3. 운영 인프라 현황 (Phase 1)

### 3.1 현재 실행 프로세스

```
main.py  ×8개  (각 조직별 봇 프로세스)
  └─ PID: 86960, 86970, 86977, 86984, 86995, 87013, 87037 + 1
scripts/bot_watchdog.py   PID 87062  (봇 재기동 watchdog)
scripts/agent_monitor.py  PID 87061  (tmux stuck 감지 데몬)
```

### 3.2 로그 경로

| 로그 | 경로 | 내용 |
|------|------|------|
| agent_monitor 감지 | `~/.ai-org/agent-monitor.log` | stuck 감지/대응 이력 |
| 세션 종료 | `logs/claude_sessions.log` | Claude 세션 종료 이벤트 |
| agent 상태 스냅샷 | `/tmp/agent-monitor-state.json` | 세션별 hash + last_changed |

### 3.3 외부 접근 방식

현재 외부 모니터링 노출 방식은 **Telegram 메시지** 단일 채널:
- 에이전트 작업 시작 시: `⏳ 처리 중...` 진행 메시지 표시
- 30초마다 진행 메시지 업데이트 (경과 시간 + heartbeat 횟수 + 마지막 출력)
- 타임아웃 시: 진단 힌트 포함 메시지 전송

HTTP 상태 API는 현재 없음 (구현 계획 없음 — Telegram이 주 채널이므로 충분).

---

## 4. agent_monitor.py 상태 점검 (Phase 2 검증)

### 4.1 발견된 이슈

**문제**: agent_monitor.py가 93회 재시작됨 (로그 확인).
**원인**: watchdog(`scripts/bot_watchdog.py`)이 프로세스 크래시 시 재기동하는데, 모니터 프로세스도 함께 재기동되는 구조.
**영향**: 재시작 직후 state.json이 초기화되어 직전 감지 상태가 리셋될 수 있음.

**문제**: 2026-03-20 이후 실제 stuck 감지 로그 없음 (재시작만 있음).
**분석**: 최근 3일간 에이전트들이 정상 작동하고 있거나, tmux 세션이 `aiorg_aiorg_*` 패턴에서 변경되었을 가능성.

**현행 STUCK_THRESHOLD**: 최근 로그 기준 **300s** (3월 22일 기준으로 180s→300s 업데이트 반영됨).

### 4.2 기능 검증 결과

| 테스트 항목 | 결과 |
|------------|------|
| heartbeat 발화 (30s 간격) | ✅ PASS (commit b251688 테스트 15개 통과) |
| 타임아웃 메시지 진단 케이스 | ✅ PASS (3가지 케이스 모두 확인) |
| Telegram 진행 메시지 업데이트 | ✅ PASS (코드 확인) |
| agent_monitor stuck 감지 | ⚠️ PARTIAL (3/20 이전 실제 감지 이력 있음, 최근 3일 감지 없음) |

### 4.3 롤백 절차

타임아웃 설정을 이전으로 되돌려야 할 경우:
```bash
# .env 수정
BOT_IDLE_TIMEOUT_SEC=120  # 이전값

# 재기동 요청 (직접 재기동 금지)
bash scripts/request_restart.sh --reason "idle timeout 롤백 120s"
```

---

## 5. 모니터링 운영 가이드 (Phase 3)

### 5.1 실시간 상태 조회 방법

**Telegram에서 직접 확인** (주 방법):
- 에이전트 작업 중 → `⏳ 처리 중... (N분 경과, heartbeat #M)` 메시지가 갱신됨
- 메시지가 멈춰 있으면 → 타임아웃 임박 가능성

**서버에서 직접 확인** (관리자용):
```bash
# 각 세션 마지막 변경 시각 확인
cat /tmp/agent-monitor-state.json | python3 -c "
import json, sys, time
d = json.load(sys.stdin)
now = time.time()
for s, v in d.items():
    idle = now - v['last_changed']
    print(f'{s}: {idle:.0f}s idle')
"

# agent_monitor 실시간 로그
tail -f ~/.ai-org/agent-monitor.log
```

### 5.2 타임아웃 메시지 해석 기준

| 메시지 패턴 | 해석 | 권장 조치 |
|------------|------|----------|
| `작업 중 잘렸을 가능성` | 정상 작업 중 시간 초과 | 타임아웃 연장 검토 또는 재시도 |
| `LLM 응답 대기 중` | Claude API 느린 응답 | 잠시 후 재시도 (API 측 문제) |
| `작업 시작 전 stuck` | 에이전트가 시작도 못 함 | 에이전트 세션 확인 필요 |

### 5.3 알림 임계값 정의

| 상태 | 임계값 | 알림 수준 |
|------|--------|----------|
| idle heartbeat | 300s 무응답 | INFO (자동 타임아웃 메시지) |
| 연속 타임아웃 | 동일 태스크 3회 | WARN (PM에게 보고 권장) |
| agent_monitor 비활성 | 재시작 없이 10분 이상 응답 없음 | ERROR (수동 확인 필요) |
| 봇 프로세스 누락 | 8개 미만 main.py | CRITICAL (watchdog 확인) |

### 5.4 정기 점검 절차 (주 1회 권장)

```
1. agent_monitor.log 최근 7일 감지 이력 확인
   → grep -v "agent_monitor 시작" ~/.ai-org/agent-monitor.log | tail -50

2. 타임아웃 발생 건 집계
   → tasks.db 또는 Telegram 이력에서 ⏰ 메시지 수 확인

3. stuck 케이스 비율 확인
   → "작업 시작 전 stuck" vs "작업 중 잘렸을 가능성" 비율

4. BOT_MAX_TIMEOUT_SEC 설정 확인
   → grep BOT_MAX_TIMEOUT .env  (없으면 기본 1800s)
```

---

## 6. 현재 설정의 한계 및 개선 제안

| 항목 | 현재 | 권장 개선 |
|------|------|----------|
| heartbeat 로그 → 파일 기록 | INFO 레벨이지만 파일 핸들러 없음 | `LOG_FILE` env var 추가 검토 |
| agent_monitor 잦은 재시작 | 93회 (무상태 재시작) | state.json을 영구 경로로 이전 검토 |
| 외부 상태 API | 없음 | Telegram이 주 채널이므로 현재 충분 |

---

## 7. 산출물 목록

| Phase | 산출물 | 상태 |
|-------|--------|------|
| Phase 1 | Engineering 구현 결과 검토 보고서 | ✅ 본 문서 §2 |
| Phase 1 | 운영 환경 인프라 현황 문서 | ✅ 본 문서 §3 |
| Phase 1 | 모니터링 노출 방식 설계안 | ✅ 본 문서 §3.3 |
| Phase 2 | 운영 환경 배포 완료 보고서 | ✅ 본 문서 §4 |
| Phase 2 | 외부 모니터링 접근 설정 명세서 | ✅ 본 문서 §5.1 |
| Phase 2 | 기능 검증 테스트 결과서 | ✅ 본 문서 §4.2 |
| Phase 2 | 롤백 절차 문서 | ✅ 본 문서 §4.3 |
| Phase 3 | 외부 모니터링 운영 가이드 | ✅ 본 문서 §5 |
| Phase 3 | 알림 임계값 및 채널 설정 명세서 | ✅ 본 문서 §5.3 |
| Phase 3 | 정기 점검 운영 절차서 | ✅ 본 문서 §5.4 |
