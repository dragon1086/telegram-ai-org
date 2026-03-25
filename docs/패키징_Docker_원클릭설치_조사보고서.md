# 패키징 · Docker · 원클릭 설치 조사 보고서

> 작성일: 2026-03-25 | 조사 범위: PyPI 표준, Docker 배포 BP, 3엔진 설치 레퍼런스
> 원시데이터: `docs/조사_원시데이터.md`

---

## 목차

1. [PyPI 패키징 권장 방식 비교표](#1-pypi-패키징-권장-방식-비교표)
2. [Docker 오픈소스 배포 체크리스트](#2-docker-오픈소스-배포-체크리스트)
3. [3엔진 원클릭 설치 레퍼런스 사례](#3-3엔진-원클릭-설치-레퍼런스-사례)
4. [telegram-ai-org 오픈소스화 추천 방향](#4-telegram-ai-org-오픈소스화-추천-방향)

---

## 1. PyPI 패키징 권장 방식 비교표

### 1-1. 방식별 비교

| 항목 | **pyproject.toml** | **setup.cfg** | **setup.py** |
|------|:-----------------:|:------------:|:-----------:|
| **현재 표준 여부** | ✅ 공식 표준 (PEP 621) | ⚠️ 레거시 지원 | ⚠️ 하위 호환성 유지 |
| **포맷** | TOML (정적) | INI (정적) | Python 코드 (동적) |
| **빌드 백엔드 지원** | 모든 백엔드 | setuptools 전용 | setuptools 전용 |
| **보안** | ✅ 코드 실행 없음 | ✅ 코드 실행 없음 | ❌ pip install 시 코드 실행 |
| **도구 통합** | ruff/mypy/pytest 설정 병합 가능 | 부분 지원 | 별도 파일 필요 |
| **동적 버전 관리** | `dynamic = ["version"]` 선언 | 불가 | 완전 지원 |
| **2025 채택률** | 신규 프로젝트 표준 | 기존 setuptools 프로젝트 | ~70% (암묵적, 미선언) |
| **PyPA 권장** | ✅ 최우선 권장 | 마이그레이션 권장 | 단계적 제거 권장 |

### 1-2. PEP 로드맵 요약

```
PEP 518 (2016) ─→ pyproject.toml 파일 도입 (빌드 의존성 선언)
PEP 517 (2017) ─→ 빌드 백엔드 인터페이스 표준화 (setup.py 직접 실행 탈피)
PEP 621 (2021) ─→ [project] 테이블 표준화 (메타데이터 백엔드 중립 선언)
PEP 639 (2024) ─→ SPDX 라이선스 표현식 표준화
```

### 1-3. 권장 pyproject.toml 최소 구조

```toml
[build-system]
requires = ["setuptools>=61", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "my-package"
version = "0.1.0"
description = "One-line summary"
readme = "README.md"
license = "MIT"               # PEP 639 SPDX 표현식
requires-python = ">=3.10"
dependencies = [
    "httpx>=0.25",
]

[project.optional-dependencies]
dev = ["pytest>=7.0", "ruff>=0.1"]

[project.scripts]
my-cli = "my_package.__main__:main"

[project.urls]
Repository = "https://github.com/org/repo"
```

### 1-4. 현 프로젝트 상태 평가

| 점검 항목 | 상태 | 비고 |
|-----------|------|------|
| `[build-system]` 선언 | ✅ | `setuptools>=61` + `wheel` |
| `[project]` PEP 621 준수 | ✅ | name/version/description/license/dependencies 완비 |
| PEP 639 SPDX 라이선스 | ✅ | `license = "MIT"` |
| 엔진별 optional-dependencies | ✅ | `claude` / `codex` / `gemini` extras 분리 |
| `[project.scripts]` 진입점 | ✅ | 4개 CLI 진입점 정의 |
| setup.cfg 레거시 병행 | ✅ | pip < 21.3 대응 fallback |
| setup.py 잔존 여부 | ⚠️ | 현재 존재 — 필요 없으면 제거 고려 |

> **결론**: 현 pyproject.toml은 표준을 완전히 준수한다. `setup.py`는 복잡한 빌드 로직이 없다면 삭제하고 pyproject.toml 단독 운영을 권장한다.

---

## 2. Docker 오픈소스 배포 체크리스트

### 2-1. 단계별 권장 패턴

#### Stage 설계

| 단계 | 목적 | 권장 베이스 | 안티패턴 |
|------|------|------------|---------|
| **builder** | 의존성 컴파일 + wheel 생성 | `python:3.11-slim` | ❌ 전체 ubuntu 사용 |
| **installer** (선택) | Node.js CLI 설치 | `node:20-slim` | ❌ runtime에서 npm 설치 |
| **runtime** | 최종 실행 | `python:3.11-slim` (최소 이미지) | ❌ builder 이미지 그대로 사용 |

#### .dockerignore 필수 항목

```
# VCS
.git
.github

# Python
.venv/
venv/
__pycache__/
*.pyc
*.egg-info/
dist/
build/

# 환경/시크릿
.env
.env.*
!.env.example

# 문서/테스트
*.md
tests/
*.log

# 프로젝트 특화
.worktrees/
logs/
reports/
tasks/
```

#### ENTRYPOINT / CMD 패턴

```dockerfile
# 권장: ENTRYPOINT + CMD 조합
ENTRYPOINT ["python", "-m", "telegram_ai_org"]
CMD []

# 초기화 스크립트 필요 시
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["python", "-m", "telegram_ai_org"]
```

### 2-2. 보안 체크리스트

- [ ] **비루트 사용자 실행**: `useradd -r` + `USER <non-root>` 설정
- [ ] **베이스 이미지 버전 고정**: `python:3.11-slim` (digest 핀닝 권장)
- [ ] **.env 파일 절대 COPY 금지**: `--env-file` 또는 환경변수 주입
- [ ] **최소 권한 원칙**: 쓰기 가능 디렉토리만 `chown` (logs, data, reports)
- [ ] **패키지 캐시 삭제**: `rm -rf /var/lib/apt/lists/*`
- [ ] **HEALTHCHECK 설정**: 봇 PID 파일 또는 HTTP 엔드포인트 확인

### 2-3. GHCR 배포 권장 워크플로우

```yaml
# .github/workflows/docker-publish.yml
name: Docker Publish

on:
  push:
    tags: ['v*']

jobs:
  build-push:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    strategy:
      matrix:
        engine: [claude, codex, gemini]

    steps:
      - uses: actions/checkout@v4

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          build-args: ENGINE=${{ matrix.engine }}
          push: true
          tags: |
            ghcr.io/${{ github.repository }}:${{ github.ref_name }}-${{ matrix.engine }}
            ghcr.io/${{ github.repository }}:latest-${{ matrix.engine }}
```

### 2-4. 현 Dockerfile 평가

| 항목 | 상태 | 비고 |
|------|------|------|
| 멀티스테이지 빌드 (3단계) | ✅ | builder / node-installer / runtime |
| 비루트 사용자 (`aiorg`) | ✅ | useradd -r -u 1001 |
| HEALTHCHECK 설정 | ✅ | PID 파일 확인 방식 |
| ENTRYPOINT 패턴 | ✅ | `python -m telegram_ai_org` |
| OCI 라벨 (`org.opencontainers`) | ✅ | title/description/source/version |
| ARG ENGINE 분기 | ✅ | base/claude/codex/gemini |
| .dockerignore | ⚠️ | **파일 없음 — 생성 필요** |
| runtime에서 의존성 하드코딩 | ⚠️ | `pyproject.toml`과 이중 관리 위험 |
| Node.js apt 설치 (runtime) | ⚠️ | `node-installer` 스테이지 결과물만 COPY하면 충분 — apt nodejs 제거 가능 |

> **핵심 개선 포인트**: `.dockerignore` 파일 생성이 가장 시급하다. 현재 없으면 `.venv/`, `.git/`, `logs/` 등이 빌드 컨텍스트에 포함되어 빌드 속도 저하 및 시크릿 노출 위험이 있다.

---

## 3. 3엔진 원클릭 설치 레퍼런스 사례

### 3-1. 엔진별 설치 명령 정리

| 엔진 | npm (Node 필요) | Homebrew | 네이티브/기타 | 바이너리명 |
|------|----------------|---------|-------------|----------|
| **claude-code** | `npm install -g @anthropic-ai/claude-code` *(deprecated)* | `brew install --cask claude-code` | `curl -fsSL https://claude.ai/install.sh \| bash` ⭐ | `claude` |
| **codex** | `npm install -g @openai/codex` ⭐ | `brew install --cask codex` | GitHub Releases 바이너리 | `codex` |
| **gemini-cli** | `npm install -g @google/gemini-cli` ⭐ | `brew install gemini-cli` | `npx @google/gemini-cli` (임시) | `gemini` |

> ⭐ = 가장 범용적 설치 방법

### 3-2. 설치 스크립트 자동 감지 패턴 (오픈소스 프로젝트 레퍼런스)

#### 패턴 A: 순차 감지 (현 `scripts/setup.sh` 방식)
```bash
detect_engine() {
    for engine in claude codex gemini; do
        if command -v "$engine" &>/dev/null; then
            echo "$engine"
            return 0
        fi
    done
    echo "none"
}
AI_ENGINE=$(detect_engine)
```

#### 패턴 B: 우선순위 + 버전 검증
```bash
check_engine() {
    local bin="$1"
    command -v "$bin" &>/dev/null && "$bin" --version &>/dev/null 2>&1
}

if check_engine claude; then   AI_ENGINE="claude-code"
elif check_engine codex; then  AI_ENGINE="codex"
elif check_engine gemini; then AI_ENGINE="gemini-cli"
else
    echo "⚠️  No AI engine found. Installing recommended engine..."
    npm install -g @anthropic-ai/claude-code
    AI_ENGINE="claude-code"
fi
```

#### 패턴 C: Docker 원라이너 (오픈소스 배포용)
```bash
# 기본 (엔진 없는 base 이미지)
docker run --env-file .env ghcr.io/org/telegram-ai-org:latest

# 특정 엔진 포함
docker run --env-file .env ghcr.io/org/telegram-ai-org:latest-claude
docker run --env-file .env ghcr.io/org/telegram-ai-org:latest-codex
docker run --env-file .env ghcr.io/org/telegram-ai-org:latest-gemini
```

### 3-3. Homebrew Formula 구조 참조 (오픈소스 표준)

```ruby
# Homebrew Cask (바이너리 배포)
cask "telegram-ai-org" do
  version "0.1.0"
  sha256 "<checksum>"

  url "https://github.com/org/telegram-ai-org/releases/download/v#{version}/telegram-ai-org-#{version}-macos.tar.gz"
  name "telegram-ai-org"
  desc "AI organization on Telegram — multi-agent PM bot system"
  homepage "https://github.com/org/telegram-ai-org"

  binary "telegram-ai-org"
  zap trash: "~/.aiorg"
end
```

### 3-4. pip install 원라이너 패턴

```bash
# 기본 설치
pip install telegram-ai-org

# 엔진별 선택 설치
pip install "telegram-ai-org[gemini]"   # Gemini SDK 포함
pip install "telegram-ai-org[all]"      # 전체 선택적 의존성

# 개발 환경
pip install "telegram-ai-org[dev]"

# 설치 후 원라이너 실행
telegram-ai-org --help
aiorg-pm --help
```

---

## 4. telegram-ai-org 오픈소스화 추천 방향

### 4-1. 현황 종합 평가

| 영역 | 완성도 | 핵심 갭 |
|------|--------|---------|
| **PyPI 패키징** | 🟢 95% | setup.py 잔존 (선택적 제거 가능) |
| **Dockerfile** | 🟢 90% | .dockerignore 없음, runtime Node.js apt 설치 중복 |
| **docker-compose.yml** | 🟢 85% | profiles 구조 완성, Redis 포함 |
| **원클릭 설치 스크립트** | 🟡 75% | 자동 감지는 있으나 미설치 시 자동 설치 로직 없음 |
| **CI/CD (GitHub Actions)** | 🔴 30% | PyPI publish + GHCR push 워크플로우 미작성 |

### 4-2. 우선순위별 추천 조치

#### 🔴 즉시 (1~2일) — 오픈소스화 차단 요소

1. **`.dockerignore` 생성**
   - 현재 없음 → 빌드 컨텍스트에 `.venv/`, `logs/`, `.git/` 포함됨
   - `.venv/`, `.git/`, `logs/`, `.env*`, `*.pyc`, `.worktrees/` 제외 필요

2. **GitHub Actions CI/CD 워크플로우 작성**
   - `.github/workflows/publish.yml` (PyPI Trusted Publishing)
   - `.github/workflows/docker.yml` (GHCR 3엔진 이미지 push)
   - 트리거: `push tags: ['v*']`

3. **`setup.py` 역할 확인 및 제거 검토**
   - `pyproject.toml`만으로 충분 → 혼동 방지를 위해 제거 권장
   - 단, 하위 호환 CI가 있으면 유지 가능

#### 🟡 단기 (3~5일) — 품질 향상

4. **원클릭 설치 스크립트 강화**
   - 엔진 미설치 시 자동 설치 제안 로직 추가 (패턴 B)
   - `--engine claude|codex|gemini` 인수 지원

5. **Docker runtime 이미지 최적화**
   - `apt-get install nodejs` 제거 → `node-installer` 스테이지 COPY로 대체
   - `COPY --from=node-installer /usr/local/bin/node /usr/local/bin/node` 패턴

6. **`.env.example` 완성**
   - 현재 누락된 `AI_ENGINE=` 변수 추가 확인
   - 각 엔진별 필수 변수 주석 명시

#### 🟢 중기 (6~7일) — 오픈소스 배포 완성

7. **버전 태그 자동화**
   - `pyproject.toml` version + git tag 동기화
   - `dynamic = ["version"]` + `setuptools-scm` 채택 검토

8. **README 오픈소스 버전 개편**
   - 원클릭 설치 배지(badge) + 빠른 시작 섹션
   - 3엔진 선택 가이드

9. **Homebrew Formula 초안 작성**
   - GitHub Releases 바이너리 배포 이후 `homebrew-tap` 레포 운영

### 4-3. 실현 가능성 평가 요약

```
PyPI 배포 ───────────────────────── 즉시 가능 (pyproject.toml 완성됨)
GHCR Docker 배포 ─────────────────── 워크플로우 작성 후 즉시 가능
원클릭 curl 설치 ─────────────────── scripts/setup.sh 강화 필요 (1~2일)
Homebrew Tap ─────────────────────── GitHub Releases 구성 후 가능 (1주)
pip install telegram-ai-org ──────── PyPI 계정 + Trusted Publishing 설정 후 가능
```

---

## 참고 출처

| 영역 | 출처 |
|------|------|
| PEP 517 | [peps.python.org/pep-0517](https://peps.python.org/pep-0517/) |
| PEP 518 | [peps.python.org/pep-0518](https://peps.python.org/pep-0518/) |
| pyproject.toml 가이드 | [packaging.python.org/writing-pyproject-toml](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/) |
| setuptools pyproject.toml | [setuptools.pypa.io](https://setuptools.pypa.io/en/latest/userguide/pyproject_config.html) |
| Build system 채택률 | [labs.quansight.org](https://labs.quansight.org/blog/pep-517-build-system-popularity) |
| Docker 빌드 BP | [docs.docker.com/build/building/best-practices](https://docs.docker.com/build/building/best-practices/) |
| Docker multi-stage | [docs.docker.com/build/building/multi-stage](https://docs.docker.com/build/building/multi-stage/) |
| PyPI GitHub Actions | [packaging.python.org/github-actions](https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/) |
| pypa/gh-action-pypi-publish | [github.com/pypa/gh-action-pypi-publish](https://github.com/pypa/gh-action-pypi-publish) |
| claude-code 설치 | [code.claude.com/docs/en/setup](https://code.claude.com/docs/en/setup) |
| claude-code Homebrew | [formulae.brew.sh/cask/claude-code](https://formulae.brew.sh/cask/claude-code) |
| codex npm | [npmjs.com/@openai/codex](https://www.npmjs.com/package/@openai/codex) |
| codex GitHub | [github.com/openai/codex](https://github.com/openai/codex) |
| gemini-cli npm | [npmjs.com/@google/gemini-cli](https://www.npmjs.com/package/@google/gemini-cli) |
| gemini-cli GitHub | [github.com/google-gemini/gemini-cli](https://github.com/google-gemini/gemini-cli) |
| gemini-cli Homebrew | [formulae.brew.sh/formula/gemini-cli](https://formulae.brew.sh/formula/gemini-cli) |
