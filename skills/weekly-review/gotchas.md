# Weekly Review — Gotchas

## 1. 봇 응답 대기 시간
각 봇의 응답을 수집할 때 충분한 대기 시간 필요.
봇이 바쁜 경우 응답이 늦을 수 있으므로 30초 이상 대기.

## 2. 이전 보고서 참조 필수
같은 내용을 반복 보고하지 않으려면 `../telegram-ai-org-data/skills/weekly-review/data/weekly-log.jsonl`의
이전 주 보고서를 반드시 읽고 "지난주 대비 변화"를 파악할 것.

## 3. 빈 보고는 금지
봇이 응답 없을 경우 "응답 없음"으로 명시.
빈 섹션을 그냥 두지 말 것.

## 4. YYYY-WW 형식
주차 번호는 ISO 8601 기준.
Python: `datetime.now().strftime("%Y-W%W")` 또는 `%G-W%V`.

## 5. 저장 경로
보고서는 `docs/weekly/YYYY-WW-weekly-report.md` 저장.
`../telegram-ai-org-data/skills/weekly-review/data/weekly-log.jsonl`에 JSON 한 줄 추가 (기계 가독용, 외부 산출물 루트).
