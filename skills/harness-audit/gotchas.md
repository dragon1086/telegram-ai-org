# Harness Audit — Gotchas

이 스킬을 사용할 때 자주 발생하는 실수와 주의사항이다.

## Gotcha 1: 봇 상태를 프로세스 존재 여부로만 확인
**상황**: `ps aux | grep bot` 으로 프로세스가 살아있는지만 확인할 때
**증상**: 프로세스는 있지만 봇 토큰 만료, Telegram API 연결 실패, asyncio 루프 행(hang) 상태 감지 못 함. "봇 상태: ✅"로 보고했지만 실제로는 메시지를 처리하지 않는 좀비 상태
**해결**: 봇 상태 확인은 프로세스 존재 + 최근 로그 타임스탬프(5분 이내 활동) + 토큰 유효성(`logs/` 에서 `Unauthorized` 오류 여부) 3가지 병행. `logs/` 에 최근 에러가 없는지 확인

## Gotcha 2: pyproject.toml과 실제 venv 패키지 비교 시 버전 무시
**상황**: 의존성 건강도 확인 시 패키지 이름만 대조하고 버전을 무시할 때
**증상**: `pyproject.toml`에 `python-telegram-bot>=20.0` 이 있고 venv에 `20.7` 이 설치돼 "정합성 OK"로 보고. 실제로는 `20.7`에 알려진 버그가 있거나 `21.x` 필요한 코드가 존재
**해결**: `.venv/bin/pip list --format=freeze` 출력과 `pyproject.toml` 요구 버전 범위를 버전 단위로 대조. 버전 범위 위반 패키지만 별도 표시

## Gotcha 3: .ai-org/runs/ 미완료 run 수 계산 시 진행 중인 run도 포함
**상황**: `.ai-org/runs/` 디렉토리의 미완료 run을 집계할 때
**증상**: 현재 실행 중인 autonomous run이 "미완료"로 집계돼 리스크 레벨이 불필요하게 HIGH로 판정됨. 실제로는 정상 진행 중
**해결**: 미완료 판정 기준 명확화 — 타임스탬프가 24시간 이상 지났으나 완료 마커(`DONE`, `completed` 등)가 없는 run만 미완료로 분류. 현재 시각 기준 1시간 이내 run은 "진행 중"으로 별도 표시

## Gotcha 4: 문서 정합성 확인 없이 "문서 최신" 보고
**상황**: CLAUDE.md, AGENTS.md 파일 수정 날짜만 확인하고 내용 정합성은 검토하지 않을 때
**증상**: `core/pm_identity.py`에 새 봇 역할이 추가됐지만 AGENTS.md에 미반영된 상태를 탐지 못 함. 신규 팀원(봇)이 잘못된 역할 기술을 기반으로 행동
**해결**: 코드 변경 이력(`git log --since="7 days ago" -- core/`)과 문서 변경 이력을 비교. `workers.yaml`의 봇 목록과 `AGENTS.md` 봇 섹션이 일치하는지 수동 대조 포함

## Gotcha 5: skills/ 인벤토리와 organizations.yaml 정합성 확인 누락
**상황**: 스킬 인벤토리 확인 시 `skills/` 디렉토리 목록만 출력하고 organizations.yaml 대조를 생략할 때
**증상**: `skills/` 에는 있지만 `organizations.yaml` `preferred_skills` 에 등록 안 된 스킬이 자율 에이전트에 의해 무시됨. 반대로 yaml에 등록됐지만 SKILL.md가 없는 스킬 참조 시 에러
**해결**: `skills/` 디렉토리 목록 ↔ 각 조직 `preferred_skills` 양방향 대조 필수. 불일치 항목을 감사 보고서 "스킬 정합성" 섹션에 명시
