# Quality Gate — Gotchas

## 1. pip install -e . 작동 안 함
이 프로젝트는 hatchling 설정 미비로 `pip install -e .` 작동 안 함.
새 패키지는 `.venv/bin/pip install <package>` 로 직접 설치.

## 2. ruff 오류수 계산 방법
`ruff check .` 출력의 각 줄이 오류 1개가 아님.
`--statistics` 플래그로 집계하거나 라인 수로 카운트.

## 3. pytest 실행 경로
`pytest tests/` 가 아니라 반드시 `.venv/bin/pytest tests/` 사용.
시스템 pytest는 다른 버전일 수 있음.

## 4. import core 실패 시
`sys.path`에 프로젝트 루트가 없어서 발생.
`PYTHONPATH=. .venv/bin/python -c "import core"` 로 재시도.

## 5. E2E 테스트는 별도
이 스킬은 unit/integration 테스트만 실행.
E2E 테스트(`tests/test_collab_e2e.py` 등)는 실제 봇 토큰 필요.

## ⚠️ 6 [절대 금지]: quality-gate PASS 후 배포/푸시/재기동을 자체 실행하지 말 것
quality-gate는 "배포 가능 여부 판정"만 담당한다. 판정 이후의 배포 행위는 infra 역할 조직 전담.
infra 역할 조직 = `organizations.yaml`에서 `capabilities`에 `infra`가 포함된 조직.
```
quality-gate PASS 이후 infra 역할 조직을 제외한 모든 specialist 조직이 해서는 안 되는 행위:
  - git push origin <branch>   → infra 역할 조직 위임 (또는 PM 명시 지시 시 예외)
  - git merge <branch>         → infra 역할 조직 위임 (또는 PM 명시 지시 시 예외)
  - 봇 재기동 명령 실행          → infra 역할 조직 위임 (또는 PM 명시 지시 시 예외)
```
quality-gate 완료 리포트 마지막에는 반드시 다음을 추가:
"→ 배포/머지/재기동이 필요하면 infra 역할 조직에 COLLAB 위임 요청하세요."

## Gotcha 1: enable_* 기본값 변경 후 테스트 미갱신 → AssertionError
**날짜**: 2026-03-30
**에러 유형**: `AssertionError`
**발생 파일**: `tests/test_pm_intercept.py,tests/unit/test_phase1_task_repository.py`
**상황**: AssertionError 오류 발생 시
**증상**: `AssertionError` — enable_* 기본값을 0→1로 변경했을 때 '기본값=0'을 검증하는 테스트가 잔존
**해결**: 기본값 변경 시 해당 기본값을 검증하는 기존 테스트도 함께 업데이트할 것

## Gotcha 2: gotchas.md 혼합 포맷 → 테스트 실패
**날짜**: 2026-03-31
**에러 유형**: `AssertionError`
**발생 파일**: `tests/test_skills.py::TestUS201GotchasFiles::test_gotchas_have_minimum_content`
**상황**: error-gotcha 스킬이 `## Gotcha X:` 형식으로 항목을 추가할 때, 기존 파일이 `## 1.` 번호 형식을 사용하면 테스트가 `## Gotcha` 카운트만 세어 1개로 판정
**증상**: `AssertionError: quality-gate/gotchas.md에 Gotcha가 1개뿐 (최소 3개 필요)`
**해결**: gotchas.md 파일에 `## Gotcha` 형식 항목을 최소 3개 이상 유지. error-gotcha 스킬 실행 후 항상 `## Gotcha` 카운트 확인

## Gotcha 3: worktree에서 design-baseline.yaml 누락 → E2E 수집 단계 SystemExit
**날짜**: 2026-03-31
**에러 유형**: `SystemExit`
**발생 파일**: `tests/e2e/conftest.py::_run_design_preflight`
**상황**: git worktree로 체크아웃한 디렉토리에 `config/design-baseline.yaml`이 없을 때 `run_design_preflight_checks`가 `passed=False`를 반환하고 `skipped` 키가 없어 SystemExit 발생
**증상**: pytest 수집 단계에서 `SystemExit: ❌ design pre-flight 실패` — 모든 E2E 테스트 차단
**해결**: `SKIP_DESIGN_PREFLIGHT=1` 환경변수로 우회. 또는 worktree에 `config/design-baseline.yaml` 심볼릭 링크 생성. 근본 수정은 design_preflight_check.py에서 파일 미존재 시 `skipped=True` 반환
