# core/** 코드 규칙

이 규칙은 `core/` 디렉토리 내 모든 파일에 적용된다.

## 필수 원칙

### async 유지
- 모든 public 비동기 함수는 `async def` 유지 — 동기 함수로 변환 금지
- `asyncio.run()`을 core 모듈 내부에서 직접 호출하지 않는다 (엔트리포인트 전용)
- 동기 I/O (time.sleep, requests.get 등)는 `run_in_executor`로 감싸서 사용

### Public 시그니처 보존
- 기존 public 함수/메서드의 파라미터 이름·타입·반환 타입을 변경할 때는 반드시 하위 호환성 확인
- 제거 전에 deprecation 주석 1주 이상 유지
- 내부 구현 변경은 자유, public interface 변경은 PM 승인 필요

### 보안
- 환경변수(API 키, 토큰, 비밀번호)를 코드에 하드코딩 절대 금지
- `os.environ.get('KEY')` 패턴 사용, 없을 때 None 반환 후 상위에서 처리
- `.env` 파일을 `print()`나 로그에 직접 출력 금지

### 코드 품질
- 줄 길이: 최대 100자 (ruff 설정 기준)
- type annotation 필수 (파라미터 + 반환값)
- docstring: public 함수에는 한 줄 이상 필수
- TODO/FIXME 작성 시 담당자와 날짜 명시: `# TODO(담당자): 내용 (YYYY-MM-DD)`

### 금지 패턴
- `glob.glob('/**', recursive=True)` — 홈/루트 재귀 탐색 절대 금지
- `os.walk(Path.home())` — 홈 디렉토리 전체 탐색 절대 금지
- `import *` — 와일드카드 임포트 금지
- `print()` 디버그 출력 — `logging` 모듈 사용
