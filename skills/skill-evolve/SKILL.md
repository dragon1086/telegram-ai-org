---
name: skill-evolve
description: "Analyze accumulated lessons from lesson_memory DB, detect recurring patterns, and propose new skills or skill improvements. Triggers: '스킬 진화', 'skill evolution', 'evolve skills', '패턴 분석', 'lesson analysis'"
disable-model-invocation: true
---

# Skill Evolution (스킬 진화)

교훈 DB에서 반복 패턴을 분석하고, 새 스킬 제안 또는 기존 스킬 개선안을 도출한다.

## Step 1: 교훈 데이터 수집

아래 Python 코드를 실행하여 데이터를 수집하라:

```python
import sqlite3, json
from collections import Counter
from pathlib import Path
from datetime import datetime, timezone, timedelta

db = Path(".ai-org/lesson_memory.db")
conn = sqlite3.connect(db)

# 최근 14일 교훈 전체
cutoff = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
rows = conn.execute(
    "SELECT category, what_went_wrong, how_to_prevent, outcome, worker, applied_count "
    "FROM lessons WHERE created_at > ? ORDER BY created_at DESC", (cutoff,)
).fetchall()

# 카테고리별 통계
cat_counts = Counter(r[0] for r in rows)
outcome_counts = Counter(r[3] for r in rows)
worker_counts = Counter(r[4] for r in rows if r[4])

print(f"총 교훈: {len(rows)}")
print(f"카테고리별: {dict(cat_counts)}")
print(f"결과별: {dict(outcome_counts)}")
print(f"봇별: {dict(worker_counts)}")

# 반복 패턴 감지 (같은 카테고리 3회 이상)
recurring = {k: v for k, v in cat_counts.items() if v >= 3}
print(f"\n반복 패턴 (3회+): {recurring}")

# 적용된 교훈 효과
applied = [r for r in rows if r[5] > 0]
print(f"적용된 교훈: {len(applied)}개")
conn.close()
```

## Step 2: 패턴 분석

수집 데이터를 기반으로 분석:

1. **반복 실패 패턴** — 같은 category 실패가 3회+ → 스킬로 방지 가능
2. **반복 성공 패턴** — 같은 category 성공이 3회+ → 스킬로 표준화 가능
3. **봇별 약점** — 특정 봇에 실패가 집중 → 봇 전용 가이드 스킬
4. **교훈 미적용** — applied_count=0 교훈이 많으면 → briefing 개선 필요

## Step 3: 스킬 제안 생성

각 반복 패턴에 대해:

1. 패턴 요약 (어떤 문제가 반복되는가)
2. 제안 스킬명 (kebab-case)
3. 스킬 유형 (reference / task / fork)
4. 스킬 내용 초안 (핵심 규칙 3-5개)
5. 기존 스킬과 중복 확인

### 제안 형식

```markdown
### 제안 1: {skill-name}
- **문제**: {반복 패턴 설명}
- **빈도**: {category}에서 {N}회 발생
- **유형**: reference
- **핵심 규칙**:
  1. ...
  2. ...
  3. ...
- **중복 검사**: 기존 {skill} 스킬과 겹치지 않음
```

## Step 4: 보고서 저장

결과를 `docs/skill-evolution/YYYY-MM-DD-evolution.md`에 저장.

포함 내용:
- 분석 기간
- 교훈 통계 요약
- 반복 패턴 목록
- 스킬 제안 목록
- 기존 스킬 개선 제안 (해당 시)

## Step 5: 스킬 생성 (승인 시)

Rocky가 제안을 승인하면 `/create-skill {skill-name}` 으로 실제 스킬 생성.
승인 없이 자동 생성하지 않는다 — 제안까지만 자율.

## 자동 스케줄 (cron)

매주 일요일 21:00 KST에 자동 실행:
```
cokacdir --cron "lesson_memory DB에서 최근 7일 교훈을 분석하고, 반복 패턴을 찾아 새 스킬 제안 보고서를 작성해서 Rocky에게 보고하라. /skill-evolve 스킬을 참조하라." --at "0 12 * * 0" --chat {CHAT_ID} --key {KEY}
```
