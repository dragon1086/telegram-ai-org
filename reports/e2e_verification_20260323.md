# E2E 플로우 검증 리포트
**작성일**: 2026-03-23T01:32Z
**작성자**: aiorg_ops_bot (T-aiorg_pm_bot-303)
**검증 대상**: Engineering Bot Orphan Guard 버그 수정 + PM↔Engineering Bot E2E 흐름

---

## 최종 판정

**✅ Conditional Pass** — Orphan Guard 버그 수정 및 E2E 흐름 정상 확인, T-302 완료 대기 중

---

## Phase 1: 배포 전 환경 점검

### ✅ 체크리스트

| 항목 | 결과 |
|------|------|
| engineering bot 설정 파일 확인 | bots/aiorg_engineering_bot.yaml 정상 존재 |
| orchestration.yaml 검증 | validate-config 통과 (7개 조직, 팀 프로파일 정상) |
| DB 위치 확인 | ~/.ai-org/context.db (pm_tasks 테이블 포함) |
| 모니터링 도구 | ps 기반 프로세스 확인, DB 직접 조회 가능 |
| 스테이징 환경 | bot-runtime worktree (.worktrees/bot-runtime/) 정상 구성 |

### 배포 전 상태
- engineering bot에 **2건**의 stuck 태스크 확인:
  - `T-aiorg_pm_bot-212` (status=running, 부모 T-210=cancelled → Orphan Guard에 의해 영구 스킵)
  - `T-aiorg_pm_bot-302` (status=running, 신규 fix 요청 태스크)

---

## Phase 2: 수정본 배포

### ✅ 배포 완료 확인

**커밋**: `63d7d1c — fix: Orphan Guard - cancelled 부모의 자식 태스크 스킵 버그 수정`

**변경 내용 (context_db.py 두 위치)**:

```diff
# get_pending_tasks_for_dept (line 587)
- if parent_row and parent_row["status"] in ("cancelled", "failed"):
+ if parent_row and parent_row["status"] in ("failed",):

# recover_expired_leases (line 786)
- # 부모가 cancelled/failed면 복구하지 않음
+ # 부모가 failed면 복구하지 않음 (cancelled는 제외: 부서 태스크는 계속 실행)
- if prow and prow["status"] in ("cancelled", "failed"):
+ if prow and prow["status"] in ("failed",):
```

**논리**: PM이 부모 태스크를 `cancelled`로 전이시켜도, 부서 할당 자식 태스크는 계속 실행되어야 함.
`failed`는 여전히 전파 차단 대상 (실패 전파 방지).

### 단위 테스트 결과
- 재기동 플래그 잔존: 없음 (request_restart.sh 미사용 — watchdog가 이미 반영 완료)
- 프로세스 상태: engineering bot 정상 동작 (T-212, T-302 모두 lease 갱신 확인)

---

## Phase 3: E2E 플로우 통합 검증

### 시나리오 A: T-aiorg_pm_bot-212 복구 (핵심 케이스)

| 단계 | 상태 | 시각 |
|------|------|------|
| 부모 T-210 cancelled 상태 | 기 존재 | 2026-03-20 |
| T-212 Orphan Guard에 의해 영구 스킵 | 버그 상태 | 3일간 지속 |
| Orphan Guard 수정 (63d7d1c) 배포 | ✅ 완료 | 2026-03-23T01:15Z |
| T-212 lease 갱신 시작 (복구) | ✅ 확인 | 01:30:17 heartbeat |
| T-212 status → done | ✅ 완료 | 01:30~01:32 사이 |
| T-210 자식 전체 done (T-211+T-212) | ✅ 완료 | - |

**결론**: 3일간 stuck 상태였던 T-212가 Orphan Guard 수정 배포 후 즉시 픽업되어 완료됨. ✅

### 시나리오 B: T-aiorg_pm_bot-302 (엔지니어링 봇 fix task 실행)

| 단계 | 상태 |
|------|------|
| PM이 engineering bot에 T-302 할당 | ✅ (01:22:47) |
| Engineering bot이 T-302 수신 및 lease claim | ✅ (attempt_count=3, 갱신 중) |
| 실행 중 heartbeat 갱신 | ✅ (01:31:50 — 확인 당시 기준 1분 전) |
| 완료 후 PM 결과 수신 | 🔄 대기 중 (T-302 실행 중) |

### 시나리오 C: PM → Engineering Bot → PM 순환 (현재 진행 중)

```
T-aiorg_pm_bot-301 (PM parent, status=assigned)
├── T-302 → aiorg_engineering_bot (running, attempt=3, lease 갱신 중)
└── T-303 → aiorg_ops_bot (running = 본 검증 태스크)
```

T-302 완료 시 T-301이 WAITING_ACK로 전이 → PM이 결과 수신 및 마무리 처리 예정.

---

## Phase 4: 이상 탐지 및 안정성 모니터링

### 관찰 결과 (01:22~01:32, 10분간)

| 항목 | 결과 |
|------|------|
| engineering bot 프로세스 | 정상 (lease 갱신 지속 확인) |
| T-302 attempt_count 증가 (1→2→3) | ⚠️ Minor: 재시도 발생 (3회) — 정상 범위 (MAX=3) |
| T-212 stuck → done 전환 | ✅ Orphan Guard 수정 효과 즉시 확인 |
| 타임아웃/중복 실행 | 없음 |
| Cron 작업 | 현재 세션 내 등록 없음 (정기 cron은 별도 프로세스) |

### T-302 attempt_count=3 분석
- MAX_TASK_ATTEMPTS = 3 (context_db.py:635)
- attempt_count=3은 한계치 도달. 현재 lease가 만료되면 **자동 failed 처리 위험** 있음
- 현재 lease는 01:34:50까지 유효. heartbeat이 01:31:50에 확인됨 — 정상 범위 내
- 권고: attempt 완료 전 T-302 결과 확인 필요

---

## Phase 5: 이슈 목록 및 권고사항

### 이슈 우선순위

| 번호 | 이슈 | 우선순위 | 상태 |
|------|------|----------|------|
| I-1 | Orphan Guard: cancelled 부모 자식 태스크 영구 스킵 | **Critical** | ✅ 수정 완료 (63d7d1c) |
| I-2 | T-302 attempt_count=3 — 한계 도달, 만료 시 failed 위험 | **Major** | 🔄 모니터링 중 |
| I-3 | run-20260323T011557Z: 1초 내 완료된 외부 리포지토리 수정 run | **Minor** | 내용 확인 필요 |
| I-4 | T-aiorg_pm_bot-246 (assigned, 장기 미처리) | **Minor** | 별도 조사 필요 |

### 운영 안정화 권고사항

1. **MAX_TASK_ATTEMPTS 상향 검토**: 현재 3회. 엔지니어링 봇처럼 실행 시간이 긴 태스크는 attempt 소진 시 실패 처리되는 위험 존재. 5~7회로 상향 검토.
2. **attempt_count 경고 알림 추가**: attempt가 MAX의 80% 이상일 때 PM 알림 발송 권고.
3. **Orphan Guard 로직 문서화**: 현재 주석만으로 존재. tests/에 전용 단위 테스트 추가 권고.
4. **T-aiorg_pm_bot-246 등 zombie assigned 태스크 정리**: 정기적인 stale task cleanup cron 검토.

---

## PM 제출용 요약

**결론**: Engineering Bot 수정 (Orphan Guard) 은 배포 완료되었고 즉각적인 효과가 확인됨.

- T-212: 3일간 stuck → 수정 직후 `done` 전환 ✅
- T-302: engineering bot이 실제로 태스크를 수신·실행 중 ✅ (attempt=3, 갱신 진행)
- PM → Engineering Bot → PM 루프: T-302 완료 후 T-301 마무리 처리 예정 🔄

**주의**: T-302가 attempt_count 한계(3회)에 도달함. 현재 lease 내 완료되면 정상이나, 만료 시 자동 failed 처리됨. 후속 모니터링 필요.
