---
name: e2e-regression
description: "Run end-to-end regression tests for the full AI organization platform. Tests all core flows from system-overview: PM routing, bot dispatch, collab protocol, discussion, scheduler, and engine compatibility. Triggers: 'e2e 테스트', 'regression test', 'e2e regression', '회귀테스트', 'smoke test', '전체 테스트', 'full test suite'"
---

# E2E Regression Test Suite (전체 회귀 테스트)

system-overview.html에 기술된 모든 핵심 기능을 E2E로 검증한다.
세션이 끊겨도 이 스킬을 실행하면 현재 시스템 상태를 즉시 파악할 수 있다.

## 테스트 범위 (system-overview 기준)

### Layer 1: 기반 인프라
- [ ] 봇 프로세스 기동 상태 (모든 7개 봇)
- [ ] Telegram Bot API 연결
- [ ] 데이터베이스 (ai_org.db, context.db) 접근성
- [ ] 환경변수 로드 (.env)

### Layer 2: PM 오케스트레이션
- [ ] 사용자 메시지 → PM 수신
- [ ] 태스크 분류 (nl_classifier)
- [ ] 봇 라우팅 (pm_router → 적합한 조직 선택)
- [ ] 태스크 디스패치 (dispatch_engine)
- [ ] 태스크 완료 보고 → PM 집계

### Layer 3: 멀티봇 협업
- [ ] COLLAB 요청 프로토콜 ([COLLAB:...] 태그 파싱)
- [ ] CrossOrgBridge 메시지 라우팅
- [ ] Discussion Manager (5라운드 토론 플로우)
- [ ] P2P 메시지 (봇 간 직접 통신)

### Layer 4: 엔진 호환성
- [ ] claude-code 엔진 실행 (PM, Engineering, Design, Product)
- [ ] codex 엔진 실행 (Ops)
- [ ] gemini-cli 엔진 실행 (Growth, Research)

### Layer 5: 회사 시스템
- [ ] 스케줄러 등록/실행
- [ ] 주간 회고 스킬 (weekly-review)
- [ ] 성과 평가 스킬 (performance-eval)
- [ ] 자동 자기개선 (auto_improve)

---

## Step 1: 사전 점검

```bash
# 현재 시각 확인
date

# 환경 확인
cd /Users/rocky/telegram-ai-org
source .venv/bin/activate

# 필수 프로세스 확인
./.venv/bin/python tools/orchestration_cli.py validate-config
```

## Step 2: Layer별 테스트 실행

### 2a. 유닛/통합 테스트 (빠름, ~30초)

```bash
# 핵심 모듈 테스트
./.venv/bin/pytest tests/test_pm_orchestrator.py tests/test_pm_routing.py tests/test_nl_classifier.py -q

# 엔진 러너 테스트
./.venv/bin/pytest tests/test_codex_runner.py tests/test_base_runner.py -q

# 협업 프로토콜 테스트
./.venv/bin/pytest tests/test_collab_mode.py tests/test_discussion.py -q

# 스케줄러 테스트
./.venv/bin/pytest tests/test_scheduler.py -q
```

### 2b. E2E 통합 테스트 (중간, ~2분)

```bash
# E2E 전체 스위트
./.venv/bin/pytest tests/e2e/ -q --tb=short

# 또는 개별 시나리오
./.venv/bin/pytest tests/e2e/test_pm_dispatch_e2e.py -v
./.venv/bin/pytest tests/e2e/test_collab_e2e.py -v
./.venv/bin/pytest tests/e2e/test_engine_compat_e2e.py -v
```

### 2c. 엔진 호환성 스모크 테스트

```bash
# Claude Code 엔진
./.venv/bin/python -c "
from tools.base_runner import RunnerFactory, RunContext
import asyncio
runner = RunnerFactory.create('claude-code')
print('claude-code runner:', type(runner).__name__, '✓')
"

# Codex 엔진
./.venv/bin/python -c "
from tools.base_runner import RunnerFactory
runner = RunnerFactory.create('codex')
print('codex runner:', type(runner).__name__, '✓')
"

# Gemini CLI 엔진
./.venv/bin/python -c "
from tools.base_runner import RunnerFactory
runner = RunnerFactory.create('gemini-cli')
print('gemini-cli runner:', type(runner).__name__, '✓')
"
```

### 2d. Telegram 연결 스모크 테스트 (선택)

```bash
# Bot API 연결 확인 (토큰 유효성)
./.venv/bin/python scripts/health_check.py --mode api-only --timeout 10
```

## Step 3: 결과 집계

아래 표를 채워 결과를 보고한다:

| 레이어 | 테스트 수 | 통과 | 실패 | 상태 |
|--------|-----------|------|------|------|
| Layer 1: 인프라 | - | - | - | - |
| Layer 2: PM 오케스트레이션 | - | - | - | - |
| Layer 3: 멀티봇 협업 | - | - | - | - |
| Layer 4: 엔진 호환성 | - | - | - | - |
| Layer 5: 회사 시스템 | - | - | - | - |
| **합계** | - | - | - | - |

## Step 4: 실패 항목 처리

실패 항목 발견 시:

1. **즉시 수정 가능**: 수정 후 해당 테스트만 재실행
2. **복잡한 버그**: `tasks/stuck_log.md`에 기록 후 다음 태스크 진행
3. **엔진 관련 실패**: `skills/bot-triage/SKILL.md` 런북 참조

## Step 5: 로그 저장

```bash
# 테스트 결과 로그 저장
./.venv/bin/pytest tests/e2e/ -q --tb=short > logs/e2e_$(date +%Y%m%d_%H%M%S).log 2>&1
echo "로그 저장: logs/e2e_$(date +%Y%m%d_%H%M%S).log"
```

## 완료 기준

- 모든 Layer 1~3 테스트 통과
- 3개 엔진 러너 인스턴스화 성공
- 실패율 0% 또는 알려진 이슈로 문서화됨

---

## 자동화된 E2E 테스트 파일 구조

```
tests/e2e/
├── __init__.py
├── conftest.py              # 공통 픽스처 (mock telegram, mock runners)
├── test_pm_dispatch_e2e.py  # PM → 부서 디스패치 플로우
├── test_collab_e2e.py       # COLLAB 요청 → 응답 플로우
├── test_engine_compat_e2e.py # 3개 엔진 호환성
├── test_discussion_e2e.py   # 5라운드 토론 플로우
└── test_scheduler_e2e.py    # 스케줄 등록/실행
```

## Gotcha 주의사항

- `gotchas.md` 참조
