---
name: retro
description: "Use after completing a sprint, project, or major milestone to run a structured retrospective. Collects Start/Stop/Continue and 5-Whys from all bots. Triggers: '회고', 'retro', 'retrospective', 'post-mortem', after sprint end or project completion"
---

# Retro (회고 스킬)

완료된 스프린트나 프로젝트에 대한 구조적 회고를 자율 진행한다.

## 회고 구조 (Start/Stop/Continue + 5 Whys)

### Step 1: 각 봇에게 회고 요청
```
[회고] {스프린트/프로젝트명}
다음 형식으로 작성:
START: 앞으로 시작해야 할 것
STOP: 그만해야 할 것
CONTINUE: 계속해야 할 것
BLOCKER: 근본 원인 (5 Whys 적용)
```

### Step 2: 패턴 분석
- 반복되는 문제 식별
- 5 Whys로 근본 원인 탐구
- 개선 액션 아이템 도출

### Step 3: 액션 아이템 배분
- 각 개선 과제를 담당 봇에 배분
- CLAUDE.md 운영 주의사항에 새 레슨 추가

### Step 4: 회고 보고서 저장
- 파일: `docs/retros/YYYY-MM-DD-retro.md`
- Rocky에게 요약 보고

### Step 5: 로그 저장
회고 완료 즉시 결과를 JSONL 로그에 기록한다:

```bash
python skills/_shared/save-log.py '{"date": "YYYY-MM-DD", "sprint": "...", "summary": "...", "action_items": [], "patterns": []}' skills/retro/data/retro-log.jsonl
```

- `date`: 회고 실행 날짜
- `sprint`: 스프린트/프로젝트 식별자
- `summary`: 전체 요약 (200자 이내)
- `action_items`: 도출된 액션 아이템 목록
- `patterns`: 반복 패턴 목록
- 저장 경로: `skills/retro/data/retro-log.jsonl`
- fcntl.flock으로 원자적 append — 동시 실행 안전

> 이 단계는 선택이 아닌 필수다. Step 4(보고서 저장) 직후 반드시 실행한다.
