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
| safe-modify | 'safe modify', '안전 수정', '실패감지 수정', '부작용 최소화' | 실패 감지·고위험 코드 안전 수정 체크리스트 | ✅ |
| failure-detect-llm | 'failure detect', 'LLM 실패감지', 'borderline failure', 'survival_rate 경계' | LLM 기반 실패 감지 보조 (경계 케이스 재검증) | ✅ |
| growth-analysis | 'growth analysis', '성장분석' | 성장 지표 분석 | ✅ |
| design-critique | 'design review', '디자인 리뷰' | UI/UX 리뷰 | ✅ |
| quality-gate | 'quality gate', '품질검사' | 배포 전 품질 검사 | ✅ |
| harness-audit | 'harness audit', '하네스 감사' | 시스템 신뢰성 감사 | ✅ |
| loop-checkpoint | 'checkpoint', '체크포인트' | 루프 상태 저장/재개 | ✅ |
| create-skill | 'create skill', '스킬 만들기' | 새 스킬 제작 가이드 | ✅ |
| skill-evolve | 'skill evolution', '스킬 진화' | 교훈 기반 스킬 개선 제안 | ✅ |
| error-gotcha | 'error gotcha', '에러 회고' | 에러 수정 후 gotcha 자동 추가 | ✅ |
| bot-triage | 'bot down', '봇 장애', 'triage' | 봇 장애 진단/복구 런북 | ✅ |
| e2e-regression | 'e2e 테스트', 'regression test', '회귀테스트', 'smoke test' | 전체 E2E 회귀 테스트 실행 | ✅ |
| gemini-image-gen | '이미지 생성', 'image generation', 'generate image' | Gemini OAuth 기반 이미지 생성 | ✅ |

## 스킬 설치 경로
```
skills/
├── _shared/save-log.py
├── autonomous-skill-proxy/SKILL.md
├── brainstorming-auto/SKILL.md
├── pm-task-dispatch/SKILL.md
├── pm-discussion/SKILL.md
├── weekly-review/SKILL.md
├── retro/SKILL.md
├── performance-eval/SKILL.md
├── engineering-review/SKILL.md
├── safe-modify/SKILL.md
├── failure-detect-llm/SKILL.md
├── growth-analysis/SKILL.md
├── design-critique/SKILL.md
├── quality-gate/SKILL.md
├── harness-audit/SKILL.md
├── loop-checkpoint/SKILL.md
├── create-skill/SKILL.md
├── skill-evolve/SKILL.md
├── error-gotcha/SKILL.md
├── bot-triage/SKILL.md
├── e2e-regression/SKILL.md
└── gemini-image-gen/SKILL.md
```

## 스킬 우선순위 (everything-claude-code 패턴)
1. 하네스 스킬 먼저 (quality-gate, harness-audit)
2. 런북 스킬 (bot-triage)
3. PM 조율 스킬 (pm-task-dispatch, pm-discussion)
4. 회사 활동 스킬 (weekly-review, retro, performance-eval)
5. 조직별 스킬 (engineering-review, growth-analysis, design-critique)
6. 자율화 스킬 (autonomous-skill-proxy, brainstorming-auto, loop-checkpoint)
7. 메타 스킬 (create-skill, skill-evolve, error-gotcha)
8. 테스트/품질 스킬 (e2e-regression)
9. AI 생성 스킬 (gemini-image-gen)

## 스킬 추가 가이드

새 스킬 추가 시 체크리스트:
1. `skills/{name}/SKILL.md` 생성
2. `.claude/skills/{name}` 심볼릭 링크 생성
3. `organizations.yaml`의 `common_skills` 또는 봇별 `preferred_skills`에 추가
4. 이 README 목록 업데이트
5. CLAUDE.md / AGENTS.md / GEMINI.md 스킬 전략 테이블 업데이트

상세 가이드: `skills/create-skill/SKILL.md` 및 `docs/SKILLS_MCP_GUIDE.md`
