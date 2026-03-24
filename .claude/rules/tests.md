# tests/** 코드 규칙

이 규칙은 `tests/` 디렉토리 내 모든 파일에 적용된다.

## 테스트 프레임워크

### pytest 전용
- 모든 테스트는 pytest 기반으로 작성 (unittest.TestCase 혼용 최소화)
- 테스트 파일명: `test_<모듈명>.py`
- 테스트 함수명: `test_<동작>_<조건>` 패턴

### Mock 원칙
- 실제 DB(SQLite, PostgreSQL 등) 를 테스트에서 직접 사용 금지 — `pytest-mock` 또는 인메모리 DB 사용
- 외부 API (Telegram, Claude API 등)는 반드시 mock 처리
- 실제 API 키가 필요한 테스트는 `@pytest.mark.skipif(not os.environ.get('REAL_API_KEY'), reason='requires real API key')` 마킹 필수

### 커버리지 원칙
- 새 기능 추가 시 해당 기능 테스트 함께 추가 (PR 단위)
- 핵심 core/ 모듈은 최소 80% 커버리지 목표
- 버그 수정 시 해당 버그를 재현하는 회귀 테스트 추가 권장

### 금지 패턴
- `time.sleep()` 을 테스트 로직에 직접 사용 금지 — `asyncio.sleep` + `pytest-asyncio` 사용
- 테스트 간 공유 상태(전역 변수, 클래스 변수) 의존 금지 — `fixture`로 격리
- 테스트 내부에서 실제 파일 시스템 프로덕션 경로 사용 금지 — `tmp_path` fixture 사용
