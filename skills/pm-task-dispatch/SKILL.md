---
name: pm-task-dispatch
description: "Use when the PM bot receives a task and needs to route it to the right department bot. Analyzes task type and assigns to engineering/design/growth/ops/research/product. Triggers: 'pm dispatch', '업무배분', 'assign task', '태스크 배분', 'route task', when a new request needs to be delegated to a specialist bot"
---

# PM Task Dispatch (업무배분 스킬)

PM 봇이 수신된 태스크를 분석하고 가장 적합한 조직 봇에 배분하는 체계적 프로세스.

## 절차

### Step 1: 태스크 분석
태스크를 받으면 다음을 파악한다:
- **주요 영역**: 개발/디자인/성장/운영/연구/제품 중 하나 또는 복합
- **긴급도**: 즉시/오늘중/이번주
- **의존성**: 다른 봇의 산출물이 먼저 필요한지
- **예상 규모**: S(1-2h) / M(반나절) / L(하루+)

### Step 2: 봇 선정
```
태스크 유형 → 담당 봇
코드/API/버그  → 개발실 (aiorg_engineering_bot)
UI/UX/디자인   → 디자인실 (aiorg_design_bot)
마케팅/지표    → 성장실 (aiorg_growth_bot)
운영/인프라    → 운영실 (aiorg_ops_bot)
시장조사/분석  → 연구실 (aiorg_research_bot)
기획/PRD       → 제품실 (aiorg_product_bot)
복합 태스크    → 주담당 봇 + 협업 봇 명시
```

### Step 3: 배분 메시지 작성
```
[태스크 배분] #{태스크ID}
담당: @{봇이름}
내용: {태스크 설명}
긴급도: {즉시/오늘중/이번주}
기대 산출물: {구체적 결과물}
협업 필요: {다른 봇 있으면 명시}
```

### Step 4: 진행 추적
- 배분 후 `orchestration.yaml` docs_root에 태스크 상태 기록
- 완료 예상 시간이 지나면 팔로업 메시지 전송
- 완료 보고 수신 시 Rocky에게 요약 전달

## 복합 태스크 처리
여러 봇이 필요한 태스크:
1. 의존성 그래프 분석
2. 병렬 실행 가능한 부분 식별
3. 순서대로 배분 (병렬 가능한 것은 동시 배분)

## 안티패턴
- ❌ 모든 태스크를 개발실에만 배분
- ❌ 의존성 고려 없이 동시 배분
- ✅ 태스크 성격에 맞는 봇 선정
- ✅ 명확한 기대 산출물 명시
