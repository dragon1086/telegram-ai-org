# Dependency Audit — telegram-ai-org 경량화 Phase 1

> 작성일: 2026-04-01
> 대상: `/Users/rocky/telegram-ai-org` (main 브랜치 기준)
> Python: 3.14 (`.venv`)
> 분석 대상: 432개 .py 파일 (`.venv/`, `build/`, `_deprecated/`, `.worktrees/` 제외)

---

## 카테고리 1 — 미사용 패키지

코드베이스 전수 grep 결과, `requirements.txt`에 선언된 핵심 의존성 중 **실제 코드에서 한 번도 import되지 않는 패키지는 없음**.

| Package | 사용 위치 | 비고 |
|---------|----------|------|
| python-telegram-bot | core/*.py 18개 파일 전역 | 필수 |
| pydantic | core/ 4개 파일 | 필수 |
| aiosqlite | core/repositories/, core/scheduler.py 등 15개 | 필수 |
| python-dotenv | core/, tools/ 14개 | 필수 |
| PyYAML | core/, tools/, scripts/ 등 광범위 | 필수 |
| loguru | core/, tools/, goal_tracker/ 전역 | 필수 |
| apscheduler | core/scheduler.py, tools/orchestration_cli.py | 필수 |
| rank-bm25 | core/memory_manager.py (lazy-import) | 필수 — lazy 유지 적절 |
| mcp | tools/memory_mcp_server.py 단독 | 필수 |
| claude-agent-sdk | tools/claude_agent_runner.py, scripts/ 4개 | 필수 |

**결론**: 제거 가능한 핵심 의존성 없음.

---

## 카테고리 2 — 중복 패키지 (개발 의존성)

### ruff vs flake8 + black 중복

| 도구 | 기능 | CI 사용 여부 | 권장 |
|------|------|-------------|------|
| ruff | lint + format (flake8 + black 기능 통합) | ✅ ci-lint.yml, ci.yml | **유지** |
| flake8 | lint 전용 | 미사용 | **제거** |
| black | format 전용 | 미사용 | **제거** |

- `.github/workflows/ci-lint.yml`: `ruff check` + `ruff format --check` 만 사용
- 코드베이스 내 `flake8`, `black` 문자열 직접 참조 0건
- **처리**: `requirements-dev.txt` 및 `pyproject.toml [dev]` extras에서 `flake8>=7.0`, `black>=23.0` 제거 완료

---

## 카테고리 3 — 개발전용 패키지 분리 현황

이미 올바르게 분리된 구조:

| 파일 | 목적 |
|------|------|
| `requirements.txt` | 런타임 필수 (10개 패키지) |
| `requirements-test.txt` | 테스트 전용 (pytest 4종) |
| `requirements-dev.txt` | 개발환경 (test 포함 + lint/build/engine SDK) |
| `requirements-optional.txt` | 엔진별 선택 (anthropic/openai/google-genai) |

`requirements-dev.txt`가 `-r requirements-test.txt`를 include하여 계층 구조가 올바르게 유지됨.

---

## 카테고리 4 — 임포트 체인 이슈

### 4.1 순환 임포트 패턴

core 패키지 내 상호 참조 빈도 (상위 5개):
```
148  from core.context_db import ContextDB
 68  from core.orchestration_config import load_orchestration_config
 60  from core.task_graph import TaskGraph
 60  from core.memory_manager import MemoryManager
 51  from core.pm_orchestrator import PMOrchestrator
```

직접적인 순환 임포트는 탐지되지 않음 (`TYPE_CHECKING` 가드 패턴 일부 적용됨).

### 4.2 무거운 임포트 체인 분석

| 모듈 | 임포트 시간 (최적화 전) | 원인 |
|------|----------------------|------|
| `goal_tracker` (패키지) | ~110ms | `__init__.py`가 state_machine 등 모든 서브모듈 eager 로딩 → loguru 67ms 포함 |
| `core.telegram_relay` | ~400ms | python-telegram-bot + 내부 30+ 모듈 체인 |
| `core.orchestration_config` | ~65ms | loguru 초기 로딩 |
| `goal_tracker.state_machine` | ~65ms | loguru 직접 의존 |

### 4.3 goal_tracker __init__.py 최적화 (Phase 3 완료)

**문제**: `goal_tracker/__init__.py`가 모든 서브모듈을 패키지 로드 시점에 eager import.
**원인**: 외부 코드는 `from goal_tracker import X`가 아닌 `from goal_tracker.state_machine import X` 패턴만 사용 — 패키지 수준 re-export가 실제로는 불필요.
**해결**: `__getattr__` 기반 지연 로딩으로 전환 (PEP 562).

```python
# 변경 전: 패키지 import 시 즉시 모든 서브모듈 로딩
from goal_tracker.state_machine import GoalTrackerState, ...

# 변경 후: 실제 접근 시점에 지연 로딩
def __getattr__(name):
    if name in _LAZY:
        mod = importlib.import_module(_LAZY[name][0])
        return getattr(mod, _LAZY[name][1])
```

**결과**: `goal_tracker` cold-start 110ms → 0.5ms (99.5% 단축)

---

## 카테고리 5 — 검토 필요 항목

| 항목 | 현황 | 권장 |
|------|------|------|
| `mcp>=1.0` | `tools/memory_mcp_server.py` 단독 사용 | MCP 서버 미사용 시 optional로 이동 가능. 현재는 유지. |
| `claude-agent-sdk>=0.1.50` | 4개 파일 사용 | 최신 버전 고정 권장 (0.1.50 pinned) |
| `httpx>=0.25` in requirements-optional.txt | python-telegram-bot 내부 의존성으로 이미 requirements.txt 포함 | 중복이나 명시적 고정 목적이므로 유지 가능 |

---

## 요약

| 항목 | 결과 |
|------|------|
| 제거된 미사용 핵심 패키지 | 0개 (모두 사용 중) |
| 제거된 중복 개발 패키지 | 2개 (`flake8`, `black`) |
| 최적화된 __init__.py | 1개 (`goal_tracker/__init__.py`) |
| 임포트 시간 개선 | goal_tracker 110ms → 0.5ms |
| 테스트 통과 | 1035개 passed |
