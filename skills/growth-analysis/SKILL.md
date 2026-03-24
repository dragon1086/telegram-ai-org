---
name: growth-analysis
description: "Use when analyzing growth metrics, user retention, or conversion funnels. Produces data-driven recommendations. Triggers: 'growth analysis', '성장분석', 'metrics analysis', '지표분석', 'growth', 'retention', 'conversion'"
allowed-tools: Read, Glob, Grep, WebSearch
---

# Growth Analysis (성장분석 스킬)

성장실 봇이 데이터 기반으로 성장 지표를 분석한다.

## 분석 프레임워크
1. **현황**: 주요 지표 현재값 (DAU, 전환율, 리텐션 등)
2. **추세**: 전주/전월 대비 변화
3. **원인 분석**: 변화의 근본 원인
4. **실험 제안**: A/B 테스트 아이디어
5. **다음 단계**: 구체적 액션 아이템

## 출력 형식
- 요약: 3줄 이내
- 상세: `docs/growth/YYYY-MM-DD-analysis.md`
