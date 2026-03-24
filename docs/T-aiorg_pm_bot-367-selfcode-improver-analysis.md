# SelfCodeImprover & ImprovementBus 코드 구조 분석 보고서
**작성일**: 2026-03-24
**목적**: SelfCodeImprover 승인 게이트 구현을 위한 현행 코드 구조 분석
**대상 독자**: @aiorg_engineering_bot (게이트 구현 담당)

---

## ① 관련 파일 맵 (계층 구조)

```
telegram-ai-org/
├── core/
│   ├── improvement_bus.py            ★ 핵심 — 신호 수집 + dispatch + 승인 게이트
│   ├── self_code_improver.py         ★ 핵심 — claude subprocess + git push
│   ├── code_improvement_approval_store.py  ★ 핵심 — pending/approved/rejected 상태 저장소
│   ├── scheduler.py                  ★ 핵심 — 크론 실행 (02:00 KST)
│   ├── telegram_relay.py             ★ 핵심 — /approve_code_fix, /reject_code_fix 핸들러
│   ├── code_health.py                △ 주변 — 코드 건강도 스캔 (신호 생성 원천)
│   ├── self_improve_monitor.py       △ 주변 — 파이프라인 모니터링 로그
│   └── improvement_actions/
│       ├── fix_error_pattern.py      △ 주변 — 에러 패턴 수정 액션
│       └── split_large_file.py       △ 주변 — 대용량 파일 분리 액션
├── scripts/
│   └── run_self_improve_pipeline.py  △ 주변 — 01:17 KST 자가 개선 파이프라인
├── data/
│   ├── code_improvement_approval.json  ○ 설정/데이터 — 승인 큐 영구 저장소
│   └── self_fix_rate.json              ○ 설정/데이터 — rate limit 이력
├── improvement_thresholds.yaml         ○ 설정 — 개선 임계값 설정
├── skills/skill-evolve/SKILL.md        ○ 문서 — 스킬 진화 가이드
└── tests/
    ├── test_improvement_bus.py
    ├── test_self_code_improver.py
    ├── test_code_approval_handler.py
    └── test_code_approval_gate_integration.py
```

**파일 분류표**

| 구분 | 파일 | 역할 |
|------|------|------|
| ★ 핵심 | improvement_bus.py | 신호 수집, priority 라우팅, 승인 게이트 분기 |
| ★ 핵심 | self_code_improver.py | claude subprocess 실행, TDD 루프, git push |
| ★ 핵심 | code_improvement_approval_store.py | pending/approved/executed 상태 관리 |
| ★ 핵심 | scheduler.py | 02:00 KST `_improvement_bus_daily` 크론 |
| ★ 핵심 | telegram_relay.py | `/approve_code_fix` `/reject_code_fix` 커맨드 |
| △ 주변 | code_health.py | CODE_SMELL 신호 원천 (core/ 파일 크기 경고) |
| △ 주변 | run_self_improve_pipeline.py | 01:17 KST 별도 파이프라인 (별개 흐름) |
| ○ 설정 | code_improvement_approval.json | 승인 큐 JSON 영구 저장 |
| ○ 설정 | self_fix_rate.json | 24h 3회 rate limit 이력 |

---

## ② priority≥8 트리거 → git push 시퀀스 다이어그램

```
[OrgScheduler] 매일 02:00 KST
        │
        ▼
scheduler.py:472  _improvement_bus_daily()
        │
        ├─ bus = ImprovementBus()
        ├─ signals = bus.collect_signals()
        │   ├── _signals_from_lesson_memory()   → LESSON_LEARNED (priority = min(10, count+3))
        │   ├── _signals_from_retro_memory()    → PERF_DROP (priority=8, avg_success_rate<70%)
        │   ├── _signals_from_skill_staleness() → SKILL_STALE (priority=7)
        │   └── _signals_from_code_health()     → CODE_SMELL (priority=6 CRITICAL / 3 WARN)
        │
        └─ report = bus.run(signals)
                │
                └─ for signal in signals:
                        │
                        ▼
           improvement_bus.py:247  _dispatch(signal)
                        │
                        ├─ [dry_run=True] → 로그만, 즉시 반환
                        │
                        ├─ [priority < 8 OR target not "code:*"] → label 반환만 (개선 없음)
                        │
                        └─ [priority >= 8 AND target.startswith("code:")]  ← 트리거 조건
                                │
                                ▼
               improvement_bus.py:265  _dispatch_with_approval_gate(signal, label)
                                │
                                ├─ store = CodeImprovementApprovalStore()
                                ├─ approved_items = store.list_approved()
                                │
                                ├─ [매칭 approved 없음] → 경로 A: pending 적재
                                │       │
                                │       ├─ approval_id = store.enqueue(signal_dict)
                                │       │     data/code_improvement_approval.json 에 저장
                                │       │     status="pending"
                                │       │
                                │       └─ pending_notifications.append(알림 메시지)
                                │             → scheduler.py:486 Telegram으로 전송
                                │             → "/approve_code_fix {approval_id}" 안내
                                │
                                └─ [매칭 approved 있음] → 경로 B: 즉시 실행
                                        │
                                        ▼
                    ╔══════════════════════════════════════╗
                    ║  [Rocky /approve_code_fix 승인 후]   ║
                    ║  telegram_relay.py:2489              ║
                    ║  _handle_approve_code_fix()          ║
                    ║   └─ store.approve(approval_id)      ║
                    ║   └─ asyncio.ensure_future(_run_fix) ║
                    ╚══════════════════════════════════════╝
                                        │
                                        ▼
              self_code_improver.py:33  SelfCodeImprover.fix(target, error_summary, related_files)
                                        │
                                        ├─ L38  _check_rate_limit(target)
                                        │     24h 이내 3회 이상이면 None 반환 (중단)
                                        │
                                        ├─ L43  _run_git(["checkout", "-b", branch])
                                        │     branch = "fix/auto-{날짜}-{파일명}"
                                        │
                                        └─ for attempt in range(1, 4):   ← MAX_ATTEMPTS=3
                                                │
                                                ▼
                              L51  _run_claude(prompt)
                                   ┌─────────────────────────────────────────────┐
                                   │ subprocess.run(                              │
                                   │   ["claude", "--print",                      │
                                   │    "--dangerously-skip-permissions",          │
                                   │    "-p", prompt],                            │
                                   │   cwd=REPO_ROOT,          # /telegram-ai-org │
                                   │   capture_output=True,                       │
                                   │   text=True,                                 │
                                   │   timeout=300,            # 5분               │
                                   │ )                                            │
                                   │ → returncode == 0 이면 True 반환             │
                                   └─────────────────────────────────────────────┘
                                                │
                                                ▼
                              L53  _run_tests()
                                   subprocess.run(
                                     [sys.executable, "-m", "pytest", "-q", "--tb=short"],
                                     cwd=REPO_ROOT, timeout=120
                                   )
                                   → (passed: bool, output: str)
                                                │
                              ┌─────────────────┴───────────────────┐
                              │ passed=True                          │ passed=False
                              ▼                                      ▼
                   L55  _commit_and_push(branch, target, attempt)   프롬프트에 test_output 추가
                         │                                           → 다음 attempt 반복
                         ├─ git add -A
                         ├─ git commit -m "fix: 자동 수정 — {target} (시도 {attempt}회)"
                         └─ git push origin {branch}        ← git push 실행 지점
                                   │
                                   ▼
                         L56  _record_rate_limit(target)    # self_fix_rate.json 업데이트
                         L57  _signal_restart(target)       # .restart_requested 플래그
                         L58  FixResult(success=True, branch=branch, ...)
                                   │
                                   ▼
              [3회 모두 실패 시] FixResult(success=False, error_message="max attempts reached")
                         └─ _return_to_main(branch, success=False)
                                   └─ git checkout main (또는 detached HEAD)
                                   └─ git branch -D {branch}  # 실패 브랜치 삭제
```

---

## ③ 훅 포인트 요약표

| # | 위치 (파일:라인) | 훅 유형 | 인터페이스/조건 | 현재 활용 상태 |
|---|-----------------|---------|----------------|---------------|
| H1 | improvement_bus.py:256 | `dry_run` 플래그 | `ImprovementBus(dry_run=True)` | ✅ 활성 — 테스트 시 사용 |
| H2 | improvement_bus.py:260 | priority 분기 | `signal.priority >= 8 and signal.target.startswith("code:")` | ✅ 활성 — 승인 게이트 진입점 |
| H3 | improvement_bus.py:265 | 승인 게이트 | `_dispatch_with_approval_gate()` | ✅ 활성 — pending/approved 분기 |
| H4 | code_improvement_approval_store.py:56 | 큐 적재 | `store.enqueue(signal_dict) → approval_id` | ✅ 활성 — pending 생성 |
| H5 | code_improvement_approval_store.py:71 | 승인 | `store.approve(approval_id) → bool` | ✅ 활성 — Rocky 명령 수신 시 |
| H6 | code_improvement_approval_store.py:82 | 거절 | `store.reject(approval_id) → bool` | ✅ 활성 — Rocky 명령 수신 시 |
| H7 | code_improvement_approval_store.py:126 | 만료 | `store.expire_old_pending(hours=24)` | ✅ 활성 — 매일 02:00 자동 실행 |
| H8 | self_code_improver.py:29 | `dry_run` 플래그 | `SelfCodeImprover(dry_run=True)` | ✅ 활성 — 테스트 시 사용 |
| H9 | self_code_improver.py:38 | rate limit | `_check_rate_limit(target)` — 24h 3회 제한 | ✅ 활성 — 과도 실행 방지 |
| H10 | telegram_relay.py:2489 | Telegram 커맨드 | `/approve_code_fix <id>` | ✅ 활성 — Rocky 승인 경로 |
| H11 | telegram_relay.py:2577 | Telegram 커맨드 | `/reject_code_fix <id>` | ✅ 활성 — Rocky 거절 경로 |
| H12 | scheduler.py:486 | 알림 큐 | `bus.pending_notifications` 순회 전송 | ✅ 활성 — Telegram 알림 |

### 개입 불가 구간 (훅 없음)

| 구간 | 위치 | 이유 |
|------|------|------|
| claude subprocess 실행 중 | self_code_improver.py:113-121 | blocking subprocess.run, 외부 개입 없음 |
| git add → commit → push 순차 실행 | self_code_improver.py:131-140 | `_run_git()` 내 `check=False`, 순차 실행으로 중간 차단 불가 |
| .restart_requested 플래그 생성 | self_code_improver.py:144-147 | 파일 생성 즉시 — watchdog가 감지 후 재기동 |
| `_run_fix()` 백그라운드 태스크 | telegram_relay.py:2528 | `asyncio.ensure_future()` — 응답 반환 후 비동기 실행, 취소 핸들 없음 |

---

## ④ 현행 흐름의 리스크 포인트

### 🔴 RISK-1: git push 실패 감지 불가

```python
# self_code_improver.py:171-172
def _run_git(self, args: list[str]) -> None:
    subprocess.run(["git"] + args, cwd=str(REPO_ROOT), check=False)  # check=False !!
```
- `git push` 실패 (원격 거부, 네트워크 오류 등)해도 예외 발생 안 함
- `FixResult(success=True)`로 반환됨 — push 성공과 commit 성공을 구분 불가
- `mark_executed()`가 호출되어 재시도 불가 상태로 전환됨

### 🔴 RISK-2: `--dangerously-skip-permissions` 플래그

```python
# self_code_improver.py:114
["claude", "--print", "--dangerously-skip-permissions", "-p", prompt]
```
- claude에게 모든 파일 접근/수정 권한 부여
- 프롬프트 인젝션 등 비정상 신호가 들어오면 코드베이스 전체에 대한 수정이 가능

### 🟠 RISK-3: ImprovementBus 경로 B — approved 재진입 시 중복 실행 가능

```python
# improvement_bus.py:277-301
approved_items = store.list_approved()
for item in approved_items:
    if item.get("signal", {}).get("target") == signal.target:
        matched = item
        break
if matched:
    ...
    result = improver.fix(...)
    store.mark_executed(approval_id)
```
- `_improvement_bus_daily`가 실행될 때마다 `list_approved()` 재확인
- Rocky가 승인했으나 02:00 KST 실행 전에 동일 신호가 다시 수집되면:
  - approved 항목 매칭 → `fix()` 즉시 실행
  - 단, `mark_executed` 후에는 재실행 안 됨 (1회 실행 후 안전)

### 🟠 RISK-4: 백그라운드 `_run_fix()` 취소 불가

```python
# telegram_relay.py:2575
asyncio.ensure_future(_run_fix())
```
- `/approve_code_fix` 실행 후 취소 방법 없음
- 실행 중 오류 발생 시 Telegram 알림은 있으나 중단 경로 없음

### 🟡 RISK-5: fix() 실패 시 mark_executed 여부

```python
# improvement_bus.py:299-301 (경로 B)
store.mark_executed(approval_id)
if result and result.success:
    return f"[auto_fixed] {label} ..."
return f"[fix_attempted] {label}"
```
- `result.success=False`여도 `mark_executed()` 호출됨
- 실패 시 동일 항목 재승인 불가 — 새 신호 생성 후 재승인 필요

### 🟡 RISK-6: PERF_DROP 신호 (priority=8, target="bot:all")

```python
# improvement_bus.py:127-136
ImprovementSignal(
    kind=SignalKind.PERF_DROP,
    priority=8,
    target="bot:all",  # "code:" 접두사 아님!
    ...
)
```
- priority=8이지만 `target.startswith("code:")` 조건 불충족 → 승인 게이트 미통과
- 현재 `_dispatch()`에서 `label` 반환만 하고 실제 액션 없음 (무해)

---

## 엔지니어링 팀 인계용 요약 1페이지

### 현재 상태 (2026-03-24 기준)

✅ **구현 완료**:
- `CodeImprovementApprovalStore` — pending/approved/rejected/expired/executed 5-상태 관리
- `ImprovementBus._dispatch_with_approval_gate()` — priority≥8 + code: 신호 → pending 적재
- `/approve_code_fix`, `/reject_code_fix` Telegram 커맨드 핸들러
- 24시간 자동 만료 (`expire_old_pending`)

### 게이트 구현 시 수정 필요 포인트

```
[수정 필요 없음] 승인 흐름 자체는 완성 상태
                 pending → approve → SelfCodeImprover.fix() 경로 정상 작동

[수정 권장 1] self_code_improver.py:171-172
  - _run_git() 내 check=False → check=True 또는 반환값 캡처
  - git push 실패를 FixResult에 반영

[수정 권장 2] self_code_improver.py:131-140
  - _commit_and_push()가 push 성공 여부를 bool로 반환하도록 수정
  - FixResult.success = commit_ok AND push_ok

[수정 권장 3] improvement_bus.py:298
  - fix() 실패 시 mark_executed 조건부 처리
  - result.success=False면 approved 상태 유지 → 재실행 가능하도록
```

### 승인 흐름 재확인 (정상 동작 시나리오)

```
1. 02:00 KST: ImprovementBus 실행
2. priority≥8 + code:X 신호 감지
3. pending 적재 → Telegram 알림:
   "🔔 코드 자동 수정 승인 요청 ... /approve_code_fix {id}"
4. Rocky가 /approve_code_fix {id} 입력
5. store.approve(id) → status="approved"
6. asyncio.ensure_future(_run_fix()) 백그라운드 실행
7. SelfCodeImprover.fix() → claude subprocess → pytest → git push
8. 결과 Telegram 보고 (성공/실패)
9. store.mark_executed(id) → status="executed"
```
