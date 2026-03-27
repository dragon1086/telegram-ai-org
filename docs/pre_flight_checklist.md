# Pre-flight 자동화 체크리스트 (RETRO-01)

> 작성: 개발실 | 2026-03-27
> 목적: E2E 테스트 실행 전 인프라/환경 상태를 자동 검증하여 timeout·filter·env 문제로 인한 false failure를 방지한다.

---

## 1. 사용법

```bash
# 기본 실행 (모든 체크)
.venv/bin/python scripts/preflight_check.py

# 특정 카테고리만
.venv/bin/python scripts/preflight_check.py --category env
.venv/bin/python scripts/preflight_check.py --category timeout
.venv/bin/python scripts/preflight_check.py --category model

# JSON 출력 (CI 파이프라인 연동용)
.venv/bin/python scripts/preflight_check.py --format json

# E2E 실행 전 자동 검증 (실패 시 E2E 스킵)
.venv/bin/python scripts/preflight_check.py --fail-fast && .venv/bin/pytest tests/e2e/
```

---

## 2. 체크 항목

### 2.1 환경 변수 (category: env)

| 항목 | 체크 내용 | 실패 시 |
|------|-----------|---------|
| `ANTHROPIC_API_KEY` | 존재 여부 + 비어있지 않음 | ERROR — Claude 엔진 불가 |
| `TELEGRAM_BOT_TOKEN` or `PM_BOT_TOKEN` | 존재 여부 | WARN — 봇 실행 불가 |
| `TELEGRAM_GROUP_CHAT_ID` | 정수값 여부 | ERROR — 채팅방 연결 불가 |
| `GOOGLE_CLOUD_PROJECT` | 존재 여부 | WARN — Gemini CLI 제한 |
| `.env` 파일 존재 | 프로젝트 루트 | WARN — 환경변수 누락 가능 |

### 2.2 타임아웃 설정 (category: timeout)

| 항목 | 기준값 | 체크 내용 |
|------|--------|-----------|
| E2E 테스트 `--timeout` | ≥120s | pytest.ini 또는 conftest.py 확인 |
| `PM_CHAT_REPLY_TIMEOUT_SEC` | ≥120 | 환경변수 또는 기본값 확인 |
| Claude subprocess timeout | ≥300s | claude_subprocess_runner.py 확인 |
| TaskPoller polling interval | ≤30s | context_db.py 설정 확인 |

### 2.3 모델 버전 (category: model)

| 항목 | 체크 내용 | 실패 시 |
|------|-----------|---------|
| `gemini-2.0-flash` 사용 | core/ + scripts/ 에서 탐지 | FAIL — deprecated 모델 |
| `gemini-3.x-preview` 사용 | core/ + scripts/ 에서 탐지 | WARN — GA 아님, 프로덕션 미권장 |
| 기본 모델이 존재하는지 | API 조회 또는 설정 파일 확인 | ERROR — 모델 응답 불가 |

### 2.4 인프라 파일 (category: infra)

| 항목 | 체크 내용 |
|------|-----------|
| `infra-baseline.yaml` | 존재 여부 + YAML 파싱 가능 |
| `orchestration.yaml` | 존재 여부 + 스키마 검증 |
| `organizations.yaml` | 존재 여부 + organizations 배열 유효 |
| `.venv/` | 가상환경 활성화 여부 |
| `tasks.db` | SQLite 접속 가능 여부 |

### 2.5 프로세스 (category: process)

| 항목 | 체크 내용 |
|------|-----------|
| tmux 설치 | `which tmux` 확인 |
| claude-code CLI | `which claude` 확인 |
| 충돌 포트 | 봇 프로세스 중복 실행 여부 |

---

## 3. 체크 결과 해석

```
✅ PASS  — 정상
⚠️ WARN  — 기능 제한될 수 있으나 실행 가능
❌ FAIL  — 즉시 수정 필요, E2E 실행 불가
💥 ERROR — 예외 발생, 체크 자체 실패
```

**WARN이 있어도 E2E는 실행**. FAIL/ERROR 가 있으면 E2E 스킵 권장.

---

## 4. CI/CD 연동

`.github/workflows/ci.yml`에 pre-flight 단계 추가:

```yaml
- name: Pre-flight check
  run: |
    .venv/bin/python scripts/preflight_check.py --format json > preflight_result.json
    .venv/bin/python scripts/preflight_check.py --fail-fast
  continue-on-error: false
```

---

## 5. E2E 로그 헤더 자동 삽입

`scripts/preflight_check.py --inject-header`를 E2E 시작 전에 실행하면
로그 파일 상단에 환경 스냅샷이 자동 삽입된다:

```
=== PRE-FLIGHT SNAPSHOT ===
date: 2026-03-27T09:00:00+09:00
infra_baseline_version: v1.2.0
python_version: 3.11.8
model: gemini-2.5-flash
timeout_sec: 120
env_hash: sha256:abc123
===========================
```

이를 통해 실패 원인이 "코드 버그인지" "인프라 환경 문제인지" 즉시 구분 가능.

---

## 6. 자동화 스크립트 위치

- **메인 스크립트**: `scripts/preflight_check.py`
- **쉘 래퍼**: `scripts/preflight_check.sh`
- **Python 모듈**: `tools/preflight_check.py` (pm_orchestrator에서 직접 호출 가능)
- **결과 로그**: `logs/preflight/YYYY-MM-DD.log`

---

## 관련 항목
- RETRO-02: 환경 격리 디버깅 가이드
- `infra/infra-baseline.yaml`: 인프라 파라미터 명세
- `docs/REFACTORING_PLAN.md`: 코드베이스 리팩토링 계획
