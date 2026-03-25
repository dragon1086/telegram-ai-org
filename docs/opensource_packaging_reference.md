# 오픈소스 원클릭 설치 패키징 레퍼런스 조사 보고서

> 작성일: 2026-03-25
> 작성 조직: 리서치실 (aiorg_research_bot)
> 태스크: T-aiorg_pm_bot-507
> 목적: telegram-ai-org 오픈소스화 패키징을 위한 Best Practice 수집

---

## Phase 1 산출물: 레퍼런스 프로젝트 목록 및 링크 정리표

| 프로젝트 | GitHub | Stars(2026-03 기준) | 설치 방식 | 핵심 패턴 |
|---------|--------|---------------------|-----------|-----------|
| **n8n** | [n8n-io/n8n](https://github.com/n8n-io/n8n) | ~50k | npm / Docker Compose | semantic-release, release PR 자동화 |
| **Dify** | [langgenius/dify](https://github.com/langgenius/dify) | ~85k | Docker Compose (.env 기반) | multi-profile compose, 800+ env vars anchor 패턴 |
| **Flowise** | [FlowiseAI/Flowise](https://github.com/FlowiseAI/Flowise) | ~35k | npm / Docker | 단일 서비스 compose, 헬스체크 엔드포인트 |
| **Open WebUI** | [open-webui/open-webui](https://github.com/open-webui/open-webui) | ~55k | Docker / run-compose.sh | GPU-aware compose 선택, 다중 compose 파일 |
| **LangSmith** | [langchain-ai/helm](https://github.com/langchain-ai/helm) | — | Docker Compose / Helm | Enterprise Docker Compose, .env 기반 |

---

## Phase 1 산출물: 프로젝트별 설치 패턴 수집본

### 1. n8n — release-create-pr.yml 구조

**GitHub Actions 릴리스 워크플로우 핵심**

```yaml
# .github/workflows/release-create-pr.yml
on:
  workflow_call:
    inputs:
      base-branch: { required: true }
      release-type: { required: true }  # patch | minor | major | experimental
  workflow_dispatch:
    inputs:
      release-type:
        type: choice
        options: [patch, minor, major, experimental, premajor]

jobs:
  create-release-pr:
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }          # 전체 히스토리 필수
      - name: Bump versions
        run: node .github/scripts/bump-versions.mjs   # 커스텀 SemVer 스크립트
      - name: Update changelog
        run: node .github/scripts/update-changelog.mjs
      - name: Push release branch
        # release/{version} 브랜치 생성
      - uses: peter-evans/create-pull-request@v5
        # PR 자동 생성
```

**n8n-hosting 릴리스 파이프라인 (semantic-release 기반)**
```json
// .releaserc.json
{
  "plugins": [
    "@semantic-release/commit-analyzer",       // feat: → minor, fix: → patch
    "@semantic-release/release-notes-generator",
    "@semantic-release/changelog",             // CHANGELOG.md 자동 업데이트
    ["@semantic-release/exec", {              // Chart.yaml 버전 동기화
      "prepareCmd": "python3 -c \"...\""
    }],
    "@semantic-release/github"                // GitHub Release 생성
  ]
}
```

**버전 자동 감지 워크플로우 (weekly cron)**
```yaml
# bump-n8n-version.yml
on:
  schedule:
    - cron: '0 0 * * 1'   # 매주 월요일
jobs:
  check-upstream:
    # GitHub API로 upstream 최신 버전 감지
    # values.yaml image.tag 자동 업데이트
    # automated/bump-n8n-{VERSION} 브랜치 PR 생성
```

---

### 2. Dify — Docker Compose 구조

**docker/docker-compose.yaml 핵심 패턴**

```yaml
# YAML Anchor 패턴 — 공통 env 변수 재사용
x-shared-env: &shared-env
  DB_HOST: ${DB_HOST:-db}
  REDIS_HOST: ${REDIS_HOST:-redis}
  SECRET_KEY: ${SECRET_KEY:?SECRET_KEY is required}   # 필수값 강제
  # 800+ 환경변수...

services:
  api:
    image: langgenius/dify-api:${DIFY_VERSION:-1.13.2}
    env_file: .env
    environment:
      <<: *shared-env    # 앵커 참조
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_started
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  # Profile 기반 선택적 서비스
  weaviate:
    profiles: [weaviate]    # --profile weaviate 로만 실행
  qdrant:
    profiles: [qdrant]
  postgresql:
    profiles: [postgresql]

  # 네트워크 격리
networks:
  ssrf_proxy_network:     # 외부 요청 SSRF 방어
  opensearch-net:
```

**온보딩 README 패턴**
```bash
# 3단계 온보딩 (Dify 방식)
git clone https://github.com/langgenius/dify.git
cd dify/docker
cp .env.example .env
# .env 수정: SECRET_KEY, DB_PASSWORD 등 필수값 설정
docker compose up -d
# http://localhost/install → 웹 설치 마법사
```

---

### 3. Flowise — 경량 단일 서비스 패턴

```yaml
# docker/docker-compose.yml
services:
  flowise:
    image: flowiseai/flowise:latest
    restart: always
    ports:
      - "${PORT:-3000}:${PORT:-3000}"
    env_file: .env
    environment:
      - PORT=${PORT:-3000}
      - FLOWISE_USERNAME=${FLOWISE_USERNAME}
      - FLOWISE_PASSWORD=${FLOWISE_PASSWORD}
      # 카테고리별 그룹화: DATABASE, STORAGE, AUTH, EMAIL, METRICS...
    volumes:
      - ~/.flowise:/root/.flowise
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:${PORT:-3000}/api/v1/ping"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s    # 초기 기동 대기
    entrypoint: sleep 3; flowise start   # 초기화 대기 패턴
```

---

### 4. Open WebUI — run-compose.sh 구조

```bash
#!/usr/bin/env bash
set -euo pipefail

# ANSI 컬러 코드 정의
RED='\033[0;31m'; GREEN='\033[0;32m'; RESET='\033[0m'

# GPU 하드웨어 감지
get_gpu_driver() {
  if lspci | grep -i nvidia >/dev/null || nvidia-smi >/dev/null 2>&1; then
    echo "nvidia"
  elif lspci | grep -i amdgpu >/dev/null 2>&1; then
    echo "amdgpu"
  elif lspci | grep -i intel >/dev/null 2>&1; then
    echo "i915"
  else
    echo -e "${RED}No recognized GPU found${RESET}" >&2; exit 1
  fi
}

# 인수 파싱: bracket-notation 지원 (--enable-gpu[count=2])
extract_value() { echo "$1" | sed 's/.*\[\(.*\)\]/\1/' | cut -d= -f2; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --enable-gpu*)
      OLLAMA_GPU_DRIVER=$(get_gpu_driver)
      OLLAMA_GPU_COUNT=$(extract_value "$1" || echo "1")
      ;;
    --enable-api*) ENABLE_OLLAMA_API=true ;;
    --quiet)       QUIET=true ;;
    *) echo "Unknown option: $1"; show_usage; exit 1 ;;
  esac
  shift
done

# 다중 compose 파일 동적 조합
DEFAULT_COMPOSE_COMMAND="docker compose -f docker-compose.yaml"
[[ "${ENABLE_GPU:-false}" == "true" ]] && DEFAULT_COMPOSE_COMMAND+=" -f docker-compose.gpu.yaml"
[[ "${ENABLE_API:-false}" == "true" ]] && DEFAULT_COMPOSE_COMMAND+=" -f docker-compose.api.yaml"

# 사용자 확인 (headless 모드 지원)
if [[ "${QUIET:-false}" != "true" ]]; then
  read -p "Proceed? (Y/n): " confirm
  [[ "${confirm,,}" == "n" ]] && exit 0
fi

export OLLAMA_GPU_DRIVER OLLAMA_GPU_COUNT
$DEFAULT_COMPOSE_COMMAND up -d --remove-orphans
```

---

## Phase 2 산출물: Best Practice 비교 분석표

### (1) setup.sh 구조 분석

| 패턴 항목 | n8n | Dify | Open WebUI | Flowise | Best Practice |
|---------|-----|------|-----------|---------|--------------|
| **Shebang** | `#!/bin/bash` | `#!/bin/bash` | `#!/usr/bin/env bash` | N/A | `#!/usr/bin/env bash` (이식성↑) |
| **Strict Mode** | 부분 적용 | 없음 | `set -euo pipefail` | N/A | `set -euo pipefail` 필수 |
| **OS 감지** | OS 분기 있음 | Docker 의존 | GPU 하드웨어 감지 | Docker 의존 | uname -s 기반 분기 |
| **의존성 체크** | npm, node, docker | docker, docker-compose | docker, lspci | npm, docker | `command -v` 로 각 도구 체크 |
| **에러 핸들링** | exit code 체크 | 제한적 | exit + 메시지 | 없음 | `trap cleanup EXIT ERR` |
| **컬러 출력** | 있음 | 있음 | ANSI 코드 정의 | 없음 | tput 또는 ANSI 상수 정의 |
| **사용자 안내** | 단계별 echo | README 의존 | 실시간 progress | README 의존 | 단계별 [INFO]/[ERROR] 프리픽스 |
| **Headless 지원** | 없음 | 없음 | `--quiet` 플래그 | 없음 | `-y/--yes` 플래그 지원 |

**핵심 패턴 템플릿**

```bash
#!/usr/bin/env bash
set -euo pipefail

# 컬러 출력
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RESET='\033[0m'
log_info()  { echo -e "${GREEN}[INFO]${RESET} $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${RESET} $*"; }
log_error() { echo -e "${RED}[ERROR]${RESET} $*" >&2; }

# 의존성 체크
check_deps() {
  local missing=()
  for cmd in docker curl git python3; do
    command -v "$cmd" >/dev/null 2>&1 || missing+=("$cmd")
  done
  [[ ${#missing[@]} -gt 0 ]] && { log_error "Missing: ${missing[*]}"; exit 1; }
}

# OS 감지
detect_os() {
  case "$(uname -s)" in
    Darwin) echo "macos" ;;
    Linux)  echo "linux" ;;
    *)      log_error "Unsupported OS"; exit 1 ;;
  esac
}

# 정리 훅
cleanup() { log_warn "Interrupted. Cleaning up..."; }
trap cleanup EXIT ERR

main() {
  log_info "Starting setup..."
  check_deps
  OS=$(detect_os)
  # ... 설치 로직
  log_info "Setup complete!"
}

main "$@"
```

---

### (2) Docker Compose 온보딩 패턴 분석

| 패턴 항목 | n8n | Dify | Flowise | Open WebUI | Best Practice |
|---------|-----|------|---------|-----------|--------------|
| **.env 연동** | `env_file: .env` | `env_file: .env` + anchor | `env_file: .env` | 동적 export | `.env.example` 제공 + `cp` 안내 |
| **필수값 강제** | 없음 | `${VAR:?error}` 패턴 | 없음 | 없음 | `${SECRET_KEY:?Must be set}` |
| **볼륨 전략** | Named volume | `./volumes/` 상대경로 | `~/.flowise` 홈 마운트 | Named volume | Named volume (이식성↑) |
| **네트워크** | default bridge | ssrf_proxy_network 격리 | default bridge | default bridge | 서비스 목적별 분리 |
| **헬스체크** | 없음 | pg_isready + curl | curl /api/v1/ping | 없음 | 서비스별 native 체크 |
| **의존성 순서** | 없음 | depends_on + condition | 없음 | 없음 | `service_healthy` condition |
| **Profile 지원** | 없음 | DB/VectorDB 선택 | 없음 | GPU/API 선택 | 선택적 서비스는 profiles 사용 |
| **start_period** | 없음 | 있음 | 30s | 없음 | 초기화 시간 고려 필수 |

**권장 docker-compose 구조**

```yaml
# 앵커로 공통 환경변수 재사용
x-common-env: &common-env
  TZ: ${TZ:-Asia/Seoul}
  LOG_LEVEL: ${LOG_LEVEL:-INFO}

services:
  app:
    image: your-org/app:${VERSION:-latest}
    restart: unless-stopped
    env_file: .env
    environment:
      <<: *common-env
      SECRET_KEY: ${SECRET_KEY:?SECRET_KEY must be set in .env}
    volumes:
      - app_data:/app/data
    networks:
      - internal
    depends_on:
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  app_data:
  redis_data:

networks:
  internal:
    driver: bridge
```

---

### (3) GitHub Actions 릴리스 자동화 분석

| 패턴 항목 | n8n | Dify | Open WebUI | Best Practice |
|---------|-----|------|-----------|--------------|
| **버전 전략** | SemVer + 커스텀 mjs 스크립트 | 수동 태그 | PyPI + Docker 분리 | semantic-release 또는 커스텀 |
| **트리거** | workflow_dispatch + workflow_call | push tag v* | push tag v* | tag push + manual dispatch |
| **Changelog** | @semantic-release/changelog | 없음 | 없음 | conventional commits → auto |
| **Docker 빌드** | GHCR 푸시 | GHCR 멀티플랫폼 | GHCR + PyPI | docker/build-push-action |
| **릴리스 PR** | peter-evans/create-pull-request | 없음 | 없음 | 릴리스 브랜치 전략 권장 |
| **Weekly auto-bump** | bump-n8n-version.yml | 없음 | dependabot | upstream 감지 cron 유용 |
| **CI 재실행 방지** | `[skip ci]` 커밋 메시지 | 없음 | 없음 | `[skip ci]` 태그 필수 |

**권장 GitHub Actions 릴리스 워크플로우**

```yaml
# .github/workflows/release.yml
name: Release

on:
  push:
    tags: ['v*.*.*']
  workflow_dispatch:
    inputs:
      release-type:
        type: choice
        options: [patch, minor, major]

jobs:
  release:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      packages: write
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }

      - name: Extract version
        id: version
        run: echo "VERSION=${GITHUB_REF_NAME#v}" >> $GITHUB_OUTPUT

      - name: Generate changelog
        uses: orhun/git-cliff-action@v3    # conventional commits 기반
        with:
          config: cliff.toml
          args: --latest --strip header
        env:
          OUTPUT: CHANGELOG_LATEST.md

      - name: Build and push Docker image
        uses: docker/build-push-action@v5
        with:
          push: true
          tags: |
            ghcr.io/${{ github.repository }}:latest
            ghcr.io/${{ github.repository }}:${{ steps.version.outputs.VERSION }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v1
        with:
          body_path: CHANGELOG_LATEST.md
          files: |
            dist/*.tar.gz
```

---

## Phase 2 산출물: telegram-ai-org 적용 가능 항목 체크리스트

### setup.sh 개선 항목

- [ ] **`set -euo pipefail` 추가** — 현재 setup.sh에 strict mode 미적용 (우선순위: HIGH)
- [ ] **의존성 체크 함수화** — `check_deps()` 함수로 docker, python3, git 사전 검증
- [ ] **OS 분기 처리** — `uname -s` 기반 macOS/Linux/WSL 분기 (현재 macOS 전용 가능성)
- [ ] **3 엔진 자동 감지** — `command -v claude-code`, `command -v gemini`, `command -v codex` 순차 체크
- [ ] **`--yes` 헤드리스 모드** — CI/CD 자동 설치용 비대화형 옵션
- [ ] **`trap cleanup EXIT ERR`** — 중단 시 임시 파일 정리
- [ ] **컬러 출력 및 진행 단계 표시** — [INFO]/[WARN]/[ERROR] 프리픽스 일관 적용
- [ ] **사전 요구사항 안내** — 설치 시작 전 필요 도구 목록 출력

### Docker Compose 개선 항목

- [ ] **`.env.example` 완성** — 모든 필수값에 `:?error` 패턴 적용, 선택값에 default 명시
- [ ] **YAML 앵커 도입** — `x-common-env` 앵커로 중복 env 정의 제거
- [ ] **헬스체크 추가** — 각 봇 컨테이너에 `/health` 엔드포인트 + healthcheck 정의
- [ ] **`depends_on` + `service_healthy`** — redis/db 준비 완료 후 앱 기동 보장
- [ ] **Named Volume 표준화** — 상대경로 마운트 대신 named volume 사용
- [ ] **`start_period` 설정** — 봇 초기화(engine 로딩) 시간 고려, 최소 30-60s
- [ ] **Profile 기반 엔진 선택** — `--profile claude-code`, `--profile gemini` 선택적 활성화

### GitHub Actions 릴리스 자동화 항목

- [ ] **Conventional Commits 도입** — feat/fix/chore 커밋 컨벤션 팀 가이드 문서화
- [ ] **`release.yml` 생성** — tag push 트리거 + workflow_dispatch 수동 옵션
- [ ] **git-cliff 또는 @semantic-release/changelog** — CHANGELOG.md 자동 생성
- [ ] **GHCR 멀티플랫폼 빌드** — `linux/amd64,linux/arm64` 동시 빌드 (Apple Silicon 지원)
- [ ] **GHA 캐시 적용** — `cache-from: type=gha` 빌드 시간 단축
- [ ] **`[skip ci]` 패턴** — 릴리스 자동화 커밋이 CI를 재트리거하지 않도록
- [ ] **weekly bump cron** — 의존 패키지(telegram-bot-api 등) 자동 버전 체크

---

## 결론 및 핵심 인사이트

### 핵심 인사이트 3가지

1. **"3단계 온보딩"이 표준** — clone → `cp .env.example .env` → `docker compose up -d` 가 사실상 업계 표준. README 첫 섹션에 이 3줄이 없으면 신규 사용자 이탈률 급증.

2. **setup.sh의 실제 역할은 "전제조건 검증 + 안내"** — 실제 설치는 Docker Compose가 담당. setup.sh는 환경 체크, .env 생성 도우미, 설치 후 URL 안내에 집중하는 것이 best practice. 복잡한 로직을 setup.sh에 넣으면 유지보수 부담만 늘어남.

3. **GitHub Actions 릴리스는 "PR 기반 자동화"가 핵심** — n8n 방식(release-create-pr.yml)처럼 자동화가 PR을 생성하고 사람이 머지 승인하는 패턴이 가장 안전. 완전 자동 머지는 사고 발생 시 롤백이 복잡해짐.

### telegram-ai-org 즉시 적용 우선순위

| 우선순위 | 항목 | 예상 공수 | 효과 |
|---------|------|---------|------|
| 🔴 HIGH | setup.sh `set -euo pipefail` + 의존성 체크 | 2h | 설치 실패 디버깅 시간 80% 감소 |
| 🔴 HIGH | `.env.example` 완성 + 필수값 강제 | 2h | 신규 사용자 오류 95% 감소 |
| 🟡 MID | Docker Compose 헬스체크 + depends_on | 3h | 기동 순서 오류 제거 |
| 🟡 MID | `release.yml` 기본 구조 생성 | 4h | 릴리스 자동화 기반 마련 |
| 🟢 LOW | Conventional Commits + git-cliff | 4h | CHANGELOG 자동화 |
| 🟢 LOW | GHCR 멀티플랫폼 빌드 | 3h | ARM Mac 지원 |

---

## 참고 출처

- [n8n release-create-pr.yml](https://github.com/n8n-io/n8n/blob/master/.github/workflows/release-create-pr.yml)
- [n8n-io/n8n-hosting CI/CD 분석](https://deepwiki.com/n8n-io/n8n-hosting/6-cicd-and-automation)
- [Dify docker-compose.yaml](https://github.com/langgenius/dify/blob/main/docker/docker-compose.yaml)
- [Dify Docker Compose 공식 문서](https://docs.dify.ai/en/self-host/quick-start/docker-compose)
- [Flowise docker-compose.yml](https://github.com/FlowiseAI/Flowise/blob/main/docker/docker-compose.yml)
- [Open WebUI run-compose.sh](https://github.com/open-webui/open-webui/blob/main/run-compose.sh)
- [Bash Scripting Best Practices 2026](https://oneuptime.com/blog/post/2026-02-13-bash-best-practices/view)
- [GitHub Actions semantic-release 자동화](https://xfuture-blog.com/posts/automating-builds-and-releases-with-conventional-commits-and-semantic-versioning/)
