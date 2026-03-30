# Phase 3-B 테스트 범위 정의서

> 작성일: 2026-03-29
> 담당: 개발실 (engineering-senior-developer)
> 기준 브랜치: fix/auto-2026-03-29-telegram_relay

---

## 1. Phase 3-B 핵심 대상 모듈

| 모듈 파일 | 설명 | 테스트 파일 |
|-----------|------|-------------|
| `core/bot_dispatcher.py` | 메시지 타입 분류 및 릴레이 디스패치 | `tests/unit/test_bot_dispatcher.py` |
| `core/pm_message_handler.py` | PM 메시지 핸들러 (리팩토링 1b/1c 결과물) | `tests/unit/test_pm_message_handler.py` |
| `core/context_compressor.py` | CC-01 컨텍스트 압축기 (Phase 2 신규) | `tests/unit/test_context_compressor.py` |
| `core/platform_adapter.py` | PA-01 플랫폼 어댑터 (Phase 2 신규) | `tests/unit/test_transplant_platform_adapter.py` |
| `core/tool_registry.py` | 툴 레지스트리 | `tests/unit/test_transplant_tool_registry.py` |
| `core/relay_command_handlers.py` | 릴레이 커맨드 핸들러 | `tests/unit/test_relay_command_handlers.py` |
| E2E: 엔진 호환성 | 3엔진(claude-code/codex/gemini-cli) 호환 | `tests/e2e/test_engine_compat_e2e.py` |
| E2E: PM 디스패치 | PM 라우터·NL 분류·멀티봇 라우팅 | `tests/e2e/test_pm_dispatch_e2e.py` |
| Integration: 툴 레지스트리 | 툴 레지스트리 전체 흐름 통합 테스트 | `tests/integration/test_tool_registry_integration.py` |

---

## 2. 전체 테스트 스위트 구성

### tests/unit/ (639 케이스)
- `test_bot_dispatcher.py` — 23 케이스
- `test_pm_message_handler.py` — 15 케이스
- `test_context_compressor.py` — 20 케이스
- `test_transplant_platform_adapter.py` — 14 케이스
- `test_transplant_tool_registry.py` — 18 케이스
- `test_relay_command_handlers.py` — 12 케이스
- 기타 35개 파일 — 537 케이스

### tests/e2e/ (418 케이스)
- `test_engine_compat_e2e.py` — 28 케이스
- `test_pm_dispatch_e2e.py` — 84 케이스
- `test_autonomous_loop_e2e.py` — 37 케이스
- `test_weekly_multibot_discussion.py` — 8 케이스
- 기타 6개 파일 — 261 케이스

### tests/integration/ (16 케이스)
- `test_tool_registry_integration.py` — 9 케이스
- `test_e2e_relay.py` — 7 케이스

---

## 3. 컬렉션 결과

- 총 수집 케이스: **1,073개** (unit 639 + e2e 418 + integration 16)
- Import 오류: **0건**
- 수집 실패: **0건**
- 경고: 4건 (pre-flight timeout 기본값 경고 — 코드 오류 아님)

---

## 4. 환경 정보

- Python: 3.14.3
- pytest: 9.0.2
- pytest-cov: 7.1.0
- pytest-asyncio: 1.3.0
- pytest-mock: 3.15.1
- 실행 환경: `.venv` (프로젝트 로컬 venv)
