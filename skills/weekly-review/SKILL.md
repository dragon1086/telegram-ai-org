---
name: weekly-review
description: "Use ONLY when Rocky directly requests a weekly meeting, or on the scheduled Friday 17:00 KST trigger. DO NOT trigger on bot-to-bot department reports or messages containing '주간보고'. Triggers: Rocky saying '주간회의 시작', 'weekly review 시작', 'weekly meeting 시작', scheduled Friday 17:00 KST only"
allowed-tools: Read, Write, Glob
---

# Weekly Review (주간회의 스킬)

AI 조직의 주간회의를 PM이 자율적으로 진행한다.

## ⚠️ 중복 실행 방지 (필수)

스킬 시작 전 반드시 확인:
- 이번 주차(`YYYY-WW`) 회의 로그가 `docs/weekly/YYYY-WW-weekly-meeting.md`에 이미 존재하면 **즉시 중단** — "이번 주 회의는 이미 진행되었습니다." 한 줄만 출력
- 부서 봇이 보낸 메시지(봇 발신자)에 의해 이 스킬이 트리거된 경우 **즉시 중단** — 부서 보고는 수집 대상이지 회의 재기동 신호가 아님

## ⚠️ PM 침묵 원칙 (필수)

- **부서 보고 수신 중 PM은 아무 메시지도 보내지 않는다**
- 각 부서가 응답할 때마다 코멘트, 요약, 감사 인사 등 일체 금지
- **모든 부서(6개) 보고 수신 완료 후** Step 2부터 진행
- 부분 수렴 중간에 종합하면 나머지 부서 보고가 재기동 신호로 오해될 수 있음

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

> 요청 발송 후 모든 부서(6개) 응답 수신까지 PM은 침묵 유지.
> 미응답 부서는 30초 대기 후 "응답 없음"으로 처리하고 Step 2 진행.

### Step 2: 통합 보고서 작성 (모든 부서 수신 완료 후)
수집된 데이터로 주간 보고서 생성:
- 파일: `docs/weekly/YYYY-WW-weekly-report.md`
- 전체 조직 요약 + 부서별 상세

### Step 3: 하이라이트 추출
- 이번주 최대 성과 Top 3
- 해결 필요한 블로커
- 다음주 핵심 목표

### Step 4: Rocky에게 보고
텔레그램으로 주간 요약 전송 (이 때 **처음이자 마지막** PM 메시지)

### Step 5: 로그 저장 (US-203 통합)
주간회의 완료 즉시 결과를 JSONL 로그에 기록한다:

```bash
DATA_DIR="${AI_ORG_DATA_DIR:-$HOME/telegram-ai-org-data}"
python skills/_shared/save-log.py '{"week": "YYYY-WW", "summary": "...", "highlights": [], "blockers": []}' "${DATA_DIR}/skills/weekly-review/data/weekly-log.jsonl"
```

- `week`: ISO 주차 형식 (예: `2026-W12`)
- `summary`: 이번 주 전체 요약 (200자 이내)
- `highlights`: Top 3 성과 목록
- `blockers`: 미해결 블로커 목록
- 저장 경로: `${AI_ORG_DATA_DIR:-$HOME/telegram-ai-org-data}/skills/weekly-review/data/weekly-log.jsonl`
- fcntl.flock으로 원자적 append — 동시 실행 안전

> 이 단계는 선택이 아닌 필수다. Step 4(보고) 직후 반드시 실행한다.

## 자동 스케줄
매주 금요일 17:00 KST 자동 실행 (스케줄러와 연동 시)
