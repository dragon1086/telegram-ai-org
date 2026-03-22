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
