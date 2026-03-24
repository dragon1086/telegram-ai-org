---
name: skill-evolve
description: "스킬 자동 진화 — lesson_memory + eval.json 기반 품질 측정 및 개선 제안. Triggers: '스킬 진화', 'skill evolution', 'evolve skills', '패턴 분석', 'lesson analysis', 'skill improve'"
disable-model-invocation: true
allowed-tools: Bash, Read, Write, Glob, Grep
---

# Skill Evolution (스킬 진화)

교훈 DB에서 반복 패턴을 분석하고, eval 점수 기반으로 스킬 개선안을 도출한다.
eval.json이 있는 스킬은 Karpathy 루프(측정 → 제안 → 재측정 → keep/revert)를 실행한다.

## Step 1: Eval 기반 점수 측정

```python
import sys
sys.path.insert(0, ".")
from core.eval_runner import EvalRunner

runner = EvalRunner()
results = runner.score_all_skills()
print(runner.format_results(results))

# 개선이 필요한 스킬 식별
needs_improvement = [r for r in results if not r.passed]
print(f"\n개선 필요: {[r.skill_name for r in needs_improvement]}")
```

eval.json이 없는 스킬은 Step 2 (교훈 데이터 수집)로 진행.

## Step 2: 교훈 데이터 수집

```python
import sqlite3, json
from collections import Counter
from pathlib import Path
from datetime import datetime, timezone, timedelta

db = Path(".ai-org/lesson_memory.db")
conn = sqlite3.connect(db)

cutoff = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
rows = conn.execute(
    "SELECT category, what_went_wrong, how_to_prevent, outcome, worker, applied_count "
    "FROM lessons WHERE created_at > ? ORDER BY created_at DESC", (cutoff,)
).fetchall()

cat_counts = Counter(r[0] for r in rows)
outcome_counts = Counter(r[3] for r in rows)
worker_counts = Counter(r[4] for r in rows if r[4])

print(f"총 교훈: {len(rows)}")
print(f"카테고리별: {dict(cat_counts)}")
print(f"결과별: {dict(outcome_counts)}")
print(f"봇별: {dict(worker_counts)}")

recurring = {k: v for k, v in cat_counts.items() if v >= 3}
print(f"\n반복 패턴 (3회+): {recurring}")
conn.close()
```

## Step 3: 패턴 분석 및 스킬 개선 제안

수집 데이터를 기반으로 분석:

1. **eval 점수 미달 스킬** — score < 7.0 → SKILL.md 내용 보강
2. **반복 실패 패턴** — 같은 category 3회+ → gotchas.md 항목 추가 또는 스킬 신규 생성
3. **반복 성공 패턴** — 같은 category 3회+ → 스킬로 표준화
4. **봇별 약점** — 특정 봇에 실패 집중 → 봇 전용 가이드 추가

### Karpathy 루프 (eval.json 있는 스킬)

```
score_before = eval_runner.score_skill(skill_name).score
# SKILL.md 개선 적용
score_after = eval_runner.score_skill(skill_name).score

if score_after > score_before:
    print(f"✅ KEEP: {score_before:.1f} → {score_after:.1f}")
    # git commit "skill-improve: {skill_name}"
else:
    print(f"⏪ REVERT: {score_after:.1f} ≤ {score_before:.1f}")
    # git revert
```

### 제안 형식

```markdown
### 제안: {skill-name} 개선
- **현재 점수**: {score_before}/10
- **문제**: {반복 패턴 설명}
- **빈도**: {category}에서 {N}회 발생
- **개선 방향**:
  1. {구체적 수정 내용}
  2. {트리거 키워드 추가}
  3. {gotcha 항목 추가}
- **예상 점수**: {score_estimated}/10
```

## Step 4: 보고서 저장

결과를 `docs/skill-evolution/YYYY-MM-DD-evolution.md`에 저장.

포함 내용:
- 분석 기간
- eval 점수 요약 (스킬별 점수 + 개선 여부)
- 반복 패턴 목록
- 스킬 제안/개선 목록
- keep/revert 결정 근거

## Step 5: 스킬 생성/수정 (승인 시)

- eval 기반 개선: 점수 향상 시 자동 커밋 가능
- 신규 스킬 생성: Rocky 승인 후 `/create-skill {skill-name}`
- 승인 없이 신규 스킬 자동 생성하지 않는다

## 자동 스케줄

scheduler.py에 등록된 야간 자동 실행 (매일 02:00 KST):
- ImprovementBus.collect_signals() → SKILL_STALE 신호 수집
- eval.json 있는 스킬 자동 점수 측정
- 주간 집계 후 Rocky에게 Telegram 보고

매주 일요일 22:00 KST: 전체 skill-evolve 보고서 생성

## Gotchas

- eval.json이 없는 스킬은 정량 측정 불가 → Step 2 패턴 분석으로 대체
- score 측정은 키워드 커버리지 기반이므로 SKILL.md 내용이 풍부할수록 정확
- keep/revert 기준: score_after > score_before (동점이면 revert)
