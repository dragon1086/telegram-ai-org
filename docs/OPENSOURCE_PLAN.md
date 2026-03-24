# OPENSOURCE_PLAN.md — telegram-ai-org 오픈소스화 마스터 플랜

> **미션**: telegram-ai-org를 오픈소스로 공개하고, 일반인이 원클릭으로 풀셋팅 후 체험할 수 있는 서비스로 패키징한다.
> **기간**: 2026-03-24 ~ 2026-03-31 (7일)
> **3대 엔진**: Claude Code / Codex / Gemini CLI 모두 정상 호환

---

## 목표 정의 (OKR)

### Objective
> **"누구나 10분 안에 자신만의 AI 조직을 텔레그램에서 운영할 수 있게 한다"**

### Key Results
| KR | 측정 기준 | 완료 기준 | 현황 |
|----|-----------|-----------|------|
| KR1: 원클릭 설치 | `./setup.sh` 또는 `docker compose up` 한 번에 전체 시스템 기동 | 첫 실행 ~ 봇 응답까지 10분 이내 | 🔲 |
| KR2: 3엔진 호환 | Claude Code / Codex / Gemini CLI 각각 단독으로 전체 플로우 작동 | E2E 테스트 3개 엔진 모두 통과 | 🔲 |
| KR3: 오픈소스 패키지 | GitHub public repo, README, 라이선스, 기여 가이드 | README star 기반 문서화 완성 | 🔲 |
| KR4: E2E 회귀 테스트 | 핵심 플로우 100% 자동화 테스트 | `pytest tests/e2e/` 그린 | 🔲 |
| KR5: 설정 없이 작동 | `.env.example`만 채우면 바로 작동 | 새 환경 첫 실행 성공률 > 95% | 🔲 |

---

## 7일 스프린트 계획

### Day 1-2 (2026-03-24~25): 기반 준비
- [x] 마스터 플랜 수립 (이 문서)
- [ ] 조직별 엔진 최적화 (organizations.yaml + bots/*.yaml)
- [ ] AGENTS.md / GEMINI.md 동기화
- [ ] GeminiCLIRunner 검증 및 .env 설정 보강
- [ ] Skills/MCP 표준 구조 문서화
- [ ] E2E 회귀 테스트 스킬 생성

### Day 3-4 (2026-03-26~27): 패키징 & 테스트
- [ ] 원클릭 설치 스크립트 개선 (`scripts/setup.sh` → 3엔진 자동 감지)
- [ ] `.env.example` 완성 (모든 필수 키 문서화)
- [ ] Docker Compose 지원 (선택 엔진별 프로파일)
- [ ] E2E 테스트 스위트 구현
- [ ] Gemini 이미지 생성 스킬 구현

### Day 5-6 (2026-03-28~29): 오픈소스 문서화
- [ ] README.md 오픈소스 버전으로 전면 개편
- [ ] CONTRIBUTING.md (기여 가이드)
- [ ] 라이선스 파일 (MIT 또는 Apache 2.0)
- [ ] 코드베이스 리팩토링 Phase 1 (핵심 모듈 응집도 개선)
- [ ] 보안 감사 (토큰, 시크릿 노출 방지)

### Day 7 (2026-03-31): 출시 준비
- [x] GitHub Actions CI/CD 설정
- [x] 전체 E2E 테스트 통과 확인
- [ ] 최종 harness-audit 실행
- [ ] v1.0.0 태그 생성 및 GitHub public 릴리스

---

## CI/CD

현재 오픈소스 배포 파이프라인은 세 단계로 분리된다.

| 순서 | 워크플로우 | 트리거 | 필요 secret | 산출물 |
|------|------|------|------|------|
| 1 | `e2e-test.yml` | `push`, `pull_request`, `workflow_dispatch` | `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_OAUTH_CREDS` | 3엔진 호환 E2E 결과 |
| 2 | `publish-pypi.yml` | `push` to `main`, tags `v*`, `workflow_dispatch` | `PYPI_API_TOKEN` | PyPI sdist/wheel 배포 |
| 3 | `docker-build-push.yml` | `push` to `main`, tags `v*`, `workflow_dispatch` | `DOCKER_USERNAME`, `DOCKER_PASSWORD` | `claude`, `codex`, `gemini` Docker 이미지 푸시 |

운영 원칙:

- 배포 전 항상 테스트: `e2e-test.yml`을 branch protection required check로 묶어 `main` 머지 전에 통과시킨다.
- 인프라 변경은 단계적으로: Docker 이미지는 엔진별(`claude`, `codex`, `gemini`)로 분리해 개별 롤백 가능하게 유지한다.
- PyPI 배포는 `python -m build`와 `twine check dist/*`를 통과한 뒤에만 진행한다.
- Gemini CI credential은 API key가 아니라 OAuth JSON secret(`GEMINI_OAUTH_CREDS`)로 관리한다.

---

## 조직별 엔진 배정 (최적화 기준)

| 조직 | 역할 | 엔진 | 근거 |
|------|------|------|------|
| PM (aiorg_pm_bot) | 오케스트레이션/조율 | **claude-code** | 복잡한 멀티스텝 추론, 긴 컨텍스트, 팀 조율 |
| 개발실 (aiorg_engineering_bot) | 코드 구현/버그수정 | **claude-code** | 복잡한 코드 아키텍처, 디버깅, 테스트 작성 |
| 디자인실 (aiorg_design_bot) | UI/UX 디자인 | **claude-code** | 크리에이티브 태스크, 마크다운 산출물 품질 |
| 기획실 (aiorg_product_bot) | PRD/요구사항 | **claude-code** | 장문 PRD, 요구사항 분석, 구조화된 문서 |
| 성장실 (aiorg_growth_bot) | 마케팅/지표분석 | **gemini-cli** | Google 검색 내장, 최신 시장 데이터, 대규모 컨텍스트 |
| 리서치실 (aiorg_research_bot) | 조사/경쟁사분석 | **gemini-cli** | 실시간 웹 검색, 문서 요약, 멀티소스 비교 |
| 운영실 (aiorg_ops_bot) | 배포/인프라 | **codex** | CLI 스크립트 특화, 경량, DevOps 자동화 |

---

## 성공 측정 기준 (Definition of Done)

### 각 태스크 완료 기준
- [ ] 단위 테스트 통과 (`pytest -q`)
- [ ] E2E 테스트 통과 (`/e2e-regression`)
- [ ] 문서 업데이트 (CLAUDE.md / AGENTS.md / GEMINI.md 중 해당)
- [ ] harness-audit 통과

### 전체 프로젝트 완료 기준
- [ ] `./scripts/setup.sh` 실행 → 10분 내 전체 봇 기동
- [ ] 3엔진 각각 `pytest tests/e2e/` 통과
- [ ] GitHub public repo 접근 가능
- [ ] README.md에서 5분 만에 시작 가능
- [ ] 보안: `.env` 파일이 `.gitignore`에 포함, 시크릿 노출 없음

---

## 진척 관리 원칙

### 자율 진행 원칙 (인간 개입 최소화)
1. **PM이 이 문서를 기준 나침반으로 삼는다** — 세션 시작 시 항상 읽는다
2. **체크박스 즉시 업데이트** — 완료된 항목은 [x]로 변경
3. **stuck 발생 시**: `tasks/stuck_log.md`에 기록 후 다음 태스크로 진행
4. **세션 끊김 대비**: 각 작업 완료 후 git commit — "세션이 끊겨도 커밋 로그로 이어받기"
5. **주간 회고**: 금요일 `weekly-review` 스킬로 자동 실행

### 회사 시스템 연동
- **주간 회의**: 매주 금요일 → `skills/weekly-review` 자동 실행 → 이 문서의 KR 업데이트
- **회고**: 스프린트 끝 → `skills/retro` 실행 → 장애물 & 개선 사항 문서화
- **성과 평가**: 월말 → `skills/performance-eval` 실행 → KR 달성률 기반 평가

---

## 기술 스택 & 패키지 요구사항

### 필수 환경
```bash
# Python 3.11+
python --version

# Node.js 18+ (Gemini CLI용)
node --version

# Claude Code CLI
claude --version

# Codex CLI
codex --version

# Gemini CLI
gemini --version
```

### 설치 경로 (현재 설정)
```bash
CLAUDE_CLI_PATH=/Users/rocky/.local/bin/claude
CODEX_CLI_PATH=/opt/homebrew/bin/codex
GEMINI_CLI_PATH=/opt/homebrew/bin/gemini  # 신규 추가
```

---

## 리스크 & 대응

| 리스크 | 확률 | 영향 | 대응 |
|--------|------|------|------|
| Gemini CLI 인증 이슈 | 중 | 중 | `gemini auth login` 가이드 + fallback to gemini API |
| 봇 토큰 노출 | 저 | 고 | `.env` gitignore 철저, `.env.example`로 구조만 공개 |
| 3엔진 호환성 갭 | 중 | 중 | E2E 테스트로 조기 발견, 엔진별 fallback 설정 |
| 세션 중단 | 고 | 중 | 커밋 기반 체크포인트, 이 문서가 재개 포인트 |
| 테스트 커버리지 부족 | 중 | 중 | E2E 회귀 스킬로 핵심 플로우 우선 커버 |

---

## 연관 문서

- `CLAUDE.md` — Claude Code 운영 지침
- `AGENTS.md` — Codex CLI 운영 지침
- `GEMINI.md` — Gemini CLI 운영 지침 (신규)
- `docs/SKILLS_MCP_GUIDE.md` — Skills/MCP 표준 구조 (신규)
- `ROADMAP.md` — 장기 기술 로드맵
- `ARCHITECTURE.md` — 시스템 아키텍처
- `tasks/stuck_log.md` — 블로킹 이슈 로그

---

*최종 업데이트: 2026-03-24 | PM: aiorg_pm_bot*
