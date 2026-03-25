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

## Gotcha 5: 테스트 봇 토큰을 `.env`에 직접 쓰면 프로덕션 토큰이 덮어씌워짐 ⚠️ 중요

**상황**: 사용자가 E2E 테스트용 임시 봇 토큰 3개를 제공했고, 에이전트가 이를 `.env`의 `PM_BOT_TOKEN` / `BOT_TOKEN_AIORG_PRODUCT_BOT` / `BOT_TOKEN_AIORG_ENGINEERING_BOT`에 직접 덮어씀.
**증상**: 재시작 후 PM봇이 프로덕션 그룹 채팅(-5203707291)에 메시지 전송 불가 → `Chat not found`. SynthesisPoller 합성 성공해도 텔레그램 알림이 전달되지 않음.
**인시던트 날짜**: 2026-03-25
**해결**:
1. E2E 테스트는 **별도 테스트 그룹방** + **전용 테스트 토큰** 사용. 프로덕션 `.env`에 테스트 토큰 절대 기입 금지.
2. 테스트용 변수는 `TEST_PM_BOT_TOKEN`, `TEST_ENGINEERING_BOT_TOKEN` 등 `TEST_` 접두어로 분리.
3. 기존 `.env` 값이 있으면 덮어쓰기 전에 반드시 백업: `cp .env .env.backup.$(date +%Y%m%d)`
4. E2E conftest에서 토큰 주입 시 `os.environ.setdefault()` 사용 → 기존 프로덕션 값 보호.
**복구 방법**: Rocky에게 원본 PM봇 / 기획실 / 개발실 토큰 재요청 후 `.env` 복원.
