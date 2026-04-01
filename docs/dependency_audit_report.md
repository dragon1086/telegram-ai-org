# Dependency Audit Report — telegram-ai-org v1.1.0

> 작성일: 2026-04-01
> 대상 브랜치: `fix/auto-2026-03-30-telegram_relay`
> Python 버전: 3.14 (`.venv`)
> 기준: `pyproject.toml` [project].dependencies

---

## 1. 핵심 의존성 현황 (Core Dependencies)

| Package | Required Version | Installed | 용도 | 실제 사용 여부 |
|---------|-----------------|-----------|------|--------------|
| python-telegram-bot | >=22.0 | 22.6 | Telegram Bot API | ✅ core/*.py 전역 사용 |
| pydantic | >=2.0 | 2.12.5 | 데이터 검증·settings | ✅ 전역 사용 |
| aiosqlite | >=0.19 | 0.22.1 | async SQLite (GoalTracker) | ✅ core/goal_tracker.py |
| python-dotenv | >=1.0 | (설치됨) | .env 로드 | ✅ 전역 사용 |
| loguru | >=0.7 | 0.7.3 | 구조화 로그 | ✅ 전역 사용 |
| PyYAML | >=6.0 | 6.0.3 | YAML 파싱 | ✅ orchestration.yaml 등 |
| apscheduler | >=3.10.0 | 3.11.2 | 일간 목표 파이프라인 cron | ✅ core/scheduler.py |
| rank-bm25 | >=0.2 | 0.2.2 | MemoryManager BM25 검색 | ✅ lazy-import (core/memory_manager.py) |
| mcp | >=1.0 | 1.26.0 | MCP tool server 연동 | ✅ (조건부 import) |
| claude-agent-sdk | >=0.1.50 | 0.1.50 | ClaudeAgent, COLLAB dispatch | ✅ core/ 전역 |

### 1.1 불필요 의존성 없음

코드베이스 전수 조사 결과 `pyproject.toml`에 선언된 핵심 의존성은 **모두 실제 코드에서 사용**됨.
`rank-bm25`는 `core/memory_manager.py`에서 lazy-import(`from rank_bm25 import BM25Okapi`)로 사용 — 핵심 의존성으로 유지 적절.

---

## 2. 선택 의존성 현황 (Optional / Engine SDK)

| Package | 대상 엔진 | Installed | 실제 사용 위치 | 분류 |
|---------|----------|-----------|--------------|------|
| anthropic | claude-code | 0.84.0 | core/llm_failure_detector.py (조건부) | optional[claude] |
| openai | codex | 2.26.0 | (직접 호출 없음 — codex CLI 경유) | optional[codex] |
| google-genai | gemini-cli | 1.68.0 | core/llm_failure_detector.py, core/artifact_indexer.py (조건부) | optional[gemini] |
| httpx | 공통 | (설치됨) | python-telegram-bot HTTPXRequest 내부 | optional[all] |

### 2.1 엔진 SDK 사용 패턴

- `anthropic`, `openai`, `google.genai` 모두 **조건부(try/except) import** 패턴 사용
- 실제 LLM 호출은 엔진 CLI 바이너리(`claude`, `codex`, `gemini`) 경유 — SDK는 보조 역할
- 따라서 엔진 SDK는 `requirements-optional.txt`로 분리 타당

---

## 3. 패키지 디스크 크기 분석

| Package | 디스크 크기 | 비중 | 최적화 가능성 |
|---------|-----------|------|------------|
| google-genai | 11 MB | 최대 | optional로 분리됨 ✅ |
| openai | 9.6 MB | 2위 | optional로 분리됨 ✅ |
| telegram | 7.5 MB | 3위 | 필수 — 경량화 불가 |
| anthropic | 5.9 MB | 4위 | optional로 분리됨 ✅ |
| pydantic_core | 4.4 MB | 5위 | 필수 (pydantic C 확장) |
| pydantic | 3.9 MB | 6위 | 필수 |
| pydantic_settings | 572 KB | 소 | 필수 |

**총 엔진 SDK 절감 가능 용량**: 약 26.5 MB (openai + google-genai + anthropic)
기본 설치(`requirements.txt`만) 대비 Docker 이미지 크기 ~27 MB 절감 가능.

---

## 4. 개발 의존성 현황 (Dev / Test)

### requirements-test.txt
| Package | 용도 |
|---------|------|
| pytest>=7.0 | 테스트 러너 |
| pytest-asyncio>=0.21 | async 테스트 지원 |
| pytest-mock>=3.0 | Mock 유틸리티 |
| pytest-timeout>=2.1 | 통합 테스트 타임아웃 제어 |

### requirements-dev.txt (test 포함)
| Package | 용도 |
|---------|------|
| ruff>=0.1 | 린터 |
| mypy>=1.10 | 정적 타입 검사 |
| black>=23.0 | 코드 포맷터 |
| flake8>=7.0 | 추가 린팅 |
| build>=1.0 | 패키지 빌드 |
| twine>=5.0 | PyPI 배포 |
| httpx>=0.25 | HTTP 테스트 클라이언트 |
| openai, anthropic, google-genai | 엔진별 통합 테스트 |

---

## 5. 감사 결론

| 항목 | 결과 |
|------|------|
| 미사용 핵심 의존성 | 없음 |
| 핵심/선택 분리 필요 패키지 | anthropic, openai, google-genai → requirements-optional.txt 분리 완료 |
| 잠재적 보안 취약점 | 없음 (최신 stable 버전 사용) |
| Python 버전 호환성 | 3.10+ (pyproject.toml requires-python = ">=3.10") |

---

## 6. 권장 사항

1. **일반 사용자**: `pip install -r requirements.txt` — 엔진 SDK 제외 약 22 MB
2. **개발자**: `pip install -e ".[dev]"` — 전체 의존성 포함
3. **CI/CD**: `pip install -e ".[test]"` — 테스트 전용
4. **Docker**: `requirements.txt` 기반 멀티스테이지 빌드 권장 (기존 Dockerfile 유지)
5. **rank-bm25**: lazy-import 패턴 유지 — 메모리 관련 기능 비활성 시 자동 skip됨

---

*이 보고서는 `tools/cold_start_benchmark.py` 및 `pip show` 출력 기반으로 자동 생성됨.*
