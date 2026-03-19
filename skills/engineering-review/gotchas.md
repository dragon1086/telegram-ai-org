# Engineering Review — Gotchas

이 스킬을 사용할 때 자주 발생하는 실수와 주의사항이다.

## Gotcha 1: 시스템 pytest로 실행해 다른 버전 결과 보고
**상황**: `pytest` 명령을 경로 없이 실행할 때
**증상**: 시스템 설치된 pytest(예: 6.x)가 실행되어 venv의 pytest(7.x 이상)와 다른 결과 반환. "테스트 통과"로 보고했지만 실제 venv 환경에서는 실패
**해결**: 반드시 `.venv/bin/pytest -q` 사용. ruff도 동일하게 `.venv/bin/ruff check .` 사용. quality-gate와 동일한 원칙 적용

## Gotcha 2: pip install -e . 로 누락 패키지 설치 시도
**상황**: 리뷰 중 새 패키지가 필요하다고 판단해 `pip install -e .` 실행할 때
**증상**: hatchling 설정 미비로 설치 실패. 이후 `import` 오류가 발생해도 "설치했으니 패키지 문제 아님"으로 오진
**해결**: 이 프로젝트에서 `pip install -e .` 는 작동하지 않음. 누락 패키지는 `.venv/bin/pip install <package>` 로 직접 설치. CLAUDE.md 운영 주의사항 참조

## Gotcha 3: E2E 테스트 실패를 "리뷰 블로커"로 분류
**상황**: `tests/test_collab_e2e.py` 등 E2E 테스트가 포함된 전체 테스트 실행 시
**증상**: E2E 테스트는 실제 봇 토큰이 필요해 CI/로컬 리뷰 환경에서 항상 실패. 이를 코드 문제로 판단해 리뷰 블로킹
**해결**: engineering-review 스킬은 unit/integration 테스트만 검증. E2E 테스트는 스코프 외. `pytest tests/ -ignore=tests/test_collab_e2e.py` 또는 E2E 파일 명시적 제외

## Gotcha 4: async 함수에서 동기 패턴 누락 탐지
**상황**: async def 함수 내부에서 blocking I/O 호출(예: `requests.get`, `time.sleep`)을 사용하는 코드를 리뷰할 때
**증상**: Ruff는 이 패턴을 잡지 못함. 코드 품질 체크리스트만 통과시키고 실제 봇 실행 시 이벤트 루프 블로킹 발생
**해결**: 리뷰 체크리스트에 "async 함수 내 동기 blocking 호출 확인" 항목 추가. `requests` 대신 `aiohttp`, `time.sleep` 대신 `asyncio.sleep` 사용 여부를 수동 확인
