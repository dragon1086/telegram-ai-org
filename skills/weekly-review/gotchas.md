# Weekly Review — Gotchas

## 1. 봇 응답 대기 시간
각 봇의 응답을 수집할 때 충분한 대기 시간 필요.
봇이 바쁜 경우 응답이 늦을 수 있으므로 30초 이상 대기.

## 2. 이전 보고서 참조 필수
같은 내용을 반복 보고하지 않으려면 `${AI_ORG_DATA_DIR:-$HOME/telegram-ai-org-data}/skills/weekly-review/data/weekly-log.jsonl`의
이전 주 보고서를 반드시 읽고 "지난주 대비 변화"를 파악할 것.

## 3. 빈 보고는 금지
봇이 응답 없을 경우 "응답 없음"으로 명시.
빈 섹션을 그냥 두지 말 것.

## 4. YYYY-WW 형식
주차 번호는 ISO 8601 기준.
Python: `datetime.now().strftime("%Y-W%W")` 또는 `%G-W%V`.

## 5. 저장 경로
보고서는 `docs/weekly/YYYY-WW-weekly-report.md` 저장.
`${AI_ORG_DATA_DIR:-$HOME/telegram-ai-org-data}/skills/weekly-review/data/weekly-log.jsonl`에 JSON 한 줄 추가 (기계 가독용, 외부 산출물 루트).

## 6. ❌ PM 중간 코멘트 금지 (신규)
부서 보고가 들어올 때마다 PM이 "감사합니다", "잘 받았습니다", 요약 코멘트 등을 보내면
나머지 부서들이 회의 재기동 신호로 오인해 중복 회의가 발생한다.
**PM 메시지는 Step 4 최종 종합 보고 1회만 허용.**

## 7. ❌ 부서 응답이 회의 재기동하는 문제 (신규)
부서 봇 응답에 "주간보고", "이번 주 완료" 등 키워드가 포함되면
weekly-review 스킬이 다시 트리거될 수 있다.
**트리거 조건은 Rocky 직접 요청 또는 금요일 스케줄만 허용.**
봇 발신 메시지로 이 스킬이 호출됐다면 즉시 중단.

## 8. ❌ 같은 주차 중복 실행 방지 (신규)
`docs/weekly/YYYY-WW-weekly-meeting.md` 파일이 이미 존재하면
이번 주 회의는 완료된 것이므로 **재실행하지 않는다.**
