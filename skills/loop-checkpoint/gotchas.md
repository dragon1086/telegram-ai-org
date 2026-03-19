# Loop Checkpoint — Gotchas

이 스킬을 사용할 때 자주 발생하는 실수와 주의사항이다.

## Gotcha 1: checkpoint.json 저장 후 files_modified 목록 누락
**상황**: 체크포인트 저장 시 `files_modified` 필드를 빈 배열 또는 생략할 때
**증상**: 재개 후 이미 수정된 파일을 다시 수정해 충돌 발생. 또는 부분 수정된 파일을 "미수정"으로 간주해 덮어씀
**해결**: 체크포인트 저장 직전 `git diff --name-only` 또는 수정 파일 추적 변수를 통해 실제 수정된 파일 목록을 `files_modified`에 기록. 재개 시 이 목록을 먼저 확인

## Gotcha 2: 재개 시 completed_stories 스킵 없이 재실행
**상황**: `.omc/checkpoint.json` 을 읽었지만 `completed_stories` 확인 없이 처음 스토리부터 재실행할 때
**증상**: 이미 완료된 US-001, US-002를 재실행해 중복 처리(파일 이중 수정, DB 중복 삽입 등) 발생. 디버깅에 재작업보다 더 많은 시간 소요
**해결**: 재개 루프 시작 시 반드시 `completed_stories` 목록 로드 → 현재 스토리가 목록에 있으면 스킵 → `next_action` 부터 실행 순서 준수. 재개 시작 로그에 "스킵된 스토리: [US-001, US-002]" 명시

## Gotcha 3: 30분 자동 체크포인트가 오류 발생 후에도 저장
**상황**: 오류 상태에서 30분 타이머가 만료돼 체크포인트가 자동 저장될 때
**증상**: 오류 상태의 `next_action`이 체크포인트에 저장됨. 재개 시 같은 오류 지점부터 시작해 무한 오류 루프
**해결**: 자동 체크포인트 저장 전 현재 상태가 정상인지 확인. 오류 발생 시에는 `next_action`을 오류 발생 스토리의 시작 지점으로 설정하고 `error_context` 필드에 오류 내용 기록. 재개 시 `error_context` 있으면 Rocky에게 먼저 보고

## Gotcha 4: context_summary를 너무 길게 작성해 재개 시 컨텍스트 초과
**상황**: `context_summary` 필드에 전체 진행 상황을 상세히 기술할 때
**증상**: checkpoint.json 파일 자체는 정상이지만 재개 에이전트가 context_summary를 읽으면서 컨텍스트 윈도우 상당 부분을 소비. 이후 실제 구현에 쓸 컨텍스트 부족
**해결**: `context_summary`는 200자 이내로 제한. "완료: 인증 모듈 / 진행 중: 라우팅 로직 / 다음: 테스트 작성" 수준으로 핵심만 기술. 상세 내용은 별도 `docs/plans/` 문서 참조
