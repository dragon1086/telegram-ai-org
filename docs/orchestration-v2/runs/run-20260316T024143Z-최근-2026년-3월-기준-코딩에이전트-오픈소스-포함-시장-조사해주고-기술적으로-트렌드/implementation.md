# implementation

## Request
최근 2026년 3월 기준 코딩에이전트(오픈소스 포함) 시장 조사해주고 기술적으로 트렌드를 파악해줘

## Note
조직 위임 실행 design phase 이동

## Implementation dispatch
- at: 2026-03-16T02:43:05.405402+00:00

delegated departments: 리서치실, 리서치실

## Implementation result
- at: 2026-03-16T02:45:52.974694+00:00

## 2026년 3월 코딩 에이전트 시장 — 핵심 결론

**시장은 $74억 규모로, Cursor가 가장 뜨겁고 GitHub Copilot이 점유율 1위를 유지하고 있다.**

---

### 🏆 상용 제품 현황

| 제품 | 점유율/사용자 | 밸류에이션 | 가격(개인) |
|------|-------------|-----------|-----------|
| **GitHub Copilot** | 42%, 누적 2,000만 유저 | MS 산하 | $10–$39/월 |
| **Cursor** | 18%, ARR $1B+ | **$29.3B → $50B 협상 중** | $20/월 |
| **Windsurf** | LogRocket 1위 랭킹 | Cognition 인수 (~$250M) | $15/월 |
| **Devin** | ARR ~$150M (Windsurf 합산) | $10.2B | $20+종량제 |
| **Claude Code** | 개발자 선호 46% (1위) | Anthropic $61.5B | $20–$100/월 |

### 🔓 오픈소스 현황

| 프로젝트 | GitHub Stars | 특징 |
|---------|-------------|------|
| **OpenHands** | 68,884 ⭐ | 오픈소스 최대, E2E 자율 에이전트 |
| **Aider** | - | SWE-bench **88%** (GPT-5, 최고 성능) |
| **SWE-agent** | 18,705 ⭐ | 학술 연구 기반 |
| **Continue** | - | IDE 플러그인, 로컬 모델 지원 |

### 📈 핵심 기술 트렌드 (3가지)

1. **Agentic Coding 전환**: 자동완성 → 자율 PR 생성. SWE-bench 88% 달성으로 실용적 수준 도달
2. **M&A 가속**: Cognition이 Windsurf를 $250M에 인수 — IDE + 자율 에이전트 통합 트렌드
3. **오픈소스 추격**: Aider+GPT-5가 상용 제품 성능을 추월하는 구간 발생

---

보고서 전문 저장 위치: `research/coding_agent_market_2026_03.md`
(가격 비교표, 투자 현황 목록, 상용 vs 오픈소스 대비표 포함)

Sources:
- [GitHub Copilot crosses 20M users](https://techcrunch.com/2025/07/30/github-copilot-crosses-20-million-all-time-users/)
- [Cursor $2.3B Series D](https://www.cnbc.com/2025/11/13/cursor-ai-startup-funding-round-valuation.html)
- [Cursor $50B valuation talks](https://www.investing.com/news/stock-market-news/ai-coding-startup-cursor-in-talks-for-funding-at-50-bln-valuation-bloomberg-4555960)
- [Cognition AI $400M raise at $10.2B](https://techcrunch.com/2025/09/08/cognition-ai-defies-turbulence-with-a-400m-raise-at-10-2b-valuation/)
- [Devin 2.0 pricing $20](https://venturebeat.com/programming-development/devin-2-0-is-here-cognition-slashes-price-of-ai-software-engineer-to-20-per-month-from-500)
- [OpenHands GitHub](https://github.com/OpenHands/OpenHands)
- [LogRocket AI Dev Tool Rankings](https://blog.logrocket.com/ai-dev-tool-power-rankings/)
- [Anthropic 2026 Agentic Coding Report](https://resources.anthropic.com/hubfs/2026%20Agentic%20Coding%20Trends%20Report.pdf)

__EXIT_CODE__:0

## Implementation result
- at: 2026-03-16T02:57:33.607889+00:00

---

## 2026년 3월 코딩 에이전트 기술 트렌드 — 종합 분석

**결론부터**: 코딩 에이전트는 2년 만에 SWE-bench 9% → 80.9%로 9배 성장했고, 기술 패러다임이 3가지 축에서 동시에 전환 중입니다.

---

### 핵심 5가지

**1. SWE-bench 80% 벽 돌파**
- Claude Opus 4.5 80.9%, Gemini 3.1 Pro 80.6%, GPT-5.2 80.0% — 상위 5개 모두 80%+
- 단, SWE-bench Pro(장기·복합 과제)에서는 여전히 **23% 상한** — 실전과의 괴리 여전

**2. RAG → 에이전틱 검색으로 패러다임 전환**
- Claude Code가 벡터 DB를 버리고 "도구로 코드 탐색"으로 전환. Cursor는 임베딩 유지, Continue.dev는 AST+임베딩+ripgrep 앙상블으로 중간 전략
- tree-sitter 기반 semantic chunking이 업계 표준으로 정착

**3. 프로토콜 표준화 완성**
- MCP(월 9,700만 다운로드) + A2A = 사실상 전 업계 표준. Linux Foundation 거버넌스로 이관
- 컨텍스트 윈도우: Llama 4 Scout 10M 토큰까지 확장, 그러나 실질 성능 괴리 주의

**4. "100줄의 역설"**
- Princeton mini-SWE-agent: 100줄 Python으로 74% 달성 → 복잡한 스캐폴드보다 강한 모델이 핵심
- 멀티에이전트는 통합 단계: OpenAI Agents SDK, Microsoft Agent Framework로 수렴

**5. 오픈소스의 추격**
- Qwen 2.5 Coder HumanEval 88.4%, DeepSeek V3.2 Speciale이 GPT-5급 성능을 저비용으로
- Cline이 VS Code 500만+ 설치로 오픈소스 채택 1위. OpenHands 40K+ stars

---

### 벤치마크 변화

| 벤치마크 | 상황 |
|---|---|
| HumanEval | **포화 상태 (99%)** — 더 이상 변별력 없음 |
| SWE-bench Verified | 주요 지표. 80%+ 시대 진입 |
| LiveCodeBench | 매월 갱신, 오염 방지 — 신뢰도 가장 높음 |
| SWE-bench Pro | 장기 과제용 — 진짜 엔지니어링 능력 측정 |

---

보고서 저장: `reports/20260316_coding_agent_tech_trends.md`

__EXIT_CODE__:0
