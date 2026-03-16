# verification

## Request
최근 2026년 3월 기준 코딩에이전트(오픈소스 포함) 시장 조사해주고 기술적으로 트렌드를 파악해줘

## Note
조직 위임 implementation phase 이동

## Verification summary
- at: 2026-03-16T03:32:03.068107+00:00

@stock_ai_ko ✅ [리서치실] 태스크 T-aiorg_pm_bot-016 완료
---

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

- **Cursor**: 2025.11 $2.3B 조달 @ $29.3B 밸류 → 현재 $50B

## Verification summary
- at: 2026-03-16T03:43:02.285962+00:00

@stock_ai_ko ✅ [리서치실] 태스크 T-aiorg_pm_bot-017 완료
---

## 2026년 3월 코딩 에이전트 기술 트렌드 — 핵심 요약

**결론**: 시장은 "단일 모델 자동완성" → **자율 멀티에이전트 + 1M 컨텍스트 + MCP 표준** 3축으로 완전히 재편됐습니다.

---

### 에이전트 아키텍처
- **멀티에이전트**가 단일 에이전트 대비 3배 성능 (SWE-bench Pro 기준: Devin 1.0 13.86% → Claude Sonnet 4.5 멀티에이전트 43.6%)
- **MCP**가 Big 3 (Anthropic·OpenAI·Google) 모두 채택 + Linux Foundation 이관 → 사실상 TCP/IP 확정
- **Claude Opus 4.6** 1M 토큰 GA (2026-03-13), 할증 없는 단가 → 전체 레포 단일 프롬프트 로드 현실화

### 코드 특화 LLM
- SWE-bench Verified 최고: **Claude Opus 4.5 + scaffold 80.9%**, Sonar Foundation Ag
