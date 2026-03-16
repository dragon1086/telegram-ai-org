# T-aiorg_pm_bot-015 통합 보고서

## 원 요청
최근 2026년 3월 기준 코딩에이전트(오픈소스 포함) 시장 조사해주고 기술적으로 트렌드를 파악해줘

## 최종 전달본
2026년 3월 기준 코딩 에이전트 시장과 기술 트렌드를 리서치실이 전수 조사했습니다. 핵심 결론: **Claude Code가 개발자 선호도 46%로 1위, Cursor가 $29.3B 밸류로 2위이며, SWE-bench 88% 돌파·MCP 표준화 완성·멀티에이전트 3배 성능 향상으로 시장이 "자율 소프트웨어 엔지니어" 시대로 전환 완료됐습니다.**

---

**📊 시장 현황 — 점유율·선호도**

| 제품 | 점유율 | 개발자 선호도 | 특징 |
|------|-------|------------|------|
| GitHub Copilot | ~42% | 9% | 대기업 표준 (10K+ 직원 56% 채택) |
| Cursor | ~18% | 19% | 스타트업~중견, ARR $2B+ |
| **Claude Code** | 급성장 | **46% (1위)** | 2025.05 출시 후 8개월 만에 선호도 1위 |
| Devin (Cognition) | 소수 | - | 완전 자율 에이전트, $20/월로 대폭 인하 |

시장이 이분화됐습니다. **스타트업은 Claude Code+Cursor**, **대기업은 조달 프로세스로 Copilot**이 결정되는 구조입니다.

---

**💰 투자·M&A 현황**
- **Cursor**: 2025.11 $2.3B 조달 @ $29.3B → 현재 $50B 라운드 협상 중, ARR $2B 돌파
- **Cognition(Devin)**: $500M @ $10.2B + **Windsurf 인수** (2025.07)
- **Windsurf**: Cognition 인수 후 Google이 CEO 역채용 ($2.4B)

**💵 가격 비교**

| 제품 | 개인 | 팀/기업 |
|------|-----|--------|
| GitHub Copilot | $10~19/월 | $39/user/월 |
| Cursor | $20~60/월 | $40~200/월 |
| Claude Code | API 토큰 과금 (정액 없음) | 볼륨 기반 |

---

**🔓 오픈소스 Top 4**

| 프로젝트 | Stars | 특징 |
|---------|------|------|
| **OpenHands** | 68,884★ | VS Code+브라우저+Jupyter, 셀프호스팅 |
| **Aider** | 41,543★ | 순수 CLI, 빠른 설치 |
| **Continue** | ~30K★ | 로컬 모델 지원, 프라이버시 우선 |
| **SWE-agent** | 18,705★ | GitHub 이슈 해결 특화, 연구용 |

---

**⚙️ 기술 트렌드 5대 전환**

**① 에이전트 아키텍처 — 멀티에이전트가 3배 성능**
- 단일 에이전트 대비 멀티에이전트 3배 성능 (SWE-bench Pro: Devin 1.0 13.86% → Claude Sonnet 4.5 멀티에이전트 43.6%)
- **MCP**: Anthropic·OpenAI·Google 빅3 모두 채택 + Linux Foundation 이관 → 사실상 TCP/IP급 업계 표준 확정. 월 다운로드 9,700만
- **Claude Opus 4.6** 1M 토큰 GA (2026-03-13), 할증 없는 단가 → 전체 레포 단일 프롬프트 로드 현실화

**② 코드 특화 LLM — 오픈소스가 클로즈드에 근접**
- SWE-bench Verified 최고: **Claude Opus 4.5 + scaffold 80.9%**, Sonar Foundation Agent 79.2%, Gemini 3 Flash 78.0%
- **오픈소스 격차 급속 축소**: DeepSeek-V3(MIT), Qwen2.5-Coder-32B(Apache 2.0) → GPT-4o 수준 → 기업 자체 배포 현실화
- Extended Thinking / RL 추론이 SWE-bench +13~23%p 향상 주도

**③ RAG → 에이전틱 검색으로 전환**
- 정적 벡터 RAG 퇴조 (Claude Code 팀도 포기), **Agentic RAG** 주류화
- **AST 기반 청킹(cAST)**: RepoEval Recall@5 +4.3%p, SWE-bench Pass@1 +2.67%p (EMNLP 2025)
- Sourcegraph Cody 종료 → Amp 전환; code-graph-rag MCP 연동

**④ 자율 디버깅·테스트 자동화**
- **Sonar Foundation Agent** (구 AutoCodeRover) SWE-bench Verified 79.2%, $1.9/이슈
- Agentic CI/CD 실용화: 빌드 실패 → Repair Agent 자동 기동 → 커밋
- Devin 2.0: $500 → **$20/월** 파격 인하 (내부 83% 향상 주장, 독립 검증 미완료)
- **"스캐폴딩이 모델보다 중요"**: 동일 모델, 다른 프레임워크 → 17 이슈(약 5~7%p) 차이 발생

**⑤ 벤치마크 세대 교체**
- HumanEval **포화(99.0%)** → 변별력 소멸
- SWE-bench Verified 오염(8~10%) 문제 → **SWE-bench Pro / Multilingual / Live** 2세대 등장
- SWE-bench Pro 최고: Opus 4.6 + WarpGrep v2 **57.5%** (Verified 대비 -23%p, 훨씬 어려움)
- LiveCodeBench가 매월 갱신되어 오염 없는 신뢰 지표로 부상

---

**📈 SWE-bench 성장 궤적**
SWE-bench 49%(2024.10) → **88%(2026.02)** — 18개월 만에 거의 2배. 실 GitHub 이슈 자동 해결이 실용적 수준 도달.

---

**🔭 단기·중기 전망**

| 기간 | 예측 |
|------|------|
| 6개월 | SWE-bench Pro가 주력 평가 지표 교체. MCP 생태계 확장 가속. Claude Code 정액 플랜 도입 시 점유율 급변 가능. Cursor $50B 라운드 성사 시 IPO 트리거 |
| 1년 | 소형 특화 코드 모델이 범용 LLM 대체. 보안 샌드박스가 제품 필수 스펙화. Agentic CI/CD 표준화 |

---

상세 자료: **coding_agent_market_2026_03.md** · **final-report.md** (약 7페이지, Executive Summary → 아키텍처 → LLM → RAG → 자율화 → 벤치마크 → 오픈소스 vs 클로즈드 격차표 → 단/중기 예측 구성)

## 조직별 핵심 결과
### 리서치실
## 2026년 3월 코딩 에이전트 시장 조사 결과

**결론부터**: Claude Code가 개발자 선호도 46%로 1위, Cursor는 $29.3B 밸류에이션, 시장은 "자율 멀티파일 에이전트"로 빠르게 재편 중입니다.

---

### 시장 점유율 & 선호도

| 제품 | 점유율 | 개발자 선호도 | 특징 |
|------|-------|------------|-----|
| GitHub Copilot | ~42% | 9% | 대기업 표준 (10K+ 직원 56%) |
| Cursor | ~18% | 19% | 스타트업~중견, ARR $2B+ |
| **Claude Code** | 급성장 | **46% (1위)** | 2025.05 출시 후 8개월 만에 1위 |
| Devin (Cognition) | 소수 | - | 완전 자율 에이전트 |

---

### 투자·M&A 현황

- **Cursor**: 2025.11 $2.3B 조달 @ $29.3B 밸류 → 현재 $50B 라운드 협상 중, ARR $2B 돌파
- **Cognition(Devin)**: $500M 조달 @ $10.2B + **Windsurf 인수** (2025.07)
- **Windsurf**: Cognition에 인수, Google이 CEO 역채용 ($2.4B)

---

### 가격 비교

| 제품 | 개인 | 팀/기업 |
|------|-----|---------|
| GitHub Copilot | $10~19/월 | $39/user/월 |
| Cursor | $20~60/월 | $40~200/월 |
| Claude Code | API 토큰 과금 (정액 없음) | 볼륨 기반 |

---

### 오픈소스 Top 4

| 프로젝트 | Stars | 특징 |
|---------|------|------|
| **OpenHands** | 68,884★ | VS Code+브라우저+Jupyter, 셀프호스팅 |
| **Aider** | 41,543★ | 순수 CLI, 빠른 설치 |
| **Continue** | ~30K★ | 로컬 모델 지원, 프라이버시 우선 |
| **SWE-agent** | 18,705★ | GitHub 이슈 해결 특화, 연구용 |

---

### 기술 트렌드 핵심 5가지

1. **SWE-bench 폭등**: 49%(2024.10) → 88%(2026.02) — 18개월 만에 거의 2배. 실 GitHub 이슈 자동 해결 가능 수준
2. **스캐폴딩이 모델보다 중요**: 동일 모델, 다른 프레임워크 → 17 이슈 차이 발생
3. **시장 이분화**: 스타트업은 Claude Code+Cursor, 대기업은 Copilot (조달 프로세스가 선택 결정)
4. **완전 자율 에이전트 표준화**: 단순 자동완성 → 멀티파일 수정+테스트 실행+자체 반복
5. **M&A 가속**: Cognition-Windsurf 통합, 빅테크의 인재·기술 흡수 경쟁

---

### 주목할 다음 포인트

- Claude Code 정액 플랜 도입 여부 → 시장점유율 급변 가능
- Cursor $50B 라운드 성사 시 IPO 트리거
- SWE-bench 90% 근접 → 새 벤치마크 기준 논의 시작

상세 보고서: `.omc/research/coding-agent-market-2026-03.md`

---

**Sources:**
- [Cursor $2.3B 조달 - TechCrunch](https://techcrunch.com/2025/11/13/coding-assistant-cursor-raises-2-3b-5-months-after-its-previous-round/)
- [Cognition Windsurf 인수 - TechCrunch](https://techcrunch.com/2025/07/14/cognition-maker-of-the-ai-coding-agent-devin-acquires-windsurf/)
- [Cognition $10.2B 밸류에이션 - CNBC](https://www.cnbc.com/2025/09/08/cognition-valued-at-10point2-billion-two-months-after-windsurf-.html)
- [개발자 선호도 통계 - Faros AI](https://www.faros.ai/blog/best-ai-coding-agents-2026)
- [OpenHands vs Aider - OpenAlternative](https://openalternative.co/compare/aider/vs/openhands)
- [기술 트렌드 - The New Stack](https://thenewstack.io/5-key-trends-shaping-agentic-development-in-2026/)

__EXIT_CODE__:0

### 리서치실
## 2026년 3월 코딩 에이전트 기술 트렌드 — 핵심 요약

**결론**: 시장은 "단일 모델 자동완성" → **자율 멀티에이전트 + 1M 컨텍스트 + MCP 표준** 3축으로 완전히 재편됐습니다.

---

### 에이전트 아키텍처
- **멀티에이전트**가 단일 에이전트 대비 3배 성능 (SWE-bench Pro 기준: Devin 1.0 13.86% → Claude Sonnet 4.5 멀티에이전트 43.6%)
- **MCP**가 Big 3 (Anthropic·OpenAI·Google) 모두 채택 + Linux Foundation 이관 → 사실상 TCP/IP 확정
- **Claude Opus 4.6** 1M 토큰 GA (2026-03-13), 할증 없는 단가 → 전체 레포 단일 프롬프트 로드 현실화

### 코드 특화 LLM
- SWE-bench Verified 최고: **Claude Opus 4.5 + scaffold 80.9%**, Sonar Foundation Agent 79.2%, Gemini 3 Flash 78.0%
- **오픈소스 격차 급속 축소**: DeepSeek-V3(MIT), Qwen2.5-Coder-32B(Apache 2.0) → GPT-4o 수준 → 기업 자체 배포 현실화
- Extended Thinking / RL 추론이 SWE-bench +13~23%p 향상 주도

### RAG·코드 인덱싱
- 정적 벡터 RAG 퇴조 (Claude Code 팀도 포기), **Agentic RAG** 주류
- **AST 기반 청킹(cAST)**: RepoEval Recall@5 +4.3%p, SWE-bench Pass@1 +2.67%p (EMNLP 2025)
- Sourcegraph Cody 종료 → Amp 전환; code-graph-rag MCP 연동

### 자율 디버깅·테스트 자동화
- **Sonar Foundation Agent** (구 AutoCodeRover) SWE-bench Verified 79.2%, $1.9/이슈
- Agentic CI/CD 실용화: 빌드 실패 → Repair Agent 자동 기동 → 커밋
- Devin 2.0: $500 → **$20/월** 파격 인하, 내부 83% 향상 주장 (독립 검증 미완료)

### 벤치마크 변화
- HumanEval 포화 (99.0%), LiveCodeBench가 새 기준
- SWE-bench Verified 오염(8-10%) 문제 → **SWE-bench Pro / Multilingual / Live** 2세대 등장
- SWE-bench Pro 최고: Opus 4.6 + WarpGrep v2 **57.5%** (Verified 대비 -23%p, 훨씬 어려움)

---

**최종 보고서**: `/Users/rocky/.ai-org/workspace/reports/coding-agent-trends-2026/final-report.md`
(Executive Summary → 아키텍처 → LLM → RAG → 자율화 → 벤치마크 → 오픈소스 vs 클로즈드 격차표 → 단/중기 예측 순 구성, 약 7페이지 분량)

__EXIT_CODE__:0
