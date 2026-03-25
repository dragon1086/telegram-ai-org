# 코드베이스 리팩토링 계획

> **원칙**: 응집도 높고, 결합도 낮고, 각 모듈이 테스트 가능하고, 확장성이 좋도록
> **우선순위**: 오픈소스 출시 후 진행. 핵심 기능 완성 우선.
> **방법**: safe-modify 스킬 원칙 준수 — 단계별, Feature Flag, 최소 범위

---

## 현재 기술 부채 현황 (2026-03-24 기준)

### 높은 결합도 이슈
| 모듈 | 문제 | 영향 범위 |
|------|------|-----------|
| `core/telegram_relay.py` | 2000줄 이상, PM + 봇 통신 + 라우팅 혼재 | 전체 |
| `core/pm_orchestrator.py` | 오케스트레이션 + 디스패치 + 보고 혼재 | PM 플로우 |
| `core/constants.py` | 런타임 YAML 로딩 + 상수 혼재 | 전체 |

### 낮은 테스트 가능성 이슈
| 모듈 | 문제 | 개선 방향 |
|------|------|-----------|
| 봇 이벤트 핸들러 | Telegram 의존성 직접 주입 | 의존성 주입 패턴 |
| 엔진 러너 | subprocess 직접 호출 | 인터페이스 추상화 (BaseRunner 강화) |
| DB 접근 | sqlite 직접 사용 | Repository 패턴 |

---

## Phase 1: 모듈 분리 (Week 2-3)

### 1a. telegram_relay.py 분리
```
telegram_relay.py (현재 2000줄)
  ↓ 분리
├── core/bot_message_handler.py  # 메시지 수신/파싱
├── core/pm_message_handler.py   # PM 전용 핸들러
├── core/bot_dispatcher.py       # 봇 디스패치 로직
└── core/telegram_sender.py      # 전송 전용
```

**완료 기준**: 각 파일 500줄 이하, 단위 테스트 커버리지 80% 이상

### 1b. 의존성 주입 패턴 도입
```python
# AS-IS
class PMOrchestrator:
    def __init__(self):
        self.telegram = TelegramBot()  # 직접 생성

# TO-BE
class PMOrchestrator:
    def __init__(self, telegram: TelegramInterface, runner: BaseRunner):
        self.telegram = telegram  # 주입
        self.runner = runner
```

---

## Phase 2: 레이어 분리 (Week 4-5)

### 2a. Repository 패턴 도입
```
core/
├── repositories/
│   ├── task_repository.py      # 태스크 CRUD
│   ├── message_repository.py   # 메시지 저장
│   └── bot_state_repository.py # 봇 상태
└── services/
    ├── dispatch_service.py     # 디스패치 비즈니스 로직
    └── orchestration_service.py # 오케스트레이션 로직
```

### 2b. 엔진 추상화 강화
```python
# 현재: RunnerFactory.create('claude-code')
# 목표: 엔진 교체가 설정 변경만으로 가능

class EngineRegistry:
    """설정 기반 엔진 레지스트리."""
    @classmethod
    def from_config(cls, org_id: str) -> BaseRunner:
        config = load_org_config(org_id)
        return RunnerFactory.create(config.preferred_engine)
```

---

## Phase 3: 테스트 인프라 강화 (Week 6)

### 3a. 테스트 픽스처 표준화
```python
# tests/conftest.py 강화
@pytest.fixture
def mock_telegram():
    """Telegram API mock."""
    return MockTelegramBot()

@pytest.fixture
def mock_runner():
    """엔진 러너 mock."""
    return MockRunner(response="테스트 응답")
```

### 3b. E2E 테스트 커버리지 목표 ✅ 완료 (2026-03-25)
- Layer 1-3: 100% 커버
- Layer 4 (엔진): 스모크 테스트 100% **달성**
- Layer 5 (회사 시스템): 80% 커버

**E2E 테스트 완비 현황** (2026-03-25 기준):
- `tests/e2e/test_engine_compat_e2e.py` — 3엔진 호환성 (mock dispatch, 에러 핸들링, RunnerFactory)
- `tests/e2e/test_pm_dispatch_e2e.py` — PM 오케스트레이션·BOT_ENGINE_MAP·라우팅 검증
- 전체 **235개 테스트, 0 failed** 확인
- CI: `.github/workflows/ci-e2e.yml` PR 자동 실행 구성 완료
- 문서: `tests/e2e/README.md` 작성 완료

---

## Phase 4: 성능 최적화 (Week 7-8)

### 4a. 비동기 처리 최적화
- 병렬 디스패치 (의존성 없는 태스크 동시 실행)
- 연결 풀링 (DB, Telegram API)

### 4b. 캐싱 전략
- YAML 설정 파일 핫 리로드 캐시
- 봇 상태 캐시 (SharedMemory 활용)

---

## 진행 원칙

1. **Feature Flag 필수**: 리팩토링 코드는 `ENABLE_REFACTORED_*` 플래그 뒤에 숨기기
2. **병렬 구현**: 기존 코드 유지하며 새 구조 병렬 개발, 검증 후 교체
3. **테스트 먼저**: CRAP > 30인 모듈은 테스트 작성 후 수정
4. **한 PR에 한 모듈**: Minimal Footprint 원칙

---

## 참조
- `skills/safe-modify/SKILL.md` — 고위험 코드 수정 절차
- `skills/engineering-review/SKILL.md` — 코드 리뷰 기준
- `ARCHITECTURE.md` — 시스템 아키텍처 (리팩토링 시 동기화)

*최종 업데이트: 2026-03-25 | 상태: Phase 3 E2E 테스트 완비 완료 / Phase 1-2 진행 중*
