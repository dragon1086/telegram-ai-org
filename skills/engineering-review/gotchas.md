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

## Gotcha 5: 기존 파일에 코드 추가 시 import 누락
**상황**: 기존 모듈에 새 코드를 추가하면서 `logger`, `json`, `datetime` 등을 사용할 때
**증상**: 해당 모듈에 import가 없는데도 IDE 자동완성이나 다른 파일 패턴을 무의식적으로 따라 사용. 코드 리뷰에서 놓치면 런타임 `NameError` 발생 (예: T-224 context_db.py `logger` 미import → 태스크 lease claim 전면 실패)
**해결**: 새 코드에서 사용하는 모든 이름이 해당 파일의 import 섹션에 있는지 확인. 특히 프로젝트의 로깅 패턴 확인 — 이 프로젝트는 `from loguru import logger` 사용. Python 3.14에서는 조건부 분기 안의 import도 함수 전체 스코프에 영향주므로 함수 최상단에 배치할 것

## Gotcha 6: Python 3.14 조건부 import로 인한 UnboundLocalError
**상황**: 함수 내 여러 조건 분기에서 `from X import Y`를 하고, 일부 분기에서는 import 없이 Y를 사용할 때
**증상**: Python 3.14에서 `from X import Y`가 한 분기에라도 있으면 Y를 함수 전체에서 local로 마킹. 해당 import 분기를 타지 않으면 `UnboundLocalError: cannot access local variable 'Y'` (예: telegram_relay.py RunContext 사건)
**해결**: 함수 내에서 사용하는 import는 반드시 함수 최상단에 한 번만 배치. 조건부 분기 안에 import를 넣지 말 것

## ⚠️ Gotcha 7 [절대 금지]: 서버 재기동 · 브랜치 푸시 · 브랜치 머지 자체 수행 금지
**상황**: 코드 수정 후 리뷰를 마치면 "커밋 → 푸시 → 재기동"까지 이어서 진행하려는 충동이 생길 때
**증상**: 개발실이 `git push`, `git merge`, `bash scripts/restart_bots.sh` 또는 `request_restart.sh` 를 직접 실행 → 스스로 kill되거나 무한 루프 재실행 (T-224 사례)
**규칙**: 개발실은 **코드 수정과 로컬 커밋까지만** 담당. 아래 세 가지는 반드시 운영실(@aiorg_ops_bot)에 위임 요청:
```
❌ 개발실 자체 수행 금지:
  - git push origin <branch>
  - git merge <branch>
  - bash scripts/restart_bots.sh / scripts/bot_control.sh
  - bash scripts/request_restart.sh

✅ 개발실 완료 후 운영실에 위임:
  "[COLLAB:브랜치 머지 및 전체 재기동 요청|맥락: 개발실 코드 수정 완료]"
```
**해결**: engineering-review 스킬의 마지막 단계는 항상 운영실 위임 메시지 작성으로 끝낼 것
