# =============================================================================
# Makefile — telegram-ai-org / AIMesh 편의 명령
#
# 사용 예:
#   make setup        — 원클릭 환경 설정 (install.sh 실행)
#   make dashboard    — 대시보드 서버 기동 (포트 8080)
#   make test         — 전체 테스트 실행
#   make test-dashboard — 대시보드 관련 테스트만 실행
#   make lint         — ruff 린트 실행
#   make clean        — __pycache__, .pyc 파일 정리
# =============================================================================

.PHONY: setup dashboard test test-dashboard lint clean help

# ── 기본 변수 ─────────────────────────────────────────────────────────────────

PYTHON       ?= python3
VENV_DIR     ?= .venv
VENV_PYTHON  := $(VENV_DIR)/bin/python
VENV_PIP     := $(VENV_DIR)/bin/pip
PORT         ?= 8080
PYTEST_OPTS  ?= -v --tb=short

# ── 도움말 ────────────────────────────────────────────────────────────────────

help:
	@echo ""
	@echo "AIMesh 편의 명령"
	@echo "────────────────────────────────────────────"
	@echo "  make setup            원클릭 환경 설정 (install.sh)"
	@echo "  make dashboard        대시보드 서버 기동 (포트 $(PORT))"
	@echo "  make test             전체 테스트 실행"
	@echo "  make test-dashboard   대시보드 관련 테스트만 실행"
	@echo "  make lint             ruff 린트 실행"
	@echo "  make clean            임시 파일 정리"
	@echo "────────────────────────────────────────────"
	@echo "  PORT=8081 make dashboard  포트 변경 예시"
	@echo ""

# ── 환경 설정 ─────────────────────────────────────────────────────────────────

setup:
	@echo ">>> 원클릭 환경 설정 시작..."
	bash install.sh

# ── 대시보드 서버 ─────────────────────────────────────────────────────────────

dashboard:
	@echo ">>> AIMesh Dashboard 기동 — http://localhost:$(PORT)"
	@if [ -f "$(VENV_PYTHON)" ]; then \
		DASHBOARD_PORT=$(PORT) $(VENV_PYTHON) dashboard.py --port $(PORT); \
	else \
		DASHBOARD_PORT=$(PORT) $(PYTHON) dashboard.py --port $(PORT); \
	fi

# ── 테스트 ────────────────────────────────────────────────────────────────────

test:
	@echo ">>> 전체 테스트 실행..."
	@if [ -f "$(VENV_PYTHON)" ]; then \
		$(VENV_PYTHON) -m pytest $(PYTEST_OPTS) tests/; \
	else \
		$(PYTHON) -m pytest $(PYTEST_OPTS) tests/; \
	fi

test-dashboard:
	@echo ">>> 대시보드 관련 테스트 실행..."
	@if [ -f "$(VENV_PYTHON)" ]; then \
		$(VENV_PYTHON) -m pytest $(PYTEST_OPTS) \
			tests/test_dashboard_realtime.py \
			tests/test_dashboard_server.py; \
	else \
		$(PYTHON) -m pytest $(PYTEST_OPTS) \
			tests/test_dashboard_realtime.py \
			tests/test_dashboard_server.py; \
	fi

# ── 린트 ──────────────────────────────────────────────────────────────────────

lint:
	@echo ">>> ruff 린트 실행..."
	@if [ -f "$(VENV_DIR)/bin/ruff" ]; then \
		$(VENV_DIR)/bin/ruff check .; \
	else \
		$(PYTHON) -m ruff check .; \
	fi

# ── 정리 ──────────────────────────────────────────────────────────────────────

clean:
	@echo ">>> 임시 파일 정리..."
	find . -type d -name "__pycache__" -not -path "./.venv/*" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc"       -not -path "./.venv/*" -delete 2>/dev/null || true
	find . -type f -name "*.pyo"       -not -path "./.venv/*" -delete 2>/dev/null || true
	find . -type f -name ".coverage"   -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -not -path "./.venv/*" -exec rm -rf {} + 2>/dev/null || true
	@echo ">>> 정리 완료"
