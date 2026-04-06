# Cold-start Import Benchmark — Before / After

> 측정일: 2026-04-01
> 환경: macOS Darwin 25.4.0, Python 3.14, `.venv` (telegram-ai-org v1.1.0)
> 도구: `tools/cold_start_benchmark.py`
> 재현 명령: `python tools/cold_start_benchmark.py`

---

## Before: 전체 의존성 일괄 설치 시 Cold-start 비용

> 측정 조건: 모든 의존성 설치 완료 상태에서 각 모듈 fresh import 시간 측정

| Module | Package | import 시간 (ms) | 상태 |
|--------|---------|-----------------|------|
| google.genai | google-genai | **415.8** | 설치됨 |
| mcp | mcp | **233.8** | 설치됨 |
| telegram | python-telegram-bot | **220.6** | 설치됨 |
| openai | openai | **209.2** | 설치됨 |
| anthropic | anthropic | **198.9** | 설치됨 |
| rank_bm25 | rank-bm25 | 50.1 | 설치됨 |
| pydantic | pydantic | 16.2 | 설치됨 |
| loguru | loguru | 14.6 | 설치됨 |
| yaml | PyYAML | 10.1 | 설치됨 |
| aiosqlite | aiosqlite | 5.7 | 설치됨 |
| dotenv | python-dotenv | 2.3 | 설치됨 |
| apscheduler | apscheduler | 2.3 | 설치됨 |
| **TOTAL** | | **1,379.6 ms** | |

### 상위 5개 병목 (Top 5 slowest)

| 순위 | Module | ms | 분류 |
|------|--------|----|------|
| 1 | google.genai | 415.8 | **Optional** (gemini 엔진) |
| 2 | mcp | 233.8 | Core |
| 3 | telegram | 220.6 | Core (필수) |
| 4 | openai | 209.2 | **Optional** (codex 엔진) |
| 5 | anthropic | 198.9 | **Optional** (claude 엔진) |

---

## After: 핵심 의존성만 설치 시 Cold-start 비용 (예상)

> 분석 조건: `requirements.txt`만 설치 (엔진 SDK 제외)
> 제외 패키지: google-genai (415.8 ms), openai (209.2 ms), anthropic (198.9 ms)

| Module | Package | import 시간 (ms) | 상태 |
|--------|---------|-----------------|------|
| mcp | mcp | 233.8 | 설치됨 |
| telegram | python-telegram-bot | 220.6 | 설치됨 |
| rank_bm25 | rank-bm25 | 50.1 | 설치됨 |
| pydantic | pydantic | 16.2 | 설치됨 |
| loguru | loguru | 14.6 | 설치됨 |
| yaml | PyYAML | 10.1 | 설치됨 |
| aiosqlite | aiosqlite | 5.7 | 설치됨 |
| dotenv | python-dotenv | 2.3 | 설치됨 |
| apscheduler | apscheduler | 2.3 | 설치됨 |
| google.genai | google-genai | N/A | 미설치 (optional) |
| openai | openai | N/A | 미설치 (optional) |
| anthropic | anthropic | N/A | 미설치 (optional) |
| **TOTAL** | | **~555.5 ms** | |

---

## 개선 요약

| 지표 | Before | After (예상) | 개선율 |
|------|--------|-------------|--------|
| 전체 cold-start | 1,379.6 ms | ~555.5 ms | **-59.7%** |
| 엔진 SDK 합산 | 823.9 ms | 0 ms | -100% (optional) |
| 디스크 크기 절감 | — | ~26.5 MB | (openai+google-genai+anthropic) |

---

## 최적화 전략

### 1. 엔진 SDK lazy-import 유지
- `anthropic`, `openai`, `google.genai`는 이미 조건부 import (`try/except ImportError`) 패턴 적용됨
- 런타임 cold-start 비용: **0 ms** (미설치 시 import 시도 없음)

### 2. mcp (233.8 ms) — 추가 검토 필요
- MCP는 핵심 의존성이나 import 비용이 높음
- 향후 lazy-import 전환 가능성 검토 권장 (RETRO-28 연계)

### 3. rank-bm25 (50.1 ms) — lazy-import 완료
- `core/memory_manager.py`에서 이미 lazy-import 구현됨
- 메모리 기능 미사용 시 import 0 ms

---

## 재현 방법

```bash
# 벤치마크 실행
python tools/cold_start_benchmark.py

# JSON 출력 (CI 자동화용)
python tools/cold_start_benchmark.py --json

# 프로젝트 내부 모듈 포함
python tools/cold_start_benchmark.py --include-project
```

---

*벤치마크 수치는 CPU 부하·메모리 상태에 따라 ±20% 변동될 수 있음.*
*측정은 `time.perf_counter()` 기반 단회 측정 (평균치 아님).*
