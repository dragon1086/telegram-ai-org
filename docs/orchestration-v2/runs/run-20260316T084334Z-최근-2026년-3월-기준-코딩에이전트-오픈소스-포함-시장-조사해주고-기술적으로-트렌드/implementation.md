# implementation

## Request
최근 2026년 3월 기준 코딩에이전트(오픈소스 포함) 시장 조사해주고 기술적으로 트렌드를 파악해줘

## Note
조직 위임 실행 design phase 이동

## Implementation dispatch
- at: 2026-03-16T08:45:00.474166+00:00

delegated departments: 리서치실, 개발실

## Implementation result
- at: 2026-03-16T08:51:22.763079+00:00

[TEAM:analyst,scientist]

---

## 2026년 3월 코딩 에이전트 시장 조사 결과

**결론**: 시장은 2026년 기준 ~$8.5B 규모, CAGR 20–25%로 고속 성장 중. Cursor가 가장 빠른 ARR 성장을 보이지만, Claude Code와 Copilot이 각각 에이전틱 실행력과 생태계 지배력으로 3강 구도를 형성 중.

---

### 주요 플레이어 핵심 수치

| 플레이어 | 사용자 | ARR | 시장점유율 |
|---------|-------|-----|---------|
| GitHub Copilot | 유료 470만, 누적 2,000만+ | ~$0.8–1B | 42% |
| **Cursor** | 유료 36만, 총 100만+ | **~$2B+** | 18% |
| Claude Code | 기업 30만+ | ~$2.5B run-rate | ~15%+ |
| Windsurf+Cognition | 100만+ | ~$150M | ~8% |
| Amazon Q Developer | 미공개 | 미공개 | ~7% |

---

### 기술 트렌드 TOP 5

1. **에이전틱 전환** — "코드 제안" → "PR 자동 생성·테스트·배포"까지. Devin, Claude Code, Copilot Workspace 모두 자율 멀티스텝 실행으로 이동
2. **SWE-bench 50%+ 돌파** — 2023년 3% → 2025년 말 50%+. 실제 GitHub 이슈 절반 이상 자동 해결 가능 단계 도달
3. **MCP 생태계 표준화** — Anthropic 주도 Model Context Protocol이 에이전트-도구 연결 사실상 표준으로 자리잡음
4. **Vibe Coding 대중화** — 비개발자도 코딩 진입 가능 → TAM 자체가 확장 중
5. **멀티 에이전트 아키텍처** — 단일 에이전트 → 오케스트레이터+서브에이전트 구조로 진화. 컨텍스트 창 200K+ 토큰이 레포 전체 이해를 가능하게 함

---

### 시장 레이어 구조

```
Layer 4 Enterprise  → Copilot Enterprise, Amazon Q, Devin
Layer 3 Agent Orch  → Claude Code, OpenHands, SWE-agent
Layer 2 IDE/Tool    → Cursor, Windsurf, Continue.dev, Cline
Layer 1 Foundation  → Claude, GPT-4o, Gemini, DeepSeek
```

---

### 오픈소스 주요 플레이어

- **OpenHands** (구 OpenDevin) — 자율 에이전트 프레임워크, 오픈소스 Devin 대항마
- **Aider** — CLI+Git 네이티브, 터미널 개발자 표준
- **Continue.dev** — IDE 플러그인, 오픈소스 Copilot 대체
- **Cline/RooCode** — VS Code 에이전틱 확장, 자율 파일/터미널 조작

---

### PM 핵심 인사이트

- **Cursor**가 역대 B2B SaaS 최속 성장 ($1B→$2B ARR 3개월) — 개발자 커뮤니티 장악이 엔터프라이즈 침투로 연결되는 구조
- **Claude Code**는 CLI임에도 $2.5B run-rate — "에이전틱 실행력" 단독으로 포지션 형성
- **MCP 미지원 툴은 생태계 소외 위험** — 표준 인프라로 부상 중
- **오픈소스 → 엔터프라이즈 전환 경로** 강화 중 (OpenHands, Continue.dev)

---

📄 상세 보고서: `research/coding-agent-market-2026/report.md`
출처: TechCrunch, CNBC, Sacra, SaaStr, Mordor Intelligence, getpanto.ai (2025–2026)

## Implementation result
- at: 2026-03-16T08:55:47.177322+00:00

## 2026년 3월 코딩 에이전트 기술 트렌드 — 핵심 결과

**결론**: SWE-bench 80% 돌파로 AI가 "보조"에서 "주도"로 전환됐고, MCP가 산업 표준으로 확정됐으며, DeepSeek 가격 충격이 시장 구조를 완전히 재편 중이다.

---

### 1. SWE-bench 벤치마크 (2026년 3월)

| 순위 | 모델 | Verified 점수 |
|------|------|--------------|
| 1 | Claude Opus 4.5 | **80.9%** |
| 2 | Claude Opus 4.6 (Thinking) | 80.8% |
| 3 | Gemini 3.1 Pro | 80.6% |
| 4 | MiniMax M2.5 | 80.2% |
| 5 | GPT-5.2 | 80.0% |

- 1년 전(2025년 초) 65% → 현재 80.9%로 **16%p 급등**
- 더 어려운 SWE-bench Pro에서는 여전히 57% 수준 → 포화 우려로 변형 벤치마크 등장

---

### 2. MCP 표준 현황

- **공개 서버 10,000개 돌파** (2025년 초 1,000개 → 10배 성장)
- 2025년 12월: Anthropic이 Linux Foundation 산하 **AAIF에 MCP 기증** → OpenAI·Google·AWS·Microsoft 공동 운영
- 2026년은 "실험 → 기업 전면 도입" 전환점. "MCP 써야 하나?" 논쟁 끝남
- 2026년 로드맵: 이벤트 기반 트리거, 보안/인가 강화, 수평 확장 해결

---

### 3. 멀티에이전트 아키텍처

- Gartner: 멀티에이전트 문의 **1,445% 급증** (2024 Q1 → 2025 Q2)
- **3-Role 패턴** 부상: Planner(계획) → Worker(병렬 실행) → Judge(품질 검증)
- Replit Agent 3: Docker 샌드박스 + Mastra로 태스크 성공률 **80% → 96%**
- **컨텍스트 전략 전환**: 사전 RAG 임베딩 → Just-in-Time 동적 로드 (Anthropic 권고)
- 현실 우려: AI 채택 90% 증가 시 버그율 9%↑, PR 크기 154%↑ (Google DORA 2025)

---

### 4. DeepSeek 가격 전쟁

| 비교 | 가격 차이 |
|------|---------|
| Claude Sonnet vs DeepSeek V3.2 | **107배** 비쌈 |
| Claude Opus vs DeepSeek V3.2 | **536배** 비쌈 |
| GPT-4 Turbo vs DeepSeek | **95% 저렴** |

- DeepSeek V3.2: GPT-5 동급 성능을 1/10 가격으로 주장
- 전략 분화: Anthropic은 에코시스템 충성도, OpenAI는 고성능 Codex 라인으로 방어
- 오픈소스 자체 호스팅 경제성 증가 → 상용/오픈소스 격차 축소

---

### 5. Vibe Coding 주류화

- Collins 사전 **2025년 올해의 단어** 선정
- 시장 규모: $2.96B (2025) → $12.3B (2027) 예측
- 도구 선호도: Claude Code **46%** > Cursor 19% > Copilot 9%
- 숙련 개발자 평균 **2.3개 도구** 병행 사용
- 보안 리스크: AI 생성 코드 **45%** 보안 테스트 실패, 취약점 비율 인간 대비 2.74배

---

### 6. 주목할 오픈소스 에이전트

| 에이전트 | Stars | 강점 |
|---------|-------|------|
| **OpenHands** | **68,884** | 풀 플랫폼, 가장 많은 커뮤니티 |
| **SWE-agent** | 18,705 | 이슈→PR 자동화 특화 |
| **Aider** | 성숙도 최고 | CLI + git 자동 커밋, 93 릴리스 |

---

### 기술 성숙도 한눈에

| 기술 | 성숙도 | 채택 단계 |
|------|--------|---------|
| SWE-bench 에이전트 | 높음 | 초기 대량 채택 |
| MCP 표준 | 높음 | **기업 전면 도입** |
| 멀티에이전트 오케스트레이션 | 중간 | 얼리어답터 |
| Vibe Coding | 높음 | 초기 다수 진입 |
| 가격 경쟁 | 높음 | 시장 전반 영향 |

---

**다음 주목 포인트**: AI 코드 품질/보안 검증 도구 급부상, 컨텍스트 엔지니어링 전문직 등장, MCP 엔터프라이즈 보안 표준화 완료 예정.

상세 보고서: `.omc/research/coding-agent-tech-trends-2026.md`
