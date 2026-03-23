# E2E 플로우 검증 최종 리포트 — T-aiorg_pm_bot-303
생성: 2026-03-23 | 담당: aiorg_ops_bot

---

## 최종 판정: **Conditional Pass** ⚠️

> PM → Engineering Bot → PM 순환 플로우는 정상 작동 중.
> 단, 현재 진행 중인 T-302가 lease TTL 초과로 반복 재시도 중이며 auto-fail 임박 (attempt 2/3).

---

## Phase 1 — 배포 전 환경 점검

| 항목 | 결과 |
|------|------|
| Orphan Guard 수정 코드 | ✅ bot-runtime 워크트리 commit `63d7d1c` 반영 완료 |
| 수정 내용 | `parent_row["status"] in ("failed",)` — cancelled 제외, failed만 스킵 |
| DB 경로 | `~/.ai-org/context.db` (4.28MB, 정상 활성) |
| 스테이징 여부 | bot-runtime 워크트리가 staging 역할, 현재 production 실행 중 |
| 봇 기동 확인 | 2026-03-22 18:40:54 KST 재기동 정상 |
| 모니터링 | `~/.ai-org/aiorg_engineering_bot.log` 실시간 기록 중 |

**백업 확인**: 메인 브랜치 코드에 동일 수정 commit `a953451`(메인-워크트리 동기화)로 보존.

---

## Phase 2 — 수정본 배포 및 단위 검증

| 항목 | 결과 |
|------|------|
| 봇 프로세스 상태 | ✅ PID 56673 실행 중 (18:40:54 재기동 후 유지) |
| T-302 최초 감지 | ✅ 18:22:48 KST — `[TaskPoller] 태스크 감지: T-aiorg_pm_bot-302` |
| 오류 로그 | ⚠️ `reply 대상 메시지를 찾지 못해 일반 전송으로 재시도` (경고, 비중단) |
| 단위 테스트 결과 | T-302 이외 오류 없음 |

---

## Phase 3 — End-to-End 플로우 통합 검증

### 시나리오별 결과표

| 시나리오 | 태스크 ID | 상태 | 결과 수신 | PM 후속 처리 |
|---------|----------|------|-----------|-------------|
| 정상 케이스 1 | T-307 | ✅ done (01:37 UTC) | ✅ PM synthesize_and_act 발동 | ✅ debate_dispatch 18:35:46 |
| 정상 케이스 2 | T-300 | ✅ done (17:23 UTC) | ✅ 수신 확인 | ✅ 완료 마킹 |
| 정상 케이스 3 | T-297 | ✅ done (16:58 UTC) | ✅ 수신 확인 | ✅ 완료 마킹 |
| 엣지 케이스 | T-302 | ⚠️ running (retry 중) | 미완료 | 대기 중 |

### 태스크 상태 전환 확인 (T-307 기준)
```
대기(pending) → 할당(assigned) → 실행(running) → 완료(done)
PM debate_dispatch(18:35) → engineering bot 수신 → 실행 → 01:37 UTC done
PM synthesize_and_act 발동 확인
```

### 24시간 통계
- **done**: 23건 ✅
- **running**: 1건 (T-302, retry 중)
- **failed**: 1건 (T-302 관련, 이전 attempt)

---

## Phase 4 — 이상 탐지 및 안정성 모니터링

### T-302 반복 재시도 패턴 (Critical)

| 시각 (KST) | 이벤트 |
|------------|--------|
| 18:22:48 | 1차 실행 시작 |
| 18:26:49 | 2차 실행 시작 (lease 만료 후 재픽업) |
| 18:31:20 | 3차 실행 시작 |
| 18:37:04 | 4차 실행 시작 |
| 18:43:04 | 5차 실행 시작 (현재 진행 중) |

- **lease_expires**: 2026-03-23T01:46:04 UTC
- **attempt_count**: 2/3 → **다음 실패 시 auto-fail**
- **원인**: `DEFAULT_LEASE_TTL_SEC = 180s` (3분) vs 태스크 실행 소요시간 4~6분 불일치

### PM runbook 완료 처리 실패 (Minor)
```
WARNING: [PM] runbook 완료 처리 실패 — state.json No such file or directory
```
삭제된 구 run 디렉토리 참조 문제. 신규 태스크 처리에는 영향 없음.

### 크론 작업 확인
봇 재기동 후 TaskPoller 정상 기동 확인 (`[TaskPoller:aiorg_engineering_bot] 폴링 시작 (간격=2.0s)`).

---

## Phase 5 — 이슈 우선순위 및 권고안

### 이슈 목록

| 우선순위 | 이슈 | 설명 | 조치 |
|---------|------|------|------|
| **Critical** | T-302 auto-fail 임박 | attempt_count=2/3, 다음 실패 시 자동 failed 전환 | lease_ttl 연장 또는 태스크 내용 분리 |
| **Major** | Lease TTL vs 실행시간 불일치 | 복잡한 태스크가 3분 내 완료 불가 → 무한 재시도 패턴 | 복잡도에 따른 TTL 동적 설정 필요 |
| **Minor** | state.json 누락 경고 | 삭제된 구 run 참조 — 비차단 | 오래된 run 참조 정리 |

### 운영 안정화 권고안

1. **lease_ttl 동적 조정**: `complexity=high` 태스크에 TTL 600s 이상 부여
2. **attempt_count 증가**: MAX_TASK_ATTEMPTS=3 → 5로 상향 (복잡 태스크 대비)
3. **T-302 상태 모니터링**: 다음 attempt에서 완료 여부 확인 필요
4. **runbook state.json 정리**: 구 run 참조 DB에서 cleanup 스크립트 적용

---

## 결론

| 플로우 단계 | 판정 |
|------------|------|
| PM → Engineering bot 태스크 할당 | ✅ PASS |
| Engineering bot 수신 및 실행 | ✅ PASS |
| Engineering bot → PM 결과 반환 | ✅ PASS |
| PM 결과 수신 및 synthesize_and_act | ✅ PASS |
| 완료 마킹 및 후속 액션 | ✅ PASS |
| T-302 현재 태스크 완료 | ⚠️ PENDING (auto-fail 위험) |

**전체 E2E 플로우**: **Conditional Pass** — 정상 작동 확인, T-302 완료 여부 추적 필요.
