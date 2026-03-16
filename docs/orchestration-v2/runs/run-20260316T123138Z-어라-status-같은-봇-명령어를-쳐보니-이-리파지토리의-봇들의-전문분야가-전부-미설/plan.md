# planning

## Request
어라.'/status'같은 봇 명령어를 쳐보니, 이 리파지토리의 봇들의 전문분야가 전부 미설정인 것으로 보여. 아마 파싱문제인 것 같아. 파싱 제대로 되게 해결해줘

## Note
요청 접수 후 planning phase로 이동

## Planning brief
- at: 2026-03-16T12:33:53.733379+00:00

🧭 PM 실행 계획
- 처리 방식: PM 직접 실행
- 요청 요약: 어라.'/status'같은 봇 명령어를 쳐보니, 이 리파지토리의 봇들의 전문분야가 전부 미설정인 것으로 보여. 아마 파싱문제인 것 같아. 파싱 제대로 되게 해결해줘
- 실행 런타임: Claude Code / sequential / resume_session
🤖 팀 구성 완료
  엔진: Claude Code
  팀: CONTRIBUTING×1
  전략 모드: sequential
💡 이유: keyword/profile-based fallback (LLM unavailable)
🧰 권장 내장 Surface
- ./.venv/bin/python tools/orchestration_cli.py validate-config: 오케스트레이션 설정 검증과 조직/런북 상태 확인
- bash scripts/bot_control.sh status all: 봇 프로세스 상태 확인과 재기동
🛰️ 체크포인트: 요청 파악 → 실행 → 결과 정리
