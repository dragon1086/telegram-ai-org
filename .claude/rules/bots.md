# bots/** 코드 규칙

이 규칙은 `bots/` 디렉토리 내 모든 파일(YAML 설정, Python 코드)에 적용된다.

## YAML 설정 파일

### 스키마 검증
- 모든 봇 설정 YAML은 `orchestration.yaml` 스키마 구조를 따른다
- 필수 필드: `id`, `name`, `engine`, `capabilities`
- `engine` 필드는 반드시 허용된 값 중 하나: `claude-code`, `gemini`, `codex`

### 보안 금지 사항
- 토큰, API 키, 패스워드를 YAML 파일에 하드코딩 금지
- 민감한 값은 반드시 환경변수 참조: `${ENV_VAR_NAME}`
- `.env` 파일 경로를 YAML에 직접 명시하지 않는다

### 조직 정의 규칙
- 새 조직 추가 시 반드시 `organizations.yaml`에 등록
- `workers.yaml` 변경 시 `organizations.yaml`과 일관성 유지
- 조직 ID는 snake_case, 영소문자+숫자+언더스코어만 허용

## Python 봇 코드

### 텔레그램 API
- 모든 Telegram API 호출은 try/except로 감싸고 에러 로깅 필수
- rate limit 처리: 429 응답 시 exponential backoff 적용
- 메시지 길이 4096자 초과 시 자동 분할 처리

### 금지 패턴
- 봇 코드에서 직접 `sys.exit()` 호출 금지 — 상위 watchdog에게 위임
- 다른 봇의 설정 파일을 직접 수정하는 코드 금지
