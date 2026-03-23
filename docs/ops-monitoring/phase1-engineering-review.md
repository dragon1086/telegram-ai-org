# Phase 1 산출물: Engineering 구현 검토 + 인프라 현황 + 모니터링 설계안

작성일: 2026-03-23
작성팀: 운영실 (aiorg_ops_bot)
기준 커밋: b251688 (2026-03-22)

---

## 1. Engineering 구현 결과 검토 보고서

### 1.1 구현 범위 (커밋 255dd02 + b251688)

| 항목 | 이전 | 이후 | 상태 |
|------|------|------|------|
| BOT_IDLE_TIMEOUT_SEC | 120s (하드코딩) | 300s (.env 적용) | ✅ |
| BOT_HB_INTERVAL_SEC | 60s (하드코딩) | 30s (.env 적용) | ✅ |
| BOT_MAX_TIMEOUT_SEC | 없음 | 1800s (절대 상한) | ✅ |
| heartbeat 로그 레벨 | DEBUG | INFO (프로덕션 가시성) | ✅ |
| 타임아웃 진단 메시지 | 단순 "무응답 Ns" | 3-tier 진단 포함 | ✅ |
| Telegram 진행 표시 | 고정 "🤔 처리 중..." | 실시간 경과시간 + hb횟수 | ✅ |
| 테스트 커버리지 | 10개 | 15개 (전체 PASS) | ✅ |

### 1.2 타임아웃 진단 3-tier 구조

```
hb_count == 0 AND 출력 없음  →  "작업 시작 전 stuck"
hb_count  > 0 AND 출력 없음  →  "LLM 응답 대기 중"
hb_count  > 0 AND 출력 있음  →  "작업 중 잘렸을 가능성"
```

타임아웃 메시지 예시:
```
⏰ 무응답 300초 (한도 300s) | 마지막 출력 40s 전: tests/ 디렉토리 스캔 중
    [heartbeat 8회 발화 — 작업 중 잘렸을 가능성]
```

### 1.3 실시간 진행 표시 (Telegram 메시지 업데이트)

heartbeat loop (30s마다) 발화 시 진행 메시지를 직접 업데이트:
```
⏳ 처리 중... (2.5분 경과, heartbeat #5)
    마지막 확인: core/telegram_relay.py 수정 중
```

### 1.4 검증 결과

```
tests/test_thinking_heartbeat.py  15/15 PASSED  (1.85s)
```

---

## 2. 운영 환경 인프라 현황 문서

### 2.1 봇 프로세스 상태

| 봇 | PID | 상태 |
|----|-----|------|
| aiorg_pm_bot | 84974 | UP |
| aiorg_engineering_bot | 84945 | UP |
| aiorg_design_bot | 84923 | UP |
| aiorg_growth_bot | 84951 | UP |
| aiorg_product_bot | 84992 | UP |
| aiorg_research_bot | 85000 | UP |
| aiorg_ops_bot | 84957 | UP |

### 2.2 환경 변수 (.env 현황)

```bash
BOT_IDLE_TIMEOUT_SEC=300      # 무응답 타임아웃 (120s → 300s 증가)
BOT_HB_INTERVAL_SEC=30        # heartbeat 발화 간격
# BOT_MAX_TIMEOUT_SEC 미설정 → 코드 기본값 1800s 적용
```

### 2.3 로그 수집 경로

| 구분 | 경로 | 레벨 | 내용 |
|------|------|------|------|
| 봇 운영 로그 | `~/.ai-org/{org_id}.log` | INFO+ | heartbeat, 타임아웃, 일반 실행 로그 |
| 세션 로그 | `logs/claude_sessions.log` | INFO | 세션 종료 이벤트 |
| 모니터 로그 | `~/.ai-org/agent-monitor.log` | INFO | stuck 감지, 자동 복구 이벤트 |
| 모니터 상태 | `/tmp/agent-monitor-state.json` | - | 세션별 해시/활동 시각 |

### 2.4 상주 데몬 현황

| 데몬 | PID | 상태 | 역할 |
|------|-----|------|------|
| agent_monitor.py | 85019 | **RUNNING** | 30s마다 tmux 세션 스캔, stuck 자동 복구 |
| bot_watchdog.py | - | 확인 필요 | 봇 프로세스 재기동 |

---

## 3. 모니터링 노출 방식 설계안

### 3.1 현재 운영 환경 특성

- **단일 머신 로컬 환경** (Mac mini, ~/.ai-org/ 파일 기반)
- 외부 HTTP 엔드포인트 없음 → 파일/로그 기반 모니터링이 현실적
- Telegram이 유일한 외부 접점 → Telegram 알림 채널 활용

### 3.2 채택 방식: 3-레이어 모니터링

```
Layer 1: 실시간 Telegram 진행 표시
  → 이미 구현 완료 (heartbeat loop에서 메시지 업데이트)

Layer 2: agent_monitor.py 파일 테일링
  → tmux 세션 스냅샷 비교 방식 (30s 간격)
  → stuck 시 자동 복구 + Telegram 알림

Layer 3: 로그 파일 집계 (~/.ai-org/{org_id}.log)
  → heartbeat #N INFO 로그 → 작업 진행 증거
  → 이상 시 수동 grep 또는 별도 tail 스크립트 활용
```

### 3.3 접근 권한 범위

| 레이어 | 접근 방식 | 인증 |
|--------|----------|------|
| Telegram 진행 메시지 | 그룹 채팅방 | Bot token (기존) |
| agent_monitor.py | 로컬 프로세스 | 로컬 사용자 권한 |
| ~/.ai-org/*.log | 로컬 파일 읽기 | 로컬 사용자 권한 |

→ 현재 환경에서 외부 방화벽/프록시 구성은 불필요.
→ Telegram을 통한 알림이 사실상 유일한 "외부" 접근 채널.
