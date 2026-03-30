# 2026-03-30 세션 발견 개선점

> 배경: cokac-bot(Rocky의 코딩 에이전트)이 telegram-ai-org 개발실의 실행 상태를 모니터링하던 중 발견한 구조적 문제들.

---

## 1. PM await 블로킹 → 비동기 이벤트 드리븐 전환

**배경**: telegram-ai-org의 PM(pm_orchestrator)이 조직 봇에 태스크를 위임할 때, `telegram_relay.py`에서 `await asyncio.wait_for(runner.run_single(...), timeout=PM_CHAT_REPLY_TIMEOUT_SEC)` 패턴으로 SDK 프로세스 완료를 동기적으로 대기한다. 이로 인해 SDK 프로세스가 실행되는 동안(10분+) PM의 이벤트 루프가 블로킹되어 다른 메시지/이벤트를 처리할 수 없다.

**현재 흐름**:
```
사용자 요청 → PM await → SDK 프로세스 실행 (10분+) → PM 응답
               ↑ 이 동안 PM 죽은 상태
```

**의도한 흐름**:
```
사용자 요청 → PM이 태스크 dispatch → 즉시 복귀 (다른 메시지 처리 가능)
SDK 프로세스 완료 → on_task_complete 이벤트 → PM 보고 전송
```

**관련 파일**:
- `core/telegram_relay.py` ~L1080: `await asyncio.wait_for(runner.run_single(...))` 블로킹 호출
- `core/pm_orchestrator.py` ~L1409: `on_task_complete()` — 다음 태스크 unblock만 하고 텔레그램 보고 없음

**수정 방향**:
- `await runner.run_single()` → `asyncio.create_task()` + 완료 콜백으로 전환
- on_task_complete()에서 텔레그램 보고 로직 추가

---

## 2. Phase별 중간 보고 메커니즘 부재

**배경**: Phase 2(구현) 커밋 완료 → Phase 3(테스트/검증) 커밋 완료까지 모두 정상 진행됐지만, 사용자에게 텔레그램 중간 보고가 한 번도 오지 않았다. 사용자는 외부에서 "지금 뭐하고 있는지" 전혀 알 수 없었다.

**현재 상태**: `pm_orchestrator.py:on_task_complete()` 는 다음을 수행:
1. `graph.mark_complete()` — 태스크 상태 done
2. DB 상태 업데이트
3. 새로 unblock된 태스크 발송
4. ❌ **사용자에게 "Phase X 완료" 알림 없음**

**수정 방향**:
- `on_task_complete()` 에 텔레그램 체크포인트 알림 추가
- 예: "✅ Phase 2 완료 (커밋: 7a6d790) — Phase 3 테스트/검증 시작"
- parent_task가 있으면 진행률 표시 (예: "3/5 완료")

---

## 3. tmux 레거시 코드 정리

**배경**: 실행 엔진이 tmux 기반에서 `claude_agent_sdk` 기반으로 전환됐지만, 코드/설정/메시지에 tmux 잔존물이 다수 남아있다. 텔레그램 사용자에게도 "tmux_batch" 같은 무의미한 런타임 표기가 노출된다.

**삭제/정리 대상 (핵심 코드)**:
- `core/session_manager.py` — 전체가 tmux 기반. 이미 `DEPRECATED` 주석 달림. 호출처 확인 후 삭제
- `core/relay_command_handlers.py` — tmux 참조
- `core/telegram_relay.py` — tmux fallback 로직 (`L1350: "tmux persistent session 실행"`, `L1358: "tmux unavailable -> resume_session fallback"`)
- `core/setup_registration.py` — tmux 참조
- `core/session_registry.py` — tmux 참조
- `tests/test_session_registry.py` — tmux 관련 테스트
- `tests/test_session_manager_shell.py` — tmux 관련 테스트

**설정 파일**:
- `.claude/settings.local.json` — tmux 참조 제거
- `orchestration.yaml` — tmux 참조 제거

**UI/메시지**:
- `dynamic_team_builder.py` 또는 메시지 템플릿에서 "tmux_batch" → "claude_agent_sdk" 표기 교체

**건드리지 않을 것**:
- `docs/orchestration-v2/runs/*/plan.md` (~20개) — 과거 실행 기록이므로 보존

---

## 우선순위 제안

| # | 개선점 | 난이도 | 영향도 | 우선순위 |
|---|--------|--------|--------|----------|
| 1 | await 블로킹 → 비동기 전환 | 높음 | 높음 | P0 |
| 2 | Phase별 중간 보고 추가 | 중간 | 높음 | P0 |
| 3 | tmux 레거시 정리 | 낮음 | 낮음 | P1 |

> #1과 #2는 서로 연관됨 — 비동기 전환이 되어야 중간 보고가 자연스럽게 동작함. 함께 진행 권장.
