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
