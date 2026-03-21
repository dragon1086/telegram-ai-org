# Skills 인덱스 — telegram-ai-org

AI 조직 하네스에서 사용하는 스킬 목록. 각 스킬은 특정 트리거 키워드로 자동 활성화된다.

## 스킬 목록

| 스킬 | 트리거 | 용도 | 자율실행 |
|------|--------|------|----------|
| autonomous-skill-proxy | 'autonomous mode', '자율모드' | 인터랙티브 스킬 자동 응답 | ✅ |
| brainstorming-auto | 'auto design', '자동 설계' | 비인터랙티브 브레인스토밍 | ✅ |
| pm-task-dispatch | 'pm dispatch', '업무배분' | PM 태스크 배분 | ✅ |
| pm-discussion | 'discuss', '토론' | 다봇 토론 조율 | ✅ |
| weekly-review | '주간회의', 'weekly review' | 주간회의 자율 진행 | ✅ |
| retro | '회고', 'retrospective' | 스프린트 회고 | ✅ |
| performance-eval | '성과평가', 'evaluation' | 봇 성과 평가 | ✅ |
| engineering-review | 'code review', '코드리뷰' | 코드 품질 검토 | ✅ |
| growth-analysis | 'growth analysis', '성장분석' | 성장 지표 분석 | ✅ |
| design-critique | 'design review', '디자인 리뷰' | UI/UX 리뷰 | ✅ |
| quality-gate | 'quality gate', '품질검사' | 배포 전 품질 검사 | ✅ |
| harness-audit | 'harness audit', '하네스 감사' | 시스템 신뢰성 감사 | ✅ |
| loop-checkpoint | 'checkpoint', '체크포인트' | 루프 상태 저장/재개 | ✅ |
| create-skill | 'create skill', '스킬 만들기' | 새 스킬 제작 가이드 | ✅ |
| skill-evolve | 'skill evolution', '스킬 진화' | 교훈 기반 스킬 개선 제안 | ✅ |
| error-gotcha | 'error gotcha', '에러 회고' | 에러 수정 후 gotcha 자동 추가 | ✅ |

## 스킬 설치 경로
```
skills/
├── autonomous-skill-proxy/SKILL.md
├── brainstorming-auto/SKILL.md
├── pm-task-dispatch/SKILL.md
├── pm-discussion/SKILL.md
├── weekly-review/SKILL.md
├── retro/SKILL.md
├── performance-eval/SKILL.md
├── engineering-review/SKILL.md
├── growth-analysis/SKILL.md
├── design-critique/SKILL.md
├── quality-gate/SKILL.md
├── harness-audit/SKILL.md
├── loop-checkpoint/SKILL.md
├── create-skill/SKILL.md
├── skill-evolve/SKILL.md
└── error-gotcha/SKILL.md
```

## 스킬 우선순위 (everything-claude-code 패턴)
1. 하네스 스킬 먼저 (quality-gate, harness-audit)
2. PM 조율 스킬 (pm-task-dispatch, pm-discussion)
3. 회사 활동 스킬 (weekly-review, retro, performance-eval)
4. 조직별 스킬 (engineering-review, growth-analysis, design-critique)
5. 자율화 스킬 (autonomous-skill-proxy, brainstorming-auto, loop-checkpoint)
6. 메타 스킬 (create-skill, skill-evolve, error-gotcha)
