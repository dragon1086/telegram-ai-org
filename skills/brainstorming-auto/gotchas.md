# Brainstorming Auto — Gotchas

이 스킬을 사용할 때 자주 발생하는 실수와 주의사항이다.

## Gotcha 1: 컨텍스트 없이 3가지 방안 생성 시 모두 generic
**상황**: CLAUDE.md, AGENTS.md, 관련 코어 파일을 읽지 않고 바로 설계 방안을 생성할 때
**증상**: "마이크로서비스 vs 모놀리식 vs 서버리스" 같은 프로젝트 무관한 보편 비교가 나옴. telegram-ai-org 특유의 봇 아키텍처, workers.yaml 구조, async 패턴이 반영되지 않음
**해결**: Step 1(컨텍스트 수집)을 반드시 완료 후 Step 2로 진행. `core/pm_orchestrator.py`, `workers.yaml`, `orchestration.yaml` 을 읽어 현재 아키텍처 파악 후 방안을 생성한다

## Gotcha 2: 설계 문서 저장 경로 오류로 파일 유실
**상황**: `docs/plans/` 디렉토리가 존재하지 않는 상태에서 자동 저장할 때
**증상**: FileNotFoundError 없이 조용히 실패하거나, 프로젝트 루트에 엉뚱한 경로로 파일이 생성됨. 이후 재개 시 설계 문서를 찾지 못해 처음부터 재설계함
**해결**: 저장 전 `docs/plans/` 디렉토리 존재 여부 확인. 없으면 먼저 생성(`mkdir -p docs/plans`). 파일명은 `YYYY-MM-DD-<topic>-design.md` 형식 준수

## Gotcha 3: prd.json 분해 시 async 패턴 무시
**상황**: 구현 계획을 태스크로 분해할 때 기존 코드베이스의 async 구조를 고려하지 않을 때
**증상**: 생성된 스토리가 동기 함수로 설계되어 실제 구현 시 `core/pm_orchestrator.py`의 asyncio 루프와 충돌. 구현자가 전면 재설계해야 함
**해결**: 방안 생성 전 `core/` 디렉토리의 주요 파일에서 `async def` 패턴 확인. 분해된 스토리에 "async 함수로 구현" 조건을 명시

## Gotcha 4: 사용자 승인 없이 진행하다 잘못된 방향 고착
**상황**: 자율 모드에서 권장 방안을 자동 선택하고 곧바로 구현 계획까지 생성할 때
**증상**: 초기 가정이 틀렸음에도 멈추지 않고 계속 진행. Rocky가 나중에 방향 자체가 잘못됐음을 발견해 전체 재작업 발생
**해결**: 권장 방안 선택 근거를 설계 문서에 명확히 기록. `.omc/checkpoint.json`에 "방향 결정: {근거}" 저장 후 Telegram으로 Rocky에게 요약 통보(비동기, 블로킹 아님)
