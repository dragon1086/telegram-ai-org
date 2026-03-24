---
name: weekly-review
description: "Use every Friday or when a weekly progress summary is needed. Collects status from all department bots and generates a weekly report. Triggers: '주간회의', 'weekly review', 'weekly meeting', '주간보고', 'weekly', every Friday at 17:00 KST"
allowed-tools: Read, Write, Glob
---

# Weekly Review (주간회의 스킬)

AI 조직의 주간회의를 PM이 자율적으로 진행한다.

## 절차 (자율 실행, 사람 개입 없음)

### Step 1: 데이터 수집 (병렬)
모든 부서 봇에게 동시에 요청:
```
[주간보고 요청] {날짜} 주차
다음을 200자 이내로 작성:
1. 이번주 주요 완료 사항
2. 진행중인 작업
3. 블로커/이슈
4. 다음주 계획
```

### Step 2: 통합 보고서 작성
수집된 데이터로 주간 보고서 생성:
- 파일: `docs/weekly/YYYY-WW-weekly-report.md`
- 전체 조직 요약 + 부서별 상세

### Step 3: 하이라이트 추출
- 이번주 최대 성과 Top 3
- 해결 필요한 블로커
- 다음주 핵심 목표

### Step 4: Rocky에게 보고
텔레그램으로 주간 요약 전송

### Step 5: 로그 저장 (US-203 통합)
주간회의 완료 즉시 결과를 JSONL 로그에 기록한다:

```bash
python skills/_shared/save-log.py '{"week": "YYYY-WW", "summary": "...", "highlights": [], "blockers": []}' ../telegram-ai-org-data/skills/weekly-review/data/weekly-log.jsonl
```

- `week`: ISO 주차 형식 (예: `2026-W12`)
- `summary`: 이번 주 전체 요약 (200자 이내)
- `highlights`: Top 3 성과 목록
- `blockers`: 미해결 블로커 목록
- 저장 경로: `../telegram-ai-org-data/skills/weekly-review/data/weekly-log.jsonl` (외부 산출물 루트)
- fcntl.flock으로 원자적 append — 동시 실행 안전

> 이 단계는 선택이 아닌 필수다. Step 4(보고) 직후 반드시 실행한다.

## 자동 스케줄
매주 금요일 17:00 KST 자동 실행 (스케줄러와 연동 시)
