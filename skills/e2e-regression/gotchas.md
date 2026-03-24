# e2e-regression — Gotchas

실제 운영 중 발생한 엣지케이스 모음. E2E 테스트 실행 시 주의할 점.

## Gotcha 1: GeminiCLIRunner 생성은 성공하지만 실행은 OAuth 필요

**상황**: `RunnerFactory.create('gemini-cli')` 는 OAuth 없이도 성공하지만, 실제 `run()` 호출은 `~/.gemini/oauth_creds.json` 필요.
**증상**: 인스턴스화 테스트 통과 → 실제 실행 테스트 실패
**해결**: E2E 테스트에서 실제 run() 호출은 skip 처리하거나 mock 사용. 인스턴스화 성공만 검증.

## Gotcha 2: organizations.yaml 엔진 주석이 YAML 파싱 방해

**상황**: `preferred_engine: gemini-cli  # 주석` 형태로 인라인 주석 추가 시 일부 YAML 파서가 오파싱.
**증상**: yaml.safe_load() 결과가 `gemini-cli  # 주석` 으로 파싱됨
**해결**: 인라인 주석은 별도 행으로 분리하거나, 테스트에서 `.strip().split('#')[0].strip()` 으로 파싱.

## Gotcha 3: 봇 YAML 파일 engine 필드 주석 처리

**상황**: `engine: gemini-cli  # 주석` 형태는 YAML에서 `gemini-cli  # 주석` 으로 읽힘 (문자열에 주석 포함)
**증상**: 엔진 배정 테스트에서 `'gemini-cli  # ...' != 'gemini-cli'` 비교 실패
**해결**: bots/*.yaml 에서 인라인 주석을 별도 행으로 분리. 또는 engine 필드 다음 줄에 engine_note 필드 추가.

## Gotcha 4: tests/e2e/ 에 conftest.py 공통 픽스처 없으면 임포트 실패

**상황**: conftest.py 없이 core 모듈 임포트 시 경로 문제
**증상**: `ModuleNotFoundError: No module named 'core'`
**해결**: `tests/e2e/conftest.py` 에 `sys.path` 설정 확인. 또는 `pytest.ini` 의 `pythonpath = .` 설정 확인.
