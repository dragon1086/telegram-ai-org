# PRD: AIMesh README 전면 개편 + 브랜딩 리뉴얼

**Version**: 1.0
**Date**: 2026-04-01
**Author**: 기획실 (aiorg_product_bot)
**Status**: Draft → 실행 위임 대기

---

## 1. 배경 및 목적

현행 README는 "NanoBunny" 토끼 마스코트를 사용 중이나, 프로젝트 별칭 **AIMesh**(다중 AI 융합 조직)와 브랜드 정체성이 불일치한다. Mermaid 다이어그램은 플러그인 미설치 환경에서 텍스트로 표시되며, 프로젝트 구조·엔진 구성·연도 등 사실과 다른 내용이 다수 존재한다.

**목표**: AIMesh 브랜드에 맞는 로고·비주얼로 전환하고, README 전 섹션을 현실에 맞게 개편한다.

---

## 2. 토끼 마스코트 제거 대상 목록

| 위치 | 현재 코드 | 조치 |
|------|----------|------|
| README.md L3 | `<img src="assets/mascot/mascot_v1.png" .../>` | `assets/logo.png`로 교체 |
| README.md L2 | `<!-- TODO: SVG 로고 완성 후 ... -->` 코멘트 | 삭제 |
| assets/ASSET_GUIDE.md §1 | NanoBunny mascot 전체 섹션 | AIMesh 로고 섹션으로 교체 |
| assets/ASSET_GUIDE.md §Color | Mint/Coral NanoBunny 컬러 | AIMesh 컬러 팔레트로 교체 |
| assets/mascot/ | mascot_v1.png, mascot_wave_v1.png, mascot_think_v1.png | 유지(레거시)하되 README 참조 제거 |

---

## 3. AIMesh 브랜드 아이덴티티

| 항목 | 정의 |
|------|------|
| **별칭** | AIMesh |
| **의미** | 여러 AI가 조직으로서 융합 (AI + Mesh Network) |
| **키워드** | 다중 AI 노드, 메시 네트워크, 조직적 협업, 자율 위임, 융합 |
| **비주얼 방향** | 복수 노드가 메시 형태로 연결된 추상적·미니멀 로고 |
| **금지 요소** | 동물 캐릭터(토끼 등), 과도한 장식, 사실적 인물 |
| **컬러 팔레트 제안** | Indigo (#4F46E5, 주색), Emerald (#059669, 보조), Slate (#374151, 배경), White (#FFFFFF) |

---

## 4. 이미지 생성 모델 제약사항 정리

| 항목 | 값 |
|------|-----|
| **모델** | `gemini-3.1-flash-image-preview` |
| **상태** | Preview (프로덕션 주의) |
| **호출 방식** | 1순위 gemini CLI (OAuth), 2순위 Google GenAI API |
| **출력 포맷** | PNG |
| **해상도** | 1024×1024 기본 (최소 512×512) |
| **파일 크기 제한** | < 10MB (텔레그램 전송 호환) |
| **러너** | `tools/gemini_image_runner.py` → `GeminiImageRunner` |

---

## 5. 작업 항목 상세 스펙 (8개 + 1)

### WI-01: AIMesh 로고 생성 및 교체

**산출물**: `assets/logo.png`

**로고 생성 프롬프트 후보** (Gemini 3.1 Flash Image Preview):

| # | 프롬프트 | 스타일 |
|---|---------|--------|
| P1 | "Minimalist logo for 'AIMesh' — an AI organization platform. Abstract mesh network of 6-7 connected nodes forming a brain-like pattern. Indigo (#4F46E5) primary, emerald (#059669) accent. Clean white background. Modern tech aesthetic, flat design, no text." | Flat |
| P2 | "Modern gradient logo: interconnected AI nodes in a hexagonal mesh pattern, representing multiple AI agents collaborating as one organization. Deep indigo to emerald gradient. Transparent background, 1024x1024, vector-style." | Gradient |
| P3 | "Abstract technology logo: organic mesh network where each node is a subtle AI brain icon, all connected by flowing lines. Dark slate background (#1A1A2E), glowing indigo (#4F46E5) nodes, emerald (#059669) connection lines. Futuristic, minimal." | Dark/Glow |
| P4 | "Logo concept: 6 geometric shapes (circle, hexagon, triangle, square, pentagon, diamond) connected by thin lines in a mesh topology. Each shape represents a different AI department. Flat design, indigo palette, white background, no text, clean." | Geometric |
| P5 | "Professional SaaS logo: neural mesh network of 7 nodes, each node slightly different size representing hierarchy (1 large orchestrator + 6 specialists). Smooth gradients, indigo-emerald color scheme. Minimalist, suitable for GitHub README header." | SaaS |

**README 교체 스펙**:
```markdown
<!-- 삭제 -->
<!-- TODO: SVG 로고 완성 후 assets/logo/logo.svg 로 교체하세요 -->
<img src="assets/mascot/mascot_v1.png" alt="telegram-ai-org" width="140"/>

<!-- 교체 -->
<img src="assets/logo.png" alt="AIMesh Logo" width="180"/>
```

**파일 규격**:
- 경로: `assets/logo.png`
- 해상도: 1024×1024 (README 표시 시 width="180")
- 배경: 투명 또는 흰색
- 파일 크기: < 1MB

---

### WI-02: "이게 뭔가요?" 섹션 이미지 추가

**목적**: 30초 설명 텍스트 하단에 시각적 플로우 이미지 첨부

**이미지 프롬프트 제안**:
> "Infographic showing a user sending a message to a Telegram chat, which triggers a PM bot that routes the request to specialized AI department bots (Engineering, Design, Planning, Growth, Research, Ops). Clean flat illustration, indigo-emerald color scheme, left-to-right flow, numbered steps 1→2→3→4."

**삽입 위치**: README L47 (설치에서 첫 응답까지 5분) 직전
```markdown
<p align="center">
  <img src="assets/diagrams/aimesh_overview.png" alt="AIMesh 동작 흐름" width="700"/>
</p>
```

**산출물**: `assets/diagrams/aimesh_overview.png`

---

### WI-03: "주요 기능" 섹션 이미지 추가

시각화 가능한 기능 4개를 선별하여 소형 이미지 첨부:

| 기능 | 이미지 프롬프트 | 파일명 |
|------|---------------|--------|
| 스마트 라우팅 | "Diagram: a central brain node receiving a message and routing it to 3 different department icons. Flat, minimal, indigo palette." | `assets/diagrams/feat_routing.png` |
| 멀티봇 협업 | "6 colored circles connected by lines, each labeled with an icon (code, paint, chart, search, gear, clipboard). Teamwork visualization, flat design." | `assets/diagrams/feat_collab.png` |
| 3종 AI 엔진 | "3 engine icons side by side: Claude (purple), Codex (green), Gemini (blue). Connected to a central platform. Tech comparison layout." | `assets/diagrams/feat_engines.png` |
| 스킬 플러그인 | "Plugin/puzzle piece connecting to a bot icon. Modular system visualization. Flat tech illustration." | `assets/diagrams/feat_skills.png` |

**테이블 형식 변경**: 설명 컬럼에 `<br/><img src="..." width="200"/>` 삽입

---

### WI-04: Quick Start 엔진 자동 배치 + 커스텀 가이드

**현재 문제**: "AI 엔진 하나: Claude Code / Codex / Gemini CLI 중 선택" → 실제로는 `organizations.yaml`에서 부서별 엔진이 자동 배정됨

**변경 사항**:

1. **삭제**: README L72 `- AI 엔진 하나: Claude Code / Codex / Gemini CLI 중 선택`
2. **삭제**: README L98 `# AI 엔진 (하나만 설정)` 관련 코멘트
3. **추가** (준비물 섹션):
```markdown
- AI 엔진 중 하나 이상: Claude Code / Codex / Gemini CLI
  > 부서별 최적 엔진이 자동 배정됩니다. 수동 선택 불필요.
```

4. **추가** (L104 이후, 새 서브섹션):
```markdown
### 엔진 커스텀 설정 (선택)

부서별 AI 엔진은 `organizations.yaml`에서 변경할 수 있습니다:

\`\`\`yaml
# organizations.yaml — 개발실 예시
- id: aiorg_engineering_bot
  execution:
    preferred_engine: claude-code   # 주 엔진
    fallback_engine: codex          # 장애 시 대체 엔진
\`\`\`

| 설정 | 위치 | 설명 |
|------|------|------|
| 부서별 엔진 변경 | `organizations.yaml` → `execution.preferred_engine` | claude-code, codex, gemini-cli 중 선택 |
| 폴백 엔진 설정 | `organizations.yaml` → `execution.fallback_engine` | 주 엔진 장애 시 자동 전환 |
| 부서 추가/삭제 | `organizations.yaml` → `organizations` 배열 | 새 봇 정의 추가 또는 `enabled: false` |
| 조직 운영 전략 | `orchestration.yaml` | 라우팅 규칙, 글로벌 지침, 스킬 설정 |
```

---

### WI-05: 아키텍처 섹션 — Mermaid → Gemini 이미지 교체

**현재 문제**: Mermaid 코드블록은 GitHub에서만 렌더링됨. 플러그인 없는 환경(일반 마크다운 뷰어, IDE 프리뷰)에서는 텍스트로 표시.

**변경 사항**:
1. Mermaid 코드블록 전체 삭제 (README L126~L153)
2. 이미 생성된 `assets/diagrams/arch_diagram_v1.png` 활용 또는 새 이미지 생성

**이미지 프롬프트** (기존 이미지가 부적합할 경우):
> "System architecture diagram: User (top) sends message to PM Bot (center, indigo). PM Bot routes to 6 department bots arranged in a circle: Engineering, Design, Planning, Growth, Research, Ops. Engineering/Design/Planning connect to Claude Code engine (purple). Growth/Research/Ops connect to Gemini CLI engine (green). Engineering also has Codex fallback (orange dotted line). All bots connect to a shared Memory/DB at bottom. Clean tech diagram, white background, labeled arrows."

**교체 마크다운**:
```markdown
## 🏗️ 아키텍처

<p align="center">
  <img src="assets/diagrams/architecture_overview.png" alt="AIMesh Architecture" width="750"/>
</p>
```

---

### WI-06: 실시간 대시보드 — 스크린샷 업로드 가이드

**현재 상태**: `assets/screenshots/` 디렉토리 존재, `.gitkeep`만 있음

**변경 사항** — 사용자(Rocky)가 직접 스크린샷 2장 이상 올릴 예정. 가이드 제공:

```markdown
## 📊 실시간 대시보드

봇 상태, 메시지 라우팅, 응답 이력을 **한 화면**에서 확인할 수 있습니다.

<p align="center">
  <img src="assets/screenshots/dashboard_main.png" alt="대시보드 메인 화면" width="700"/>
</p>

<p align="center">
  <img src="assets/screenshots/dashboard_routing.png" alt="메시지 라우팅 뷰" width="700"/>
</p>
```

**스크린샷 업로드 가이드**:
1. 대시보드 실행: `python dashboard.py` → `http://localhost:8050` 접속
2. 브라우저에서 전체 화면 캡처 (권장 해상도: 1920×1080 이상)
3. 메인 대시보드 뷰 → `assets/screenshots/dashboard_main.png`로 저장
4. 라우팅/메시지 흐름 뷰 → `assets/screenshots/dashboard_routing.png`로 저장
5. (선택) 봇 상태 상세 뷰 → `assets/screenshots/dashboard_bots.png`
6. 파일 크기 권장: 각 500KB~2MB (너무 크면 GitHub 로딩 느림)
7. 저장 후 `git add assets/screenshots/` → 커밋

---

### WI-07: 부서별 봇 구성 — Codex 추가 + 실제 적용

**현재 문제**: README 테이블에 Codex 엔진이 없음. 실제로는 `organizations.yaml`에서 개발실 fallback으로 codex 사용 중.

**README 테이블 변경**:

```markdown
| 봇 | 역할 | 주 엔진 | 폴백 엔진 |
|----|------|---------|----------|
| 🧠 `aiorg_pm_bot` | 전체 조율, 라우팅 | Claude Code | Gemini CLI |
| 💻 `aiorg_engineering_bot` | 코드 작성, API 구현, 버그 수정 | Claude Code | **Codex** |
| 🎨 `aiorg_design_bot` | UI/UX 설계, 와이어프레임 | Claude Code | Gemini CLI |
| 📋 `aiorg_product_bot` | 기획, 요구사항 분석, PRD | Claude Code | Gemini CLI |
| 📣 `aiorg_growth_bot` | 성장 전략, 마케팅, 지표 분석 | Gemini CLI | Claude Code |
| 🔭 `aiorg_research_bot` | 시장조사, 경쟁사 분석 | Gemini CLI | Claude Code |
| ⚙️ `aiorg_ops_bot` | 배포, 인프라, 모니터링 | Gemini CLI | Claude Code |
```

**실제 프로젝트 적용**: `organizations.yaml` 확인 결과 개발실에 이미 `fallback_engine: codex` 설정 완료. README만 동기화하면 됨.

---

### WI-08: 프로젝트 구조 — 현실 반영

**현행 README vs 실제 구조 비교**:

| README 기재 | 실제 존재 | 차이 |
|-------------|----------|------|
| `bots/` | ✅ (YAML 설정 파일) | 정확 |
| `core/` | ✅ (메시지 라우팅·엔진 공통) | 정확 |
| `skills/` | ✅ (플러그인 스킬) | 정확 |
| `dashboard/` | ✅ (대시보드 모듈) | 정확 |
| `tests/` | ✅ (E2E + 유닛) | 정확 |
| `orchestration.yaml` | ✅ | 정확 |
| `organizations.yaml` | ✅ | **README에 누락** |
| `quickstart.sh` | ✅ | 정확 |
| `docker-compose.yml` | ✅ | 정확 |
| `tools/` | ✅ (러너, CLI, 유틸) | **README에 누락** |
| `scripts/` | ✅ (운영 스크립트) | **README에 누락** |
| `docs/` | ✅ (문서) | **README에 누락** |
| `assets/` | ✅ (이미지, 로고) | **README에 누락** |
| `config/` | ✅ | **README에 누락** |
| `main.py` | ✅ (진입점) | **README에 누락** |
| `dashboard.py` | ✅ (대시보드 진입점) | **README에 누락** |
| `goal_tracker/` | ✅ | **README에 누락** |
| `infra/` | ✅ | **README에 누락** |

**수정된 프로젝트 구조**:
```
aimesh/
├── main.py               # 봇 시스템 진입점
├── dashboard.py           # 대시보드 진입점
├── orchestration.yaml     # 조직 운영 전략 설정
├── organizations.yaml     # 봇 조직 구성 (부서·엔진 배정)
├── docker-compose.yml     # 멀티엔진 Docker 설정
├── quickstart.sh          # 원클릭 설치 스크립트
├── bots/                  # 부서별 봇 설정 (YAML)
├── core/                  # 메시지 라우팅·엔진 공통 코어
├── tools/                 # AI 엔진 러너, CLI 도구, 유틸리티
├── skills/                # 플러그인 스킬 모음
├── scripts/               # 운영·배포 스크립트
├── dashboard/             # 실시간 모니터링 대시보드
├── tests/                 # E2E + 유닛 테스트
├── docs/                  # 프로젝트 문서
├── assets/                # 로고·다이어그램·스크린샷
├── config/                # 환경별 설정
├── goal_tracker/          # 목표 추적 시스템
└── infra/                 # 인프라 베이스라인 설정
```

---

### WI-09: 라이선스 연도 수정

**현재**: `[MIT License](LICENSE) © 2024 telegram-ai-org contributors`
**수정**: `[MIT License](LICENSE) © 2025–2026 AIMesh contributors`

---

## 6. 품질 검증 체크리스트

### 로고 (WI-01)
- [ ] 해상도 ≥ 512×512
- [ ] PNG 포맷
- [ ] 투명 또는 흰색 배경
- [ ] 파일 크기 < 1MB
- [ ] 동물 캐릭터 없음
- [ ] AIMesh 메시 네트워크 컨셉 반영
- [ ] Rocky 최종 승인

### README 전체
- [ ] 토끼 이미지 참조 완전 제거
- [ ] `assets/logo.png` 정상 렌더링 (GitHub 미리보기)
- [ ] Mermaid 코드블록 완전 제거 → 이미지 교체
- [ ] "AI 엔진 하나 선택" 문구 제거
- [ ] Codex 엔진 테이블 반영
- [ ] 프로젝트 구조 현실 반영
- [ ] 라이선스 연도 2025–2026
- [ ] 모든 이미지 alt 텍스트 존재
- [ ] 깨진 이미지 링크 없음

---

## 7. 인수 조건 (Definition of Done)

1. `assets/logo.png` 파일 존재 + README에서 정상 표시
2. README 내 토끼/NanoBunny 참조 0건
3. 모든 이미지가 Gemini 3.1 Flash Image Preview로 생성 (프롬프트 기록)
4. Mermaid 코드블록 0건 → 이미지로 대체
5. Quick Start에서 "엔진 선택" 문구 제거 + 커스텀 가이드 추가
6. 부서별 봇 테이블에 Codex 폴백 컬럼 존재
7. 프로젝트 구조가 실제 디렉토리와 일치
8. 라이선스 연도 정확

---

## 8. 롤백 기준

- 로고 품질 미달 시: README에서 이미지 섹션만 제거한 텍스트 버전 유지
- Gemini 이미지 생성 실패 시: 텍스트 설명으로 대체 (이미지 placeholder 남기지 않음)
- 기존 `assets/mascot/` 파일은 삭제하지 않음 (레거시 참조용 보존)

---

## 9. 실행 위임 계획

| 작업 | 위임 대상 | 우선순위 |
|------|----------|---------|
| WI-01 로고 생성 | 디자인실 (@aiorg_design_bot) | P0 (선행) |
| WI-02~03, WI-05 이미지 생성 (5개) | 디자인실 (@aiorg_design_bot) | P1 |
| WI-04 Quick Start 코드 + WI-07 Codex 적용 확인 | 개발실 (@aiorg_engineering_bot) | P1 |
| WI-04~09 README 전체 편집 | 개발실 (@aiorg_engineering_bot) | P2 (이미지 완료 후) |
| WI-06 스크린샷 | Rocky (수동 업로드) | P2 |

---

## 10. 운영 기준 추가

> **향후 README 내 이미지 운영 기준**: 모든 새 이미지는 `gemini-3.1-flash-image-preview` 모델로 생성하며, 사용한 프롬프트를 해당 디렉토리의 `PROMPT_LOG.md`에 기록한다.
