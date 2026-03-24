# CONTRIBUTING.md — telegram-ai-org 기여 가이드

telegram-ai-org에 기여해 주셔서 감사합니다!
이 문서는 버그 신고, 기능 제안, 코드 기여 방법을 안내합니다.

---

## 목차

- [행동 강령](#행동-강령)
- [시작하기](#시작하기)
- [브랜치 전략](#브랜치-전략)
- [PR 규칙](#pr-규칙)
- [코드 스타일](#코드-스타일)
- [테스트 작성](#테스트-작성)
- [이슈 등록](#이슈-등록)
- [이슈 템플릿](#이슈-템플릿)
- [커밋 메시지 규칙](#커밋-메시지-규칙)
- [릴리스 절차](#릴리스-절차)

---

## 행동 강령

이 프로젝트는 건설적이고 포용적인 커뮤니티를 지향합니다.
기여자는 다음을 준수해야 합니다:

- 다른 기여자를 존중하고 배려하는 언어 사용
- 기술적 의견 차이는 데이터와 근거로 논의
- 개인 공격이나 차별적 발언 금지
- 유지보수자의 결정 존중

---

## 시작하기

### 로컬 개발 환경 설정

```bash
# 1. 저장소 포크 후 클론
git clone https://github.com/your-username/aimesh.git
cd aimesh

# 2. 의존성 설치 (가상환경 자동 생성)
bash scripts/setup.sh

# 3. 환경 변수 설정
cp .env.example .env
# .env 파일에 테스트용 봇 토큰 설정 (실제 Telegram 봇 토큰 필요)

# 4. 테스트 실행으로 환경 확인
./.venv/bin/pytest -q
```

### 코드 품질 도구 확인

```bash
# ruff 린터 실행
./.venv/bin/ruff check .

# 자동 수정
./.venv/bin/ruff check --fix .
```

### 3개 컨텍스트 파일 동기화 원칙 (필수)

이 프로젝트는 Claude Code / Codex / Gemini CLI 3개 엔진을 지원합니다.
각 엔진은 자신의 컨텍스트 파일만 읽기 때문에 다음 3개 파일은 **항상 동시에 수정**해야 합니다:

```
CLAUDE.md   (가장 상세한 기준 문서)
AGENTS.md   (Codex CLI용, CLAUDE.md와 동기화)
GEMINI.md   (Gemini CLI용, CLAUDE.md와 동기화)
```

한 파일을 수정하면 나머지 두 파일도 같은 내용으로 즉시 업데이트합니다.

---

## 브랜치 전략

### 브랜치 구조

```
main          ─── 프로덕션 배포 기준 (태그 기반 릴리스)
  └── develop ─── 통합 브랜치 (PR 머지 대상)
        ├── feature/xxx   ── 신규 기능
        ├── fix/xxx       ── 버그 수정
        ├── docs/xxx      ── 문서 수정
        ├── refactor/xxx  ── 리팩토링
        └── chore/xxx     ── 빌드/설정 변경
```

### 브랜치 네이밍 규칙

| 유형 | 패턴 | 예시 |
|------|------|------|
| 신규 기능 | `feature/<짧은-설명>` | `feature/docker-compose-support` |
| 버그 수정 | `fix/<짧은-설명>` | `fix/gemini-auth-timeout` |
| 문서 | `docs/<짧은-설명>` | `docs/readme-opensource` |
| 리팩토링 | `refactor/<짧은-설명>` | `refactor/runner-interface` |
| 설정/빌드 | `chore/<짧은-설명>` | `chore/github-actions-ci` |

### 브랜치 생성

```bash
# develop에서 분기
git checkout develop
git pull origin develop
git checkout -b feature/my-feature
```

> **주의**: `main` 브랜치에 직접 푸시하지 마세요. 모든 변경은 `develop` 경유 PR로 머지됩니다.

### Git 워크트리 활용 (병렬 작업 시)

현재 브랜치와 무관한 새 작업을 받으면 워크트리를 사용해 격리합니다:

```bash
# 워크트리 생성
git worktree add .worktrees/<task-slug> develop
cd .worktrees/<task-slug>
git checkout -b fix/<task-slug>

# 작업 완료 후 머지
cd <project-root>
git checkout develop
git merge fix/<task-slug> --no-ff -m "merge: <설명>"

# 정리
git worktree remove .worktrees/<task-slug>
git branch -d fix/<task-slug>
```

---

## PR 규칙

### PR 제출 전 체크리스트

```
[ ] develop 브랜치 기준으로 작성했다
[ ] 로컬에서 .venv/bin/pytest -q 통과 확인
[ ] .venv/bin/ruff check . 경고 없음 확인
[ ] 새 기능/버그 수정에 대한 테스트 추가
[ ] CLAUDE.md / AGENTS.md / GEMINI.md 동시 업데이트 완료 (해당 시)
[ ] .env 파일이나 시크릿이 커밋에 포함되지 않았다 확인
[ ] PR 설명에 변경 사유와 테스트 방법 기재
```

### PR 제목 형식

```
<type>(<scope>): <짧은 설명>
```

| type | 의미 |
|------|------|
| `feat` | 신규 기능 |
| `fix` | 버그 수정 |
| `docs` | 문서 수정 |
| `refactor` | 기능 변경 없는 코드 개선 |
| `test` | 테스트 추가/수정 |
| `chore` | 빌드/설정/CI 변경 |

**예시**

```
feat(gemini): GeminiCLIRunner OAuth 2.0 인증 지원 추가
fix(pm-bot): synthesis_poll_loop needs_review 무한루프 수정
docs(readme): 오픈소스 README 전면 개편
test(e2e): 3엔진 E2E 호환성 테스트 추가
chore(ci): GitHub Actions lint+test 워크플로 추가
```

### PR 설명 템플릿

```markdown
## 변경 사유
<!-- 왜 이 변경이 필요한가 -->

## 변경 내용
<!-- 무엇을 변경했는가 (bullet list) -->
-

## 테스트 방법
<!-- 리뷰어가 어떻게 검증할 수 있는가 -->

## 관련 이슈
<!-- Closes #이슈번호 -->

## 체크리스트
- [ ] 테스트 추가/업데이트
- [ ] 문서 업데이트 (해당 시)
- [ ] Breaking change 없음 (있다면 명시)
- [ ] 3개 컨텍스트 파일 동기화 완료 (CLAUDE.md / AGENTS.md / GEMINI.md)
```

### 리뷰 프로세스

1. PR 생성 → CI 자동 실행 (lint + test)
2. 메인테이너 1명 이상 리뷰 승인 필요
3. `develop` 브랜치로 Squash Merge
4. `main` 머지는 릴리스 시점에 메인테이너가 수행

---

## 코드 스타일

### Python

- **Formatter/Linter**: `ruff` (설정: `pyproject.toml`)
- **Line length**: 100자
- **Python version**: 3.11+
- **타입 힌트**: 모든 함수 시그니처에 필수

```python
# 올바른 예
async def route_task(task: str, context: dict[str, Any]) -> str:
    """태스크를 적합한 부서로 라우팅한다."""
    ...

# 잘못된 예 (타입 힌트 없음)
async def route_task(task, context):
    ...
```

### 파일 구조 원칙

| 디렉토리 | 원칙 |
|----------|------|
| `core/` | 도메인 로직 — 외부 의존성 최소화 |
| `tools/` | CLI 실행 래퍼 — 엔진별 추상화 계층 유지 |
| `skills/` | 재사용 가능한 자동화 워크플로 |
| `tests/` | 미러 구조 (`core/foo.py` → `tests/test_foo.py`) |

### 핵심 코딩 규칙

```python
# 1. 환경 변수는 os.environ 또는 python-dotenv 사용
import os
ENGINE_PATH = os.environ.get("CLAUDE_CLI_PATH", "claude")
# 하드코딩 금지: ENGINE_PATH = "/opt/homebrew/bin/claude"  ❌

# 2. 비동기 함수 우선 (Telegram 봇은 모두 asyncio 기반)
async def handle_message(update: Update, context: Context) -> None:
    ...

# 3. 로깅은 loguru 사용 (print 금지)
from loguru import logger
logger.info("태스크 시작: {task_id}", task_id=task.id)
# print("태스크 시작")  ❌

# 4. 예외 삼킴 금지
try:
    result = await runner.run(task)
except Exception as e:
    logger.error("Runner 실패: {e}", e=e)
    raise   # 반드시 재발생 또는 명시적 처리
# except: pass  ❌ 절대 금지

# 5. 시크릿 하드코딩 금지
# TOKEN = "1234567890:ABC..."  ❌
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]  # ✅
```

### 3개 컨텍스트 파일 동기화

```
수정 대상                동시 업데이트 필수
───────────────────────  ──────────────────────────────
orchestration.yaml       CLAUDE.md + AGENTS.md + GEMINI.md
CLAUDE.md                AGENTS.md + GEMINI.md
새 엔진 추가              tools/러너 + orchestration.yaml + 3개 컨텍스트 파일
bots/*.yaml 구조 변경    CLAUDE.md + AGENTS.md + GEMINI.md
```

### 안전 코드 수정 원칙 (safe-modify)

실패 감지 코드 및 고위험 경로(신뢰도 판단, 라우팅 로직)를 수정할 때:

| 원칙 | 실무 규칙 |
|------|-----------|
| **Minimal Footprint** | PR당 파일 3개 이하, 시그니처 유지 |
| **Defensive Programming** | Guard Clause 우선, `except: pass` 절대 금지 |
| **Feature Flags** | 판정 로직 변경 시 Feature Flag 뒤에 감추기 |
| **Idempotency** | 전역 상태 변경 금지, 순수 함수 지향 |

---

## 테스트 작성

### 테스트 파일 위치

```
tests/
├── test_pm_orchestrator.py          # PM봇 오케스트레이터 단위 테스트
├── test_pm_routing.py               # PM 라우팅 단위 테스트
├── test_context_window.py           # 컨텍스트 창 단위 테스트
├── test_pm_context_injection.py     # PM 컨텍스트 주입 통합 테스트
├── e2e/
│   ├── test_engine_compat_e2e.py    # 3엔진 호환성 E2E (22개)
│   └── test_pm_dispatch_e2e.py      # PM 라우팅 E2E (12개)
└── ...
```

### 테스트 작성 원칙

```python
# 1. pytest-asyncio 사용 (asyncio_mode = "auto" 설정됨)
async def test_pm_router_returns_valid_org():
    router = PMRouter()
    result = await router.route("마케팅 전략 분석해줘")
    assert result.org_id in ("aiorg_growth_bot", "aiorg_research_bot")

# 2. 외부 의존성은 pytest-mock으로 격리
async def test_runner_calls_cli(mocker):
    mock_proc = mocker.patch("tools.claude_code_runner.asyncio.create_subprocess_exec")
    mock_proc.return_value = AsyncMock(stdout=b"결과", returncode=0)
    runner = ClaudeCodeRunner()
    result = await runner.run("테스트")
    assert "결과" in result

# 3. 새 기능/버그 수정 = 테스트 필수
# 4. E2E 테스트는 실제 CLI 없이 시뮬레이션 모드로 실행 가능하게 작성
# 5. 파일명: core/pm_router.py → tests/test_pm_router.py (미러 구조)
```

### 테스트 실행

```bash
# 전체 테스트
./.venv/bin/pytest -q

# 특정 파일
./.venv/bin/pytest tests/test_pm_orchestrator.py -v

# E2E만
./.venv/bin/pytest tests/e2e/ -q

# 커버리지 리포트
./.venv/bin/pytest --cov=core --cov=tools --cov-report=term-missing

# 품질 게이트 (머지 전 권장)
./.venv/bin/ruff check . && ./.venv/bin/pytest -q
```

---

## 이슈 등록

### 이슈 등록 전 확인

1. [기존 이슈](https://github.com/dragon1086/aimesh/issues) 검색 — 중복 확인
2. 최신 `main` 브랜치에서 재현되는지 확인
3. `.env` 설정이 올바른지 확인 (특히 엔진 경로)

### 이슈 라벨

| 라벨 | 의미 |
|------|------|
| `bug` | 버그 신고 |
| `enhancement` | 신규 기능 제안 |
| `documentation` | 문서 개선 |
| `engine:claude-code` | Claude Code 관련 |
| `engine:codex` | Codex 관련 |
| `engine:gemini-cli` | Gemini CLI 관련 |
| `good first issue` | 초보 기여자에게 적합한 이슈 |
| `help wanted` | 도움 필요 |

---

## 이슈 템플릿

### 버그 신고

```markdown
**버그 설명**
<!-- 무슨 일이 일어났는가 -->

**재현 방법**
1.
2.
3.

**기대 동작**
<!-- 어떻게 동작해야 하는가 -->

**실제 동작**
<!-- 어떻게 동작했는가 -->

**환경 정보**
- OS: [예: macOS 14.x / Ubuntu 22.04]
- Python: [예: 3.11.8]
- 사용 엔진: [claude-code | codex | gemini-cli]
- 엔진 버전: [예: claude 1.x.x]

**로그 / 에러 메시지**
\`\`\`
로그 붙여넣기
\`\`\`
```

### 기능 제안

```markdown
**제안 기능 요약**
<!-- 한 문장으로 -->

**동기 / 배경**
<!-- 왜 이 기능이 필요한가 -->

**제안 구현 방법**
<!-- 어떻게 구현할 수 있는가 (선택) -->

**대안**
<!-- 고려한 다른 방법이 있는가 -->
```

---

## 커밋 메시지 규칙

[Conventional Commits](https://www.conventionalcommits.org/) 규칙을 따릅니다.

```
<type>(<scope>): <짧은 설명>

[선택] 상세 설명

[선택] Closes #이슈번호
```

**예시**

```
feat(gemini): GeminiCLIRunner OAuth 2.0 인증 지원 추가

OAuth 2.0 기반 인증을 지원해 API 키 없이도 Gemini CLI를 사용할 수 있게 한다.
~/.gemini/oauth_creds.json 파일을 자동으로 감지하고 fallback으로 API 키를 사용한다.

Closes #42
```

```
fix(pm-bot): synthesis_poll_loop needs_review 상태 무한루프 수정

needs_review 상태를 SQL 제외 조건에 추가해 30초마다 재합성되는 무한루프를 방지한다.

Closes #87
```

---

## 릴리스 절차

> 메인테이너만 수행합니다.

```bash
# 1. develop → main PR 생성 및 머지 (GitHub에서)

# 2. 버전 태그 생성
git checkout main
git pull origin main
git tag -a v1.0.0 -m "Release v1.0.0: 오픈소스 초기 공개"
git push origin v1.0.0

# 3. GitHub Release 생성
gh release create v1.0.0 --notes "릴리스 노트 작성"

# 4. E2E 최종 확인
./.venv/bin/pytest tests/e2e/ -q
```

### 버전 관리 규칙 (Semantic Versioning)

```
MAJOR.MINOR.PATCH
  │      │     └── 버그 수정 (하위 호환)
  │      └──────── 신규 기능 (하위 호환)
  └─────────────── Breaking change (하위 비호환)
```

---

## 배포 및 봇 재기동 원칙

> 이 원칙은 기여자가 직접 봇을 운영하는 경우에 적용됩니다.

- **배포 (git push / git merge)**: 운영실(@aiorg_ops_bot) 전담
- **봇 재기동**: 직접 프로세스 종료 금지 — 반드시 `bash scripts/request_restart.sh --reason "이유"` 사용
  - watchdog가 플래그 파일을 감지하고 안전하게 재기동을 처리
  - 직접 재기동 시 현재 실행 중인 태스크 결과가 유실됨

```bash
# 올바른 재기동 방법
bash scripts/request_restart.sh --reason "코드 수정 완료"

# 금지
bash scripts/restart_bots.sh           # ❌
kill $(pgrep -f main.py)               # ❌
```

---

## 질문이 있으신가요?

- **GitHub Discussions**: 일반적인 질문이나 아이디어 공유
- **GitHub Issues**: [버그 신고 및 기능 제안](https://github.com/dragon1086/aimesh/issues)
- **PR 코멘트**: 코드 관련 구체적 토론

기여해 주셔서 감사합니다!

---

*최종 업데이트: 2026-03-25 | telegram-ai-org contributors*
