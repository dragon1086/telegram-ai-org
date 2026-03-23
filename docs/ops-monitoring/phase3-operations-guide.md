# Phase 3 산출물: 외부 모니터링 운영 가이드

작성일: 2026-03-23
작성팀: 운영실 (aiorg_ops_bot)
배포 대상: PM, 개발팀 전체

---

## 1. 외부 모니터링 운영 가이드

### 1.1 에이전트 상태 해석 기준

Telegram 메시지에서 에이전트 상태를 읽는 방법:

#### A. 정상 동작 중 (작업 처리 중)

```
⏳ 처리 중... (2.5분 경과, heartbeat #5)
```

- heartbeat #N이 증가하고 있으면 → **정상 실행 중**
- 경과 시간이 늘어나도 heartbeat가 있으면 → 잘린 게 아님

#### B. 타임아웃 발생 시 — 3가지 케이스

**케이스 1: stuck (작업 시작도 못 함)**
```
⏰ 무응답 300초 (한도 300s) | 실행 중 출력 없음
    [heartbeat 0회 발화 — 작업 시작 전 stuck]
```
→ 원인: 태스크 큐 잠금, 툴 권한 오류, 환경 초기화 실패
→ 조치: 태스크 재시도 또는 봇 재기동 요청

**케이스 2: LLM 응답 대기 중 (API 지연)**
```
⏰ 무응답 300초 (한도 300s) | 실행 중 출력 없음
    [heartbeat 5회 발화 — LLM 응답 대기 중]
```
→ 원인: Claude API 응답 지연, 컨텍스트 과부하
→ 조치: 재시도 충분. BOT_IDLE_TIMEOUT_SEC 추가 증가 고려 (현재 300s)

**케이스 3: 작업 중 잘림 (실제 진행 중이었음)**
```
⏰ 무응답 300초 (한도 300s) | 마지막 출력 40s 전: tests/ 스캔 중
    [heartbeat 8회 발화 — 작업 중 잘렸을 가능성]
```
→ 원인: BOT_IDLE_TIMEOUT_SEC 부족, 복잡한 태스크
→ 조치: 태스크를 더 작게 분할하거나 BOT_IDLE_TIMEOUT_SEC 증가

### 1.2 모니터링 지표 조회 방법

#### Telegram (실시간, 권장)
- 채팅방에서 진행 메시지 확인 — 별도 설정 불필요

#### CLI (수동 점검)
```bash
# 전체 봇 상태
python scripts/health_check.py

# 특정 봇 로그 최근 50줄
tail -50 ~/.ai-org/aiorg_pm_bot.log

# heartbeat 발화 이력 확인
grep "heartbeat #" ~/.ai-org/aiorg_pm_bot.log

# stuck 감지 이력 확인
grep "stuck\|STUCK" ~/.ai-org/agent-monitor.log | tail -20

# agent_monitor 데몬 상태 확인
ps aux | grep agent_monitor | grep -v grep
```

---

## 2. 알림 임계값 및 채널 설정 명세서

### 2.1 알림 임계값 정의

| 상황 | 임계값 | 심각도 | 알림 채널 |
|------|--------|--------|----------|
| 타임아웃 발생 (케이스 1: stuck) | 즉시 | 🔴 Critical | Telegram 그룹 |
| 타임아웃 발생 (케이스 2: LLM 대기) | 즉시 | 🟡 Warning | Telegram 그룹 |
| 타임아웃 발생 (케이스 3: 작업 중 잘림) | 즉시 | 🟡 Warning | Telegram 그룹 |
| 봇 프로세스 다운 | 즉시 | 🔴 Critical | Telegram 그룹 (bot_watchdog) |
| 같은 봇 30분 내 타임아웃 3회 | 연속 3회 | 🔴 Critical | Telegram 그룹 |
| heartbeat 미발화 (태스크 10분+ 경과) | 10분 | 🟡 Warning | 로그 확인 |

### 2.2 현재 알림 채널 구성

| 채널 | 담당 컴포넌트 | 현황 |
|------|--------------|------|
| Telegram 그룹 채팅 | telegram_relay.py watchdog | ✅ 자동 발송 |
| Telegram 그룹 채팅 | agent_monitor.py | ✅ stuck 감지 시 발송 |
| 로그 파일 | logger.info() | ✅ ~/.ai-org/{org_id}.log |

### 2.3 타임아웃 재발 시 에스컬레이션

```
1회: Telegram 자동 알림 (현재 구현됨)
2회 (30분 내): PM이 수동 재시도
3회 (30분 내): BOT_IDLE_TIMEOUT_SEC 증가 검토 + 태스크 분할
```

---

## 3. 정기 점검 운영 절차서

### 3.1 일일 점검 (매일 오전)

```bash
# 1. 전체 봇 상태 확인
python scripts/health_check.py

# 2. 어제 타임아웃 발생 건수 확인
grep "무응답\|TIMEOUT\|TimeoutError" ~/.ai-org/*.log | grep "$(date -v-1d '+%Y-%m-%d')" | wc -l

# 3. stuck 감지 이력 확인
grep "stuck" ~/.ai-org/agent-monitor.log | grep "$(date -v-1d '+%Y-%m-%d')"
```

### 3.2 주간 점검 (매주 월요일)

- [ ] 지난 주 타임아웃 발생 패턴 분석 (봇별, 케이스별)
- [ ] heartbeat 발화 로그에서 평균 태스크 소요 시간 집계
- [ ] BOT_IDLE_TIMEOUT_SEC 적정성 재검토 (기준: 전체 태스크의 95%가 완료되는 시간 × 1.2)
- [ ] agent_monitor.py 데몬 실행 여부 확인 + 재기동 필요 여부 판단

### 3.3 타임아웃 임계값 조정 기준

```
현재: BOT_IDLE_TIMEOUT_SEC=300

조정 신호:
- 케이스 3 (작업 중 잘림)이 주 5회 이상 → 50s 증가 검토
- 케이스 2 (LLM 대기)가 주 5회 이상 → API 지연 원인 조사 먼저
- 케이스 1 (stuck)이 주 3회 이상 → 코드 버그 조사 우선

상한 권고: 600s (10분) — 그 이상은 태스크 분할이 더 효과적
```

### 3.4 운영 환경 변수 변경 절차

1. `.env` 파일 수정
2. `bash scripts/request_restart.sh --reason "타임아웃 설정 변경: {내용}"` 실행
3. watchdog이 재기동 처리 (현재 실행 중인 태스크 완료 후)
4. `python scripts/health_check.py`로 재기동 확인
5. 변경 내용을 이 문서 §1.2에 업데이트

---

## 4. 현재 운영 환경 요약 (한눈에 보기)

```
타임아웃 설정:   300s idle → 1800s 절대 상한
heartbeat 주기:  30s마다 발화 → Telegram 메시지 업데이트
진단 가시성:     타임아웃 메시지에 stuck/LLM대기/작업중잘림 자동 구분
로그 위치:       ~/.ai-org/{org_id}.log (INFO 레벨 이상)
stuck 감지 데몬: agent_monitor.py (PID 85019, 30s 간격)
봇 상태:         7/7 UP (health_check.py로 확인)
```
