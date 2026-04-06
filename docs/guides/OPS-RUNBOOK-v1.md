# 운영 매뉴얼 (Runbook) — telegram-ai-org v1.0.0
> Phase 4 산출물 | 작성: 운영실(aiorg_ops_bot) | 날짜: 2026-03-29

---

## 1. 모니터링 체계

### 1.1 상시 모니터링 컴포넌트

| 컴포넌트 | 경로 | 주기 | 역할 |
|---------|------|------|------|
| bot_watchdog.py | scripts/ | 상시 (데몬) | 봇 프로세스 사망 감지 + 자동 재기동 |
| health_check.py | scripts/ | 수동 / CI | API 연결 + 봇 응답 확인 |
| ops_rollout_monitor.py | scripts/ | 배포 후 15분 | 배포 직후 안정성 모니터링 |
| agent_monitor.py | scripts/ | 주기적 | 에이전트 응답 품질 모니터링 |
| status_dashboard.py | scripts/ | 수동 | 전체 봇 상태 대시보드 출력 |

### 1.2 E2E 로그 헤더 모니터링 (RETRO-10 완성)

E2E 실행 시 `logs/e2e_preflight_latest.log`에 자동 삽입되는 헤더:
```
[PREFLIGHT] timestamp=2026-03-29T...
[PREFLIGHT] baseline=v1.2.0
[PREFLIGHT] timeout=120s
[PREFLIGHT] telethon_filter=record_on_activation
[PREFLIGHT] status=PASS
```

로그 확인 명령:
```bash
tail -f logs/e2e_preflight_latest.log
cat logs/e2e_preflight_latest.log | grep "\[PREFLIGHT\]"
```

### 1.3 크론 작업 현황
```bash
# 등록된 크론 확인
python tools/memory_ttl_checker.py  # 매일 00:00 KST 메모리 TTL 관리
python scripts/daily_metrics.py     # 일간 지표
python scripts/daily_retro.py       # 일간 회고
```

---

## 2. 알림 체계

### 2.1 텔레그램 알림 (현행)
- 모든 운영 알림은 텔레그램 채팅방으로 전달
- 봇 재기동 완료/실패: watchdog이 채팅방에 자동 통보
- 배포 완료: 운영 PM이 수동 보고

### 2.2 알림 레벨 정의

| 레벨 | 조건 | 대응 |
|-----|------|------|
| 🔴 CRITICAL | 봇 3분 이상 무응답 / E2E 전체 실패 | 즉시 triage (bot-triage 스킬 실행) |
| 🟠 WARNING | E2E 일부 실패 / pre-flight WARN | 원인 분석 후 1시간 내 조치 |
| 🟡 INFO | 배포 완료 / 재기동 성공 | 채팅방 보고만 |
| 🟢 OK | 정상 운영 | 모니터링 유지 |

### 2.3 봇 장애 대응 (bot-triage 스킬)
```
트리거 조건: 봇 응답 없음 / 크래시 / 비정상 동작
```
대응 순서:
1. `/bot-triage` 스킬 실행 → 자동 진단
2. 프로세스 확인: `bash scripts/bot_control.sh status`
3. 로그 확인: `tail -100 logs/bot_*.log`
4. 안전 재기동: `bash scripts/request_restart.sh --reason "장애 복구"`
5. 인시던트 보고서 생성 (engineering-incident-response-commander 에이전트)

---

## 3. 롤백 계획

### 3.1 롤백 판단 기준

| 지표 | 정상 | 롤백 기준 |
|-----|------|---------|
| E2E 통과율 | 100% (430/430) | 95% 미만 (20개 이상 실패) |
| 봇 응답률 | 100% | 80% 미만 |
| pre-flight | PASS | FAIL |
| P95 응답시간 | < 30초 | > 120초 지속 |

### 3.2 즉시 롤백 트리거
- 배포 후 5분 내 봇 전체 무응답
- pre-flight FAIL 지속
- 텔레그램 메시지 수신 중단

### 3.3 롤백 실행
```bash
# 코드 롤백 (git revert)
git log --oneline -5          # 롤백 대상 커밋 확인
git revert <commit-hash> --no-edit
gh pr create --title "revert: 긴급 롤백 - [사유]"
# CI 통과 후 머지

# 즉시 재기동 요청
bash scripts/request_restart.sh --reason "긴급 롤백 후 재기동"

# 상태 확인
python scripts/health_check.py
```

---

## 4. 장애 대응 시나리오

### 시나리오 A: 봇 전체 무응답
```
1. bot-triage 스킬 실행
2. bot_control.sh status → 프로세스 상태 확인
3. 로그에서 오류 확인
4. request_restart.sh 실행
5. 5분 내 미복구 → 롤백 실행
```

### 시나리오 B: 특정 봇만 장애
```
1. 해당 봇 로그 확인
2. 해당 봇만 재기동 요청 (request_restart.sh --bot <봇명>)
3. 오류 원인 분석 → 핫픽스 배포
```

### 시나리오 C: E2E 테스트 대규모 실패
```
1. 로그 확인: logs/e2e_preflight_latest.log
2. pre-flight 수동 실행: bash scripts/preflight_check.sh --fail-fast
3. infra-baseline.yaml 버전 확인
4. 환경 격리 디버깅: docs/ENV_DEBUG_GUIDE.md 참조 (RETRO-02 완성)
5. 코드 vs 인프라 이분 → 원인 특정 후 수정
```

### 시나리오 D: 인프라 베이스라인 불일치
```
1. infra-baseline.yaml 현행 버전 확인
2. 최신 버전으로 복구 (git checkout)
3. pre-flight 재실행
4. E2E 재실행 확인
```

---

## 5. 정기 운영 체크리스트

### 일간 (매일)
- [ ] `python scripts/health_check.py` 실행
- [ ] `python scripts/status_dashboard.py` 상태 확인
- [ ] logs/e2e_preflight_latest.log 이상 여부 확인
- [ ] memory_ttl_checker.py 크론 정상 실행 여부

### 주간 (매주 월요일)
- [ ] `/harness-audit` 스킬 실행 → 전체 시스템 헬스 체크
- [ ] `python scripts/weekly_standup.py` 지표 리뷰
- [ ] E2E 전체 실행: `python -m pytest tests/e2e/ --timeout=120`
- [ ] infra-baseline.yaml 버전 유효성 재확인

### 월간
- [ ] `python scripts/monthly_review.py` 실행
- [ ] 보안 감사 (validate-dangerous-patterns.sh)
- [ ] 의존성 업데이트 검토 (pyproject.toml)
- [ ] Docker 이미지 갱신

---

## 6. 환경 격리 디버깅 가이드 (요약)

> 상세: `docs/ENV_DEBUG_GUIDE.md` (RETRO-02 완성, 6개 섹션)

**10분 이내 코드/인프라 이분 방법:**
1. pre-flight 실행 → PASS면 인프라 정상 → **코드 문제**
2. pre-flight FAIL → infra-baseline.yaml 확인 → **인프라 문제**
3. 로컬 통과 + CI 실패 → 환경변수/시크릿 누락 → **CI 설정 문제**
4. 특정 봇만 실패 → 해당 엔진 API 키 확인 → **인증 문제**

---

## 7. 운영 도구 빠른 참조

```bash
# 전체 봇 상태
bash scripts/bot_control.sh status

# 봇 재기동 요청 (안전)
bash scripts/request_restart.sh --reason "사유"

# pre-flight 체크
bash scripts/preflight_check.sh

# 헬스체크
python scripts/health_check.py

# 상태 대시보드
python scripts/status_dashboard.py

# E2E 전체 실행
python -m pytest tests/e2e/ --timeout=120 -v

# 롤아웃 모니터링
python scripts/ops_rollout_monitor.py --duration 15m

# 하네스 감사
python scripts/run_harness_audit.py
```
