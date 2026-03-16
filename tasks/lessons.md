# 프로젝트 레슨 (누적)

Claude Code 세션 시작 시 이 파일을 읽어 과거 실수를 반복하지 않는다.

---

## [2026-03-16] 봇 재시작 전 패키지 sync

**증상**: 소스 수정 후 봇 재시작 → `ModuleNotFoundError: No module named 'aiosqlite'` 반복 크래시 → 텔레그램 봇 전체 무응답

**원인**: `pyproject.toml`에 의존성이 선언되어 있어도 venv에 자동 반영되지 않음. `pip install -e .`를 실행해야 sync됨.

**해결**: `.venv/bin/pip install -e . --quiet` 후 재시작

**적용 규칙**: 소스 수정 + 재시작 작업 순서는 항상
1. 코드 수정
2. `.venv/bin/pip install -e . --quiet`
3. `bash scripts/start_all.sh`
