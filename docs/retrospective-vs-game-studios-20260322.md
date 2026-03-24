# 회고: Claude Code Game Studios vs. aiorg 조직 비교 분석
> 작성 기준: 2026-03-22 | 비교 대상: https://github.com/Donchitos/Claude-Code-Game-Studios

---

## 핵심 요약

Game Studios 레포는 "잘 정의된 스킬/파이프라인으로 48개 AI를 조직처럼 운영"하는 레퍼런스 사례다.
우리 조직(aiorg)은 **에이전트 수(197개)와 도메인 커버리지에서 압도적으로 앞서지만**,
**스킬 수(4개 vs 37개)와 자동화 검수 체계(훅 0개 vs 8개)에서 명확한 격차**가 있다.
"조직 설계" 관점에서 우리가 더 큰 조직을 갖고도 잠재력을 덜 쓰고 있는 구조다.

---

## 1. 에이전트 수 및 역할 구조 비교

| 항목 | Game Studios | aiorg |
|------|-------------|-------|
| 에이전트 수 | 48개 | 197개 |
| 계층 구조 | 3티어 (Director/Lead/Specialist) | 조직별 분류 (design/engineering/marketing 등) |
| 역할 명세 | 에이전트당 담당 디렉토리·출력물 명시 | 에이전트당 전문분야·스타일 명시 |
| 모델 배정 | Tier에 따라 Opus/Sonnet/Haiku 차등 | 단일 모델 (Sonnet) |
| 에이전트간 갈등 해소 | coordination-rules.md (5개 규칙 명문화) | orchestration.yaml 글로벌 지침 |

**Game Studios 강점**: 수직 위임(Vertical Delegation), 수평 협의(Horizontal Consultation), 갈등시 상위 에이전트 에스컬레이션이 문서화됨. "No Unilateral Cross-Domain Changes" 원칙으로 에이전트 월권 방지.

**aiorg 강점**: 도메인 커버리지(game dev, marketing, engineering, sales 등)가 훨씬 넓음. 197개는 단일 도메인이 아닌 멀티버티컬 조직.

**격차**: aiorg는 에이전트 간 갈등 해소 프로토콜, 모델 티어 배정 기준이 명시적이지 않음.

---

## 2. 스킬(명령어) 목록 비교

| 항목 | Game Studios | aiorg |
|------|-------------|-------|
| 스킬 수 | 37개 | 4개 (session-wrap, strategic-compact, tool-advisor, verification-engine) |
| 스킬 구조 | 각 스킬이 독립 디렉토리 + SKILL.md | 동일 구조 ✅ |
| 워크플로우 커버리지 | 프로젝트 전 생애주기 (시작→설계→개발→QA→릴리스) | 세션 관리·검증 중심 |
| 팀 소집 스킬 | /team-audio, /team-combat 등 도메인별 팀 소집 | 없음 |
| 단계 게이트 스킬 | /gate-check (7단계 Phase Gate + PASS/FAIL 판정) | 없음 |
| 자동화 트리거 | 37개 스킬 모두 trigger 조건 명시 | 일부 명시 |

**Game Studios 핵심 패턴**: `/gate-check`는 Phase별 필수 아티팩트 체크리스트 + 자동 검증 + 사용자 확인을 묶어서 실행. "Never assume PASS for unverifiable items." 원칙이 스킬 안에 명문화됨.

**aiorg 강점**: `verification-engine`의 Iron Law("NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE")는 Game Studios보다 더 엄격한 검증 철학. `session-wrap`의 4개 병렬 서브에이전트 구조는 오히려 더 정교함.

**격차**: 태스크 생애주기 전체를 커버하는 스킬이 없음. 개발 시작→설계→PR→배포→회고에 해당하는 스킬이 0개.

---

## 3. CLAUDE.md 및 워크플로우 정의 비교

| 항목 | Game Studios | aiorg |
|------|-------------|-------|
| CLAUDE.md 역할 | 협업 원칙 + 기술스택 + 규칙 파일 @참조 | 없음 (orchestration.yaml + 봇별 system prompt) |
| 협업 철학 명문화 | "Question→Options→Decision→Draft→Approval" 5단계 | orchestration.yaml 글로벌 지침에 스코프 규칙 |
| 파일 쓰기 전 승인 | "May I write this to [filepath]?" 필수 | 프로덕션 데이터 수정 시 Rocky 승인 필수 |
| 세션 상태 관리 | production/stage.txt + session-state/ | 없음 (태스크 단위 stateless) |

**Game Studios 강점**: 협업 원칙이 COLLABORATIVE-DESIGN-PRINCIPLE.md에 예시 포함해서 상세히 기술. "Wrong Model (자율 생성기)" vs "Right Model (전문 컨설턴트)" 대비가 명확.

**aiorg 강점**: orchestration.yaml의 글로벌 지침이 모든 봇에 자동 주입됨 — 일관성 면에서 우수. 특히 "위험한 시스템 탐색 절대 금지" 같은 실운영 사고에서 나온 구체적 룰이 있음.

---

## 4. 코딩 규칙 비교

| 항목 | Game Studios | aiorg |
|------|-------------|-------|
| 경로별 규칙 파일 | 11개 (ai-code.md, gameplay-code.md 등 경로별 자동 적용) | 없음 |
| 규칙 강제 방식 | .claude/rules/ → 경로 매칭 시 자동 주입 | 봇 system prompt에 포함 |
| 디자인 문서 섹션 강제 | GDD 8개 섹션 필수 (훅에서 검증) | 없음 |
| 브랜치 전략 | Trunk-based development | 워크트리 기반 브랜치 전략 (orchestration.yaml) |

**Game Studios 핵심**: `src/gameplay/` 코드엔 "데이터 중심 설계" 룰, `src/core/`엔 "메모리 할당 최적화" 룰이 경로만 맞으면 자동 적용됨. 인간이 "이 파일은 어떤 규칙이야"를 기억하지 않아도 됨.

**aiorg 격차**: 파일 경로별 자동 규칙 매칭이 없음. 규칙은 봇의 전체 프롬프트 안에 녹아 있어 선택적 적용이 어려움.

---

## 5. 자동화 검수 체계 비교

| 항목 | Game Studios | aiorg |
|------|-------------|-------|
| 훅 수 | 8개 | 0개 (별도 hook 미운영) |
| 커밋 전 검증 | validate-commit.sh (하드코딩 탐지, TODO 형식, JSON 유효성, GDD 8섹션) | /quality-gate 스킬 (수동 실행) |
| 에셋 검증 | validate-assets.sh (명명 규칙) | 없음 |
| 세션 시작 자동화 | session-start.sh (스프린트 컨텍스트 로드) | 없음 |
| 누락 문서 감지 | detect-gaps.sh | 없음 |
| 컨텍스트 압축 전 | pre-compact.sh | strategic-compact 스킬 (수동) |
| CI/CD 파이프라인 | 없음 (shell script 기반) | 없음 |

**Game Studios 핵심**: 훅이 PreToolUse 단계에서 실행됨 — AI가 commit 명령을 내리기 *전에* 자동으로 검증. 블로킹이 자동화됨.

**aiorg 격차**: /quality-gate 스킬이 있지만 사람/PM이 직접 호출해야 함. 커밋 전 자동 블로킹이 없음.

---

## 종합 평가표

| 영역 | Game Studios | aiorg | 우위 |
|------|:-----------:|:-----:|:----:|
| 에이전트 수/도메인 | 48개 / 게임개발 특화 | 197개 / 멀티버티컬 | **aiorg** |
| 스킬 수 | 37개 | 4개 | **Game Studios** |
| 스킬 설계 품질 | 매우 상세 (단계별 체크리스트) | 높음 (Iron Law 등) | **비등** |
| 협업 원칙 명문화 | 매우 상세 | 보통 (orchestration.yaml) | **Game Studios** |
| 자동화 훅 | 8개 (커밋 전 자동 블로킹) | 0개 | **Game Studios** |
| 경로별 규칙 자동 적용 | 11개 룰 | 없음 | **Game Studios** |
| 실운영 사고 기반 룰 | 없음 | 있음 (홈 탐색 금지 등) | **aiorg** |
| 조직 안전 원칙 | 파일 쓰기 전 승인 | 프로덕션 수정 승인 필수 | **비등** |
| 세션 상태 지속성 | stage.txt + session-state/ | 없음 | **Game Studios** |

---

## 핵심 인사이트 및 액션 제안

### 우리가 잘하고 있는 것 ✅
1. **에이전트 규모와 도메인 커버리지** — 197개로 멀티버티컬 커버. Game Studios는 게임개발 단일 도메인.
2. **검증 철학의 엄밀함** — `verification-engine`의 Iron Law가 Game Studios의 어떤 스킬보다 명확.
3. **실운영 사고 기반 룰** — "위험한 시스템 탐색 절대 금지" 같은 실전 경험이 녹은 규칙이 있음.
4. **글로벌 지침 자동 주입** — orchestration.yaml로 전체 조직에 일관 적용.

### 우리가 부족한 것 ⚠️
1. **스킬 수가 너무 적다 (4개 vs 37개)** — 태스크 생애주기(시작→설계→검토→배포→회고)를 커버하는 스킬이 없음.
2. **자동화 훅이 없다** — 커밋 전/후 자동 검증 없이 전적으로 PM 수동 호출에 의존.
3. **경로별 자동 규칙이 없다** — 파일을 어디에 쓰느냐에 따라 규칙이 달라져야 하는데 수동 판단에 맡김.
4. **세션 상태가 stateless** — 태스크 간 컨텍스트가 memory 파일로만 이어지고, 단계 진행 상태 추적이 없음.

### 즉시 실행 가능한 개선 제안 (우선순위 순)
1. **`/task-kickoff` 스킬 신설** — 태스크 시작 시 스코프·에이전트·산출물·성공조건을 물어보고 확인받는 5단계 스킬 (Game Studios `/start` 패턴 참고)
2. **`/retrospective` 스킬 신설** — 태스크 완료 후 회고, 교훈 추출, MEMORY.md 업데이트를 자동화
3. **PreToolUse 훅 도입** — 커밋 명령 전 자동으로 /quality-gate 를 실행하도록 settings.json에 훅 추가
4. **`/design-review` 스킬 신설** — PRD/설계서 제출 시 필수 섹션 체크리스트 자동 검증

---

*참조 레포: https://github.com/Donchitos/Claude-Code-Game-Studios (v0.3.0, 2.4K stars)*
*분석 기준: 2026-03-22, 로컬 클론 ~/.claude/agents/, orchestration.yaml 직접 비교*
