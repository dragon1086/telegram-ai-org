# Phase 2 산출물: 운영 환경 배포 완료 보고서 + 검증 결과

작성일: 2026-03-23
작성팀: 운영실 (aiorg_ops_bot)

---

## 1. 운영 환경 배포 완료 보고서

### 1.1 배포 상태

| 항목 | 상태 | 근거 |
|------|------|------|
| 코드 배포 | ✅ 완료 | 커밋 b251688 메인 브랜치 반영 |
| .env 설정 적용 | ✅ 완료 | BOT_IDLE_TIMEOUT_SEC=300, BOT_HB_INTERVAL_SEC=30 |
| 봇 프로세스 실행 | ✅ 7/7 UP | health_check.py --json 확인 |
| agent_monitor 데몬 | ✅ RUNNING | PID 85019 (재기동 후 신규 PID 갱신) |
| 신규 코드 로드 여부 | ✅ 확인 | 재기동 후 최신 커밋 기준 실행 중 |

### 1.2 배포된 환경 변수 구성

```bash
# 현행 운영 환경 타임아웃 설정
BOT_IDLE_TIMEOUT_SEC=300      # 무응답 타임아웃: 120s → 300s (+150%)
BOT_HB_INTERVAL_SEC=30        # heartbeat 주기: 60s(구) → 30s(-50%)
BOT_MAX_TIMEOUT_SEC=(미설정)  # 절대 상한: 코드 기본값 1800s 적용

# 외부 방화벽/프록시: 로컬 환경 — 설정 불필요
# 인증: Telegram Bot Token (기존 채널 재사용)
```

### 1.3 롤백 절차

이슈 발생 시 즉시 적용 절차:

```bash
# Step 1: 이전 타임아웃으로 복구 (재기동 없이 즉시)
# .env에서 아래 값으로 변경:
BOT_IDLE_TIMEOUT_SEC=120
BOT_HB_INTERVAL_SEC=60

# Step 2: 재기동 요청 (봇 직접 종료 금지)
bash scripts/request_restart.sh --reason "타임아웃 설정 롤백"

# Step 3: 복구 확인
python scripts/health_check.py
```

코드 롤백이 필요한 경우:
```bash
git revert b251688    # heartbeat 진단 강화 롤백
git revert 255dd02    # heartbeat 개선 + 300s 롤백
bash scripts/request_restart.sh --reason "heartbeat 코드 롤백"
```

---

## 2. 외부 모니터링 접근 설정 명세서

### 2.1 모니터링 접근 경로

현 환경(로컬 Mac mini 단일 머신)에서 유효한 외부 접근 방식:

| 접근 채널 | 방식 | 실시간성 | 설정 필요 |
|-----------|------|----------|----------|
| Telegram 그룹 채팅 | Bot API push | ✅ 즉시 | 없음 (기존 채널) |
| ~/.ai-org/*.log | 파일 읽기 | 수동 | 없음 |
| /tmp/agent-monitor-state.json | 파일 읽기 | 30s 단위 | 없음 |
| python scripts/health_check.py | CLI 실행 | 즉시 | 없음 |

### 2.2 Telegram 통해 볼 수 있는 실시간 상태

heartbeat 발화 시 진행 메시지 자동 업데이트:
```
⏳ 처리 중... (2.5분 경과, heartbeat #5)
```

타임아웃 발생 시 진단 메시지:
```
⏰ 무응답 300초 (한도 300s) | 마지막 출력 40s 전: tests/ 스캔 중
    [heartbeat 8회 발화 — 작업 중 잘렸을 가능성]
```

---

## 3. 기능 검증 테스트 결과서

### 3.1 테스트 실행 결과

```
실행 명령: .venv/bin/python -m pytest tests/test_thinking_heartbeat.py -v
실행 시각: 2026-03-23
```

| 테스트 케이스 | 결과 |
|--------------|------|
| test_hb_count_zero_no_output (stuck) | PASSED |
| test_hb_count_positive_no_output (LLM 대기) | PASSED |
| test_hb_count_positive_with_output (작업 중 잘림) | PASSED |
| test_watchdog_timeout_message_format | PASSED |
| test_progress_snapshot_tracking | PASSED |
| + 10개 기존 테스트 | PASSED |
| **합계** | **15/15 PASSED** |

### 3.2 운영 환경 동작 검증

| 검증 항목 | 방법 | 결과 |
|-----------|------|------|
| 봇 프로세스 7개 모두 UP | health_check.py | ✅ 전원 UP |
| .env 설정 로드 | grep .env | ✅ 300s/30s 확인 |
| agent_monitor 데몬 동작 | ps aux | ✅ PID 85019 |
| heartbeat INFO 로그 경로 | ~/.ai-org/{org_id}.log | ✅ 파일 존재, INFO 레벨 수집 |
| heartbeat 실제 발화 로그 | 로그 grep | 대기 중 (장시간 태스크 발생 시 확인) |

> **참고**: heartbeat 실제 발화 로그는 300s 이상 소요되는 태스크 실행 시 `~/.ai-org/{org_id}.log`에서 확인 가능.
> 현재는 배포 후 해당 조건 미발생 — 기능 자체는 테스트 15/15 PASS로 검증 완료.
