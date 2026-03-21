# Skill System Refactoring — Revised Plan (v2)
> Date: 2026-03-21
> Status: CONSENSUS REACHED (Architect + Critic ITERATE → Revised)

## RALPLAN-DR Summary

### Principles
1. **Single Responsibility** — 한 스킬이 하나의 명확한 역할
2. **Log Consistency** — 모든 워크플로 스킬은 JSONL 로그 저장
3. **Guardrail by Default** — On Demand Hooks로 자동 품질 검증
4. **Incident-Driven Runbook** — 실제 장애 경험에서 런북 추출
5. **DRY (Don't Repeat Yourself)** — 공유 유틸은 한 곳에

### Decision Drivers
1. 오늘 봇 장애 재발 방지 — bot-triage 런북이 가장 긴급
2. 자동 품질 검증 누락 — quality-gate hooks 필요
3. 로그 일관성 격차 — retro에 JSONL 로그 없음

### Architect/Critic Feedback 반영사항
- ~~PreToolUse:Write~~ → **PostToolUse:Write + ruff-only** (전체 run.sh는 deadlock 위험)
- ~~harness-audit 분할~~ → **--scope infra|code|all 파라미터** (YAGNI)
- ~~save-log.py 복제~~ → **skills/_shared/save-log.py 공유 유틸**

---

## Task 1: bot-triage Runbook 스킬 신규 생성
> 카테고리: Runbook | 복잡도: MEDIUM

- [ ] `skills/bot-triage/SKILL.md` — 봇 장애 진단/복구 절차
- [ ] `skills/bot-triage/gotchas.md` — 초기 gotcha
- [ ] `skills/bot-triage/scripts/diagnose.sh` — 자동 진단 스크립트
- [ ] `skills/bot-triage/templates/incident-report.md` — 인시던트 보고서 템플릿
- [ ] `.claude/skills/bot-triage` → symlink

## Task 2: quality-gate에 PostToolUse:Write Hook 추가
> 카테고리: Code Quality | 복잡도: LOW

- [ ] `skills/quality-gate/SKILL.md` — frontmatter에 hooks 추가
- [ ] `skills/quality-gate/scripts/lint-only.sh` — ruff-only 경량 스크립트

## Task 3: retro 스킬에 실행 로그 저장 추가
> 카테고리: Workflow Automation | 복잡도: LOW

- [ ] `skills/_shared/save-log.py` — 공유 JSONL append 유틸
- [ ] `skills/retro/SKILL.md` — Step 5 로그 저장 단계 추가
- [ ] `skills/weekly-review/SKILL.md` — save-log.py 경로 업데이트

## Task 4: harness-audit에 --scope 파라미터 추가
> 카테고리: Infrastructure Ops + Code Quality | 복잡도: LOW

- [ ] `skills/harness-audit/SKILL.md` — $ARGUMENTS 기반 scope 분기

## 부수 작업
- [ ] `skills/README.md` — bot-triage 추가
- [ ] `error-gotcha/gotchas.md` — 초기 gotcha 파일 생성
- [ ] `create-skill/gotchas.md` — 초기 gotcha 파일 생성
