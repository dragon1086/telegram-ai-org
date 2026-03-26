# scripts/** 코드 규칙

이 규칙은 `scripts/` 디렉토리 내 모든 Shell/Python 스크립트에 적용된다.

## 경로 스코프 제한 (최우선)

### 절대 금지 패턴
- `find ~ -name '*'` / `find / -name '*'` — 홈/루트 전체 탐색 금지
- `glob('/**/*', recursive=True)` — 루트 재귀 glob 금지
- `os.walk(Path.home())` / `os.walk('/')` — 홈/루트 walk 금지
- `ls -R ~/` / `ls -R /` — 재귀 디렉토리 나열 금지

### 허용 패턴 (프로젝트 스코프 내)
- `find /Users/rocky/telegram-ai-org -name '*.db'` — 프로젝트 내부로 한정
- `glob('/Users/rocky/telegram-ai-org/**/*.py', recursive=True)` — 프로젝트 내부만
- 경로 변수: `PROJECT_DIR="/Users/rocky/telegram-ai-org"` 상단 정의 후 사용

### 허용 패턴 (산출물 저장소 — AI_ORG_DATA_DIR)
- `DATA_DIR="${AI_ORG_DATA_DIR:-$HOME/telegram-ai-org-data}"` — 상단에 정의 후 사용
- `find "${DATA_DIR}" -name '*.jsonl'` — 산출물 디렉토리 내부로 한정
- `glob(os.environ.get('AI_ORG_DATA_DIR', str(Path.home() / 'telegram-ai-org-data')) + '/**/*', recursive=True)`
- **금지**: `AI_ORG_DATA_DIR` 없이 `../telegram-ai-org-data/` 상대 경로 하드코딩

## 외부 프로세스 실행

### subprocess 제한
- `subprocess.run()` 시 `shell=True` 사용 시 입력값 검증 필수
- 외부 바이너리 경로는 절대 경로 또는 PATH 화이트리스트 기반
- 사용자 입력을 직접 subprocess 인자로 전달 금지

### 봇 재기동
- 봇 재기동이 필요한 경우: `bash scripts/request_restart.sh --reason "사유"` 전용
- `restart_bots.sh` 직접 호출 금지 — watchdog가 안전하게 처리

## Shell 스크립트 품질

- 첫 줄 shebang: `#!/usr/bin/env bash`
- `set -euo pipefail` 또는 개별 에러 처리
- 변수 참조 시 `"${VAR}"` 큰따옴표 감싸기
- 스크립트 상단에 역할 주석 1줄 이상 필수
