# 환경 격리 디버깅 가이드 (RETRO-02)

> **목적**: 테스트/운영 실패 발생 시 "코드 버그인가, 인프라 문제인가"를 **5분 안에** 판별하는 실전 가이드.
> **대상 독자**: 개발실, 운영실, QA 엔지니어
> **작성일**: 2026-03-27 (RETRO-02)
> **관련 문서**: `docs/ENV_ISOLATION_DEBUG_GUIDE.md` (상세 플로우), `infra-baseline.yaml` (기준 파라미터)

---

## 1. 코드 vs 인프라 이분법

실패를 두 경로로 분류한다. **동시에 두 경로를 수정하지 않는다** — 한 번에 하나씩 검증해야 원인이 명확해진다.

### "코드 버그" 판단 기준

| 신호 | 설명 |
|------|------|
| 단위 테스트 실패 | `pytest tests/unit/ -q` 에서 즉시 재현됨 |
| 같은 환경에서 재현 가능 | 동일 머신, 동일 .env, 동일 코드로 항상 실패 |
| 로직 오류 | 예상 출력 vs 실제 출력의 논리적 차이 |
| ImportError / AttributeError | 코드 수정 후 새로 발생한 경우 |
| 최근 커밋과 연관 | `git log --oneline -5` 기준 24h 이내 변경 파일에서 발생 |

**코드 경로 확정 조치**: `git revert` 또는 핫픽스 브랜치 → 단위 테스트 추가 → PR 머지

### "인프라 이슈" 판단 기준

| 신호 | 설명 |
|------|------|
| 환경마다 다른 결과 | 로컬 PASS, CI FAIL 또는 그 반대 |
| timeout 에러 | `asyncio.TimeoutError`, `httpx.ReadTimeout`, `Telethon` 연결 끊김 |
| connection error | `ConnectionRefusedError`, `NetworkError` |
| 환경변수 미설정 | pre-flight 헤더에 `[WARN]` 또는 `[FAIL]` 태그 |
| infra-baseline.yaml 불일치 | baseline 버전과 현재 실행 환경의 파라미터 차이 |
| 이전 테스트 메시지 혼입 | Telethon min_id 필터 미설정 (cross-contamination) |

**인프라 경로 확정 조치**: `infra-baseline.yaml` 갱신 → `.env` 수정 → E2E 재실행

---

## 2. 5분 안에 환경 격리하는 체크리스트

아래 순서대로 실행한다. **각 단계에서 원인이 확정되면 이후 단계는 생략한다.**

### Step 1 — Pre-flight 헤더 확인 (30초)

```bash
# pre-flight 체크 실행
bash scripts/preflight_check.sh 2>&1 | tail -20
# 또는 JSON 출력
.venv/bin/python scripts/preflight_check.py --json | python -m json.tool
```

- `[FAIL]` 항목이 있으면 → **인프라 경로** (Step 4로 이동)
- `[WARN]` 항목만 있으면 → 계속 진행 (심각한 인프라 이슈 없음)
- `[PASS]` 전부 → Step 2로 이동

### Step 2 — 단위 테스트 단독 실행 (1분)

```bash
.venv/bin/python -m pytest tests/unit/ -q --tb=short 2>&1 | tail -20
```

- 실패 있으면 → **코드 경로**
- 전부 통과 → Step 3으로 이동

### Step 3 — 최근 커밋 확인 (30초)

```bash
git log --oneline -10
git diff HEAD~1 HEAD --name-only
```

- 실패 파일과 수정 파일이 겹치면 → **코드 경로**
- 겹치지 않으면 → Step 4로 이동

### Step 4 — infra-baseline.yaml 비교 (1분)

```bash
cat infra-baseline.yaml
```

baseline이 없거나 파라미터가 현재 환경과 다르면 → **인프라 경로**

### Step 5 — 네트워크/API 연결 확인 (1분)

```bash
# 환경변수 설정 상태 일괄 확인
for var in TELEGRAM_BOT_TOKEN TELEGRAM_GROUP_CHAT_ID ANTHROPIC_API_KEY GEMINI_API_KEY; do
  echo "$var: ${!var:+[SET]}${!var:-[MISSING]}"
done
```

누락된 변수 있으면 → **인프라 경로** (`.env` 수정 필요)

---

## 3. 일반적인 함정 (Common Pitfalls)

### Timeout 설정 함정

```yaml
# infra-baseline.yaml — 잘못된 예
e2e_timeout_sec: 60   # ❌ S-P1 시나리오에 부족 (실제 소요 80~90초)

# 올바른 예
e2e_timeout_sec: 120  # ✅ ETC-02 수정 사항 (2026-03-25)
```

**증상**: E2E 테스트가 "통과 직전"에 timeout으로 실패. 로컬에서는 느린 네트워크에서만 발생.

**해결**: `infra-baseline.yaml`의 `e2e_timeout_sec`를 120 이상으로 설정.

### Filter 설정 함정 (cross-contamination)

```python
# 잘못된 예 — min_id 필터 없음
handler = helper.make_handler(chat_entity, collected, stop_flag)  # ❌

# 올바른 예
await helper.record_min_id(chat_entity)  # ✅ 먼저 기록
handler = helper.make_handler(chat_entity, collected, stop_flag)
```

**증상**: E2E 테스트가 이전 테스트에서 발생한 메시지를 수신하여 오탐 발생.

**해결**: `scripts/telethon_listener.py`의 `TelethonListenerHelper.record_min_id()` 반드시 먼저 호출.

```bash
# min_id 설정 상태 확인
grep -n "record_min_id\|min_id" tests/e2e/conftest.py | head -10
```

### 환경변수 누락 함정

```bash
# 잘못된 예 — .env 없이 바로 E2E 실행
.venv/bin/python -m pytest tests/e2e/ -q  # ❌ 환경변수 누락 가능

# 올바른 예
source .venv/bin/activate
cp .env.example .env  # 값 채우기
bash scripts/preflight_check.sh  # 검증
.venv/bin/python -m pytest tests/e2e/ -q  # ✅
```

**증상**: `ValueError: 필수 환경변수 'TELEGRAM_BOT_TOKEN' 가 설정되지 않았습니다`

**해결**: `.env.example`을 복사하고 필수 변수 모두 설정.

### Deprecated 모델 함정

```python
# 잘못된 예
model = "gemini-2.0-flash"  # ❌ 2026-06-01 서비스 종료 예정

# 올바른 예
model = "gemini-2.5-flash"  # ✅ GA 버전 (2026-03-22 기준 권장)
```

**탐지**:
```bash
grep -rn "gemini-2.0-flash" core/ scripts/ bots/ tools/
```

---

## 4. infra-baseline.yaml 활용법

### 역할

`infra-baseline.yaml`은 **인프라 파라미터의 단일 진실 소스**다. 코드에 파라미터를 하드코딩하지 않고 이 파일에 명세한다.

```yaml
# infra-baseline.yaml 예시
version: v0.4.0
e2e_timeout_sec: 120
unit_timeout_sec: 30
min_id_filter: enabled
deprecated_models:
  - gemini-2.0-flash
env:
  required:
    - TELEGRAM_BOT_TOKEN
    - TELEGRAM_GROUP_CHAT_ID
  optional:
    - ADMIN_CHAT_ID
    - WATCHDOG_BOT_TOKEN
```

### 환경 버전 고정 방법

1. `version` 필드를 semver(`vX.Y.Z`)로 관리
2. 파라미터 변경 시 `version`을 bump
3. E2E 로그 헤더에 `baseline_version` 자동 기록 (pre-flight 체크 후 출력)

```bash
# 현재 baseline 버전 확인
grep "^version:" infra-baseline.yaml

# E2E 실행 시 헤더 확인
.venv/bin/python -m pytest tests/e2e/ -q -s 2>&1 | grep "\[PRE-FLIGHT\]"
```

### baseline 갱신 절차

```bash
# 1. 변경 이유를 주석으로 기록
# 2. version 필드 bump
# 3. 변경된 파라미터 반영
# 4. pre-flight 체크 재실행하여 검증
bash scripts/preflight_check.sh
```

---

## 5. E2E 테스트 실패 시 디버그 순서

```
[E2E 실패 발생]
       |
       v
  [Step 1] bash scripts/preflight_check.sh
       |
       +-- FAIL 항목 있음 ──────────────────────────> [인프라 경로]
       |                                                 ↓
       |                                       infra-baseline.yaml 확인
       |                                       .env 수정
       |                                       E2E 재실행
       |
       +-- PASS/WARN 만 있음
       |
       v
  [Step 2] pytest tests/unit/ -q --tb=short
       |
       +-- 단위 테스트 실패 ──────────────────────────> [코드 경로]
       |                                                 ↓
       |                                       git log 확인
       |                                       핫픽스 브랜치
       |                                       단위 테스트 추가
       |
       +-- 단위 테스트 통과
       |
       v
  [Step 3] git log --oneline -10
       |
       +-- 최근 커밋 있고 파일 겹침 ─────────────────> [코드 경로]
       |
       +-- 겹치지 않음
       |
       v
  [Step 4] cat infra-baseline.yaml
       |
       +-- 파일 없음 / 파라미터 불일치 ─────────────> [인프라 경로]
       |
       +-- 일치
       |
       v
  [Step 5] 환경변수 확인 + 팀 에스컬레이션
           repro.log 첨부하여 GitHub Issue 등록
```

### 에스컬레이션 시 첨부 파일

```bash
# 재현 로그 수집
.venv/bin/python -m pytest tests/<실패_파일> -q --tb=long -s 2>&1 > /tmp/repro.log

# pre-flight 헤더 수집
bash scripts/preflight_check.sh 2>&1 > /tmp/preflight.log

# baseline 현재 내용
cat infra-baseline.yaml > /tmp/baseline_snapshot.yaml
```

GitHub Issue에 위 3개 파일 첨부 + `[env-debug]` 레이블 추가.

---

## 참조 파일

| 파일 | 역할 |
|------|------|
| `scripts/preflight_check.sh` | Bash pre-flight 체크 스크립트 (RETRO-01) |
| `scripts/preflight_check.py` | Python pre-flight 체크 (JSON 출력 지원) |
| `tests/e2e/preflight_check.py` | E2E 테스트 전용 pre-flight 모듈 |
| `core/env_guard.py` | 런타임 환경변수 가드 (require_env, warn_default_timeout) |
| `infra-baseline.yaml` | 인프라 기준 파라미터 명세 |
| `docs/ENV_ISOLATION_DEBUG_GUIDE.md` | 상세 Phase별 디버그 절차서 |

---

## 운영 원칙

1. **단일 진실 소스**: 인프라 파라미터는 `infra-baseline.yaml` 단일 파일. 코드 하드코딩 금지.
2. **헤더 필수**: E2E 테스트 로그에는 pre-flight 헤더가 포함되어야 한다. 헤더 없는 로그로 버그 리포트 제출 금지.
3. **이분 원칙**: 코드 경로와 인프라 경로를 동시에 수정하지 않는다.
4. **기록 원칙**: 인프라 변경 시 `infra-baseline.yaml`의 `version`을 bump하고 변경 이유를 주석으로 남긴다.
