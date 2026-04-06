# ContextDB.create_pm_task() 조사 보고서

> 태스크 ID: T-aiorg_pm_bot-912
> 조사일: 2026-03-30
> 조사 사유: Daily Retro 대화형 회고 전체 실패 — `ContextDB.create_pm_task() got an unexpected keyword argument 'chat_id'`

---

## ① 함수 시그니처 현황

**파일**: `core/context_db.py`, 라인 272~289

```python
async def create_pm_task(
    self,
    task_id: str,
    description: str,
    assigned_dept: str | None,
    created_by: str,                    # 필수 (기본값 없음)
    parent_id: str | None = None,       # 선택
    metadata: dict | None = None        # 선택
) -> dict:
```

| 파라미터 | 타입 | 필수 여부 | 기본값 |
|---------|------|----------|--------|
| `task_id` | `str` | ✅ 필수 | — |
| `description` | `str` | ✅ 필수 | — |
| `assigned_dept` | `str \| None` | ✅ 필수 | — |
| `created_by` | `str` | ✅ 필수 | — |
| `parent_id` | `str \| None` | 선택 | `None` |
| `metadata` | `dict \| None` | 선택 | `None` |

**`chat_id` 파라미터: 정의되지 않음 (존재하지 않음)**

---

## ② 전체 호출부 목록 및 chat_id 전달 패턴

### 주요 호출부 요약 (프로덕션 코드)

| 파일 | 라인 | chat_id 전달 방식 | created_by | 이상 여부 |
|------|------|-------------------|-----------|----------|
| `core/retro_discussion.py` | 250–255 | `chat_id=self._chat_id` **직접 키워드 인자** | **누락** | ❌ **버그 — 에러 원인** |
| `core/scheduler.py` | 290–296 | `metadata={"chat_id": self._pm_chat_id}` | `"pm_scheduler"` | ✅ 올바름 |
| `core/relay_on_message_mixin.py` | 550, 593, 629 | 없음 | 전달됨 | ✅ 정상 |
| `core/staleness_checker.py` | 214 | 없음 | 전달됨 | ✅ 정상 |
| `core/diverge_converge.py` | 63 | 없음 | 전달됨 | ✅ 정상 |
| `core/collab_dispatcher.py` | 325 | 없음 | 전달됨 | ✅ 정상 |
| `core/pm_discussion_mixin.py` | 300, 510, 587, 632, 665 | 없음 | 전달됨 | ✅ 정상 |
| `core/pm_orchestrator.py` | 1322 | 없음 | 전달됨 | ✅ 정상 |
| `core/pm_synthesis_mixin.py` | 256 | 없음 | 전달됨 | ✅ 정상 |
| `core/telegram_relay.py` | 1475, 2319, 2362, 2398, 3141 | 없음 | 전달됨 | ✅ 정상 |

### 테스트 코드 호출 패턴

| 파일 | 전달 방식 | 비고 |
|------|----------|------|
| `tests/test_verification.py` | positional args 4개 | ✅ 정상 |
| `tests/test_diverge_converge.py` | positional args 4개 | ✅ 정상 |
| `tests/test_pm_orchestrator.py` | positional/keyword | ✅ 정상 |
| `tests/test_context_db_pm.py` | positional args 4개 | ✅ 정상 |
| `tests/test_seed_and_hub_registration.py` | `create_pm_task(id, prompt, org, 0)` | ⚠️ `created_by=0` (int) — 타입 불일치 경고 |

---

## ③ Daily Retro 호출 경로 전문

```
[크론 트리거]
  OrgScheduler.daily_retro()              (core/scheduler.py:476)
  └─ RetroDiscussion(                     (core/scheduler.py:484–489)
       pm_orchestrator=self._pm_orchestrator,
       send_text=self._safe_send,
       pm_chat_id=self._pm_chat_id,       ← GROUP_CHAT_ID (int)
       goal_tracker=self._goal_tracker,
     )
  └─ rd.run_retro(meeting_type="daily_retro")  (core/scheduler.py:490)
       └─ self._run_round("잘한_것", session, orgs)   (retro_discussion.py:~140)
            └─ _collect_org_response(org_id, ...)     (retro_discussion.py:~220)
                 └─ create_pm_task(                   (retro_discussion.py:250–255) ← 💥 에러 발생
                      task_id=parent_task_id,
                      description=prompt[:200],
                      assigned_dept="pm",
                      chat_id=self._chat_id,          ← INVALID KWARG
                      # created_by 누락!
                    )
```

### chat_id 출처 및 전달 경로

```
scheduler._pm_chat_id (= GROUP_CHAT_ID = -5203707291, int)
  → RetroDiscussion.__init__(pm_chat_id=self._pm_chat_id)
    → self._chat_id = pm_chat_id
      → create_pm_task(chat_id=self._chat_id)  ← ❌ 함수 미정의 파라미터
```

---

## ④ 발견된 불일치·누락·잠재 이슈 목록

| # | 이슈 | 파일:라인 | 심각도 |
|---|------|---------|--------|
| **BUG-01** | `create_pm_task()` 호출 시 `chat_id` 미정의 키워드 인자 전달 → 즉시 에러 | `core/retro_discussion.py:254` | 🔴 Critical |
| **BUG-02** | 동일 호출에서 필수 파라미터 `created_by` 완전 누락 | `core/retro_discussion.py:250` | 🔴 Critical |
| **WARN-01** | `test_seed_and_hub_registration.py`에서 `created_by=0` (int 전달, str 기대) | `tests/test_seed_and_hub_registration.py:355,369` | 🟡 Warning |

### BUG-01+02 상세

**문제 코드** (`core/retro_discussion.py:250–255`):
```python
await self._pm._db.create_pm_task(
    task_id=parent_task_id,
    description=prompt[:200],
    assigned_dept="pm",
    chat_id=self._chat_id,     # ← 없는 파라미터. 에러 발생
    # created_by 완전 누락     # ← 필수 파라미터 누락
)
```

**올바른 패턴** (`core/scheduler.py:290–296` 참조):
```python
await self._pm_orchestrator._db.create_pm_task(
    task_id=parent_task_id,
    description=f"[{meeting_type}] {topic}",
    assigned_dept="pm",
    created_by="pm_scheduler",              # ✅ 필수 인자
    metadata={"chat_id": self._pm_chat_id}, # ✅ chat_id는 metadata에 담음
)
```

---

## ⑤ 다음 단계 권고사항

### 즉시 수정 (Critical — Daily Retro 전면 복구)

**`core/retro_discussion.py:250–255` 수정**:

```python
# BEFORE (버그)
await self._pm._db.create_pm_task(
    task_id=parent_task_id,
    description=prompt[:200],
    assigned_dept="pm",
    chat_id=self._chat_id,
)

# AFTER (수정안)
await self._pm._db.create_pm_task(
    task_id=parent_task_id,
    description=prompt[:200],
    assigned_dept="pm",
    created_by="pm_retro_discussion",
    metadata={"chat_id": self._chat_id},
)
```

변경 포인트:
1. `chat_id=` 키워드 인자 제거
2. `created_by="pm_retro_discussion"` 추가 (필수 파라미터)
3. `chat_id`는 `metadata={"chat_id": ...}` 로 이동

### 보조 조치

- `test_seed_and_hub_registration.py` — `created_by=0` → `created_by="test_seeder"` 수정 권장
- `create_pm_task` 함수에 `chat_id` 파라미터 추가 여부 검토: 현재 구조상 `metadata`에 담는 방식이 일관성 있음 → 함수 시그니처 변경 불필요

---

*조사 완료: 2026-03-30 | 담당: 개발실 (aiorg_engineering_bot)*
