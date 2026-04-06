# 코드 vs 인프라 이분 디버깅 가이드 (RETRO-02)

> **작성**: 개발실 | **최초 작성**: 2026-03-27 | **최종 개정**: 2026-03-29
> **관련 태스크**: RETRO-02
> **연관 문서**: `infra-baseline.yaml`, `docs/pre_flight_checklist.md`, `scripts/preflight_check.py`

---

## 1. 개요

### 목적

테스트·운영 실패가 발생했을 때 **"코드 버그인가, 인프라/환경 문제인가"** 를 10분 안에 판별한다.
두 경로를 동시에 수정하면 원인 특정이 불가능해지므로, **반드시 하나씩 격리·검증**한다.

### 사용 시점

| 상황 | 이 가이드를 사용하는가? |
|------|------------------------|
| E2E 테스트가 갑자기 실패 | ✅ 예 |
| 로컬 PASS / CI FAIL (또는 반대) | ✅ 예 |
| timeout 에러가 불규칙하게 발생 | ✅ 예 |
| 단위 테스트가 일관되게 실패 | ✅ 예 (코드 경로 확정 후 활용) |
| 환경변수 누락 오류 | ✅ 예 |
| PR 리뷰 목적의 로직 검토 | ❌ 아니오 |

### 이분법 핵심 원칙

```
장애 발생
    │
    ├─ pre-flight 체크 먼저 ──────────────────────────────────────────
    │   FAIL → 인프라 경로 → infra-baseline.yaml + .env 수정 후 재실행
    │   PASS → 코드 경로  → 단위 테스트 + 최근 커밋 확인
    │
    └─ 증상 패턴으로 보조 판단
            "항상 실패"          → 코드 버그 가능성 높음
            "가끔 실패"          → timeout / race condition
            "특정 환경에서만 실패" → 인프라 문제 확실
```

---

## 2. 환경 격리 절차

실패를 재현하기 전에 **환경을 최소 변수 상태로 만든다**.
로컬 → Docker → CI 순서로 환경별 격리 단계를 따른다.

### 2-A. 로컬 환경 격리

```bash
# 1) 가상환경 초기화 (다른 프로젝트 의존성 오염 방지)
deactivate 2>/dev/null || true
source .venv/bin/activate
pip install -r requirements.txt --quiet

# 2) .env 초기화 — .env.example 기준으로 새로 설정
cp .env.example .env
# (필수 값: TELEGRAM_BOT_TOKEN, TELEGRAM_GROUP_CHAT_ID, ANTHROPIC_API_KEY 등)

# 3) 외부 연결 의존성 차단 후 단위 테스트만 먼저 실행
pytest tests/unit/ -q --tb=short
# → 여기서 실패 = 코드 문제 (외부 연결 없이도 실패하므로)

# 4) pre-flight 체크로 환경 상태 스냅샷
python scripts/preflight_check.py --format json | tee /tmp/local_preflight.json
```

### 2-B. Docker 환경 격리

```bash
# 1) 이미지 캐시 무효화 후 클린 빌드
docker compose build --no-cache

# 2) 단일 서비스로 격리 실행 (다른 서비스 영향 제외)
docker compose run --rm bot-pm bash

# 3) 컨테이너 내부에서 환경변수 확인
env | grep -v "TOKEN\|KEY\|SECRET" | sort

# 4) 컨테이너 내부에서 단위 테스트
pytest tests/unit/ -q --tb=short

# 5) 네트워크 연결 없이 재현 가능한지 확인
docker compose run --rm --no-deps bot-pm pytest tests/unit/ -q
```

### 2-C. CI 환경 격리

```bash
# 1) CI에서 실패한 스텝 로그를 다운로드
gh run view <run_id> --log-failed > /tmp/ci_fail.log

# 2) 로컬에서 동일한 CI 환경 변수 세트로 재현
#    (GitHub Actions secrets를 .env에 대응시켜 설정)
export CI=true
export GITHUB_ACTIONS=true

# 3) CI 환경 의존성과 동일하게 고정
pip install -r requirements.txt --constraint requirements-lock.txt

# 4) CI와 동일한 명령어로 테스트
pytest tests/ -q --tb=short --timeout=120

# 5) CI 로그 헤더에 baseline_version 기재 여부 확인
grep "PRE-FLIGHT\|baseline_version" /tmp/ci_fail.log | head -5
```

---

## 3. 이분 판단 체크포인트

아래 질문에 Yes/No로 답하며 순서대로 진행한다.
**Yes가 나온 시점에서 해당 경로로 확정**하고, 이후 질문은 생략한다.

### Phase 1 — 환경 체크 (30초)

| # | 질문 | Yes → | No → |
|---|------|-------|------|
| Q1 | `preflight_check.py` 에서 `[FAIL]` 항목이 있는가? | **인프라 경로** | Q2 진행 |
| Q2 | 필수 env 변수(BOT_TOKEN, API_KEY 등) 중 미설정 항목이 있는가? | **인프라 경로** | Q3 진행 |
| Q3 | `infra-baseline.yaml` 의 `timeout` 가 120 미만인가? | **인프라 경로** | Q4 진행 |

### Phase 2 — 코드 체크 (1~2분)

| # | 질문 | Yes → | No → |
|---|------|-------|------|
| Q4 | `pytest tests/unit/ -q` 에서 실패가 있는가? | **코드 경로** | Q5 진행 |
| Q5 | `git log --oneline -10` 기준 24h 이내 변경 파일에서 오류가 발생하는가? | **코드 경로** | Q6 진행 |
| Q6 | 동일 코드로 다른 환경(로컬↔CI)에서 성공하는가? | **인프라 경로** | Q7 진행 |

### Phase 3 — 심층 격리 (추가 3~5분)

| # | 질문 | Yes → | No → |
|---|------|-------|------|
| Q7 | env 변수를 모두 제거(`unset`)하면 오류 패턴이 달라지는가? | **인프라 경로** | Q8 진행 |
| Q8 | timeout을 기본값(120s)으로 교체했을 때 동작이 달라지는가? | **인프라 경로** | Q9 진행 |
| Q9 | Docker 클린 빌드 후 재실행하면 동작이 달라지는가? | **인프라 경로** | 팀 에스컬레이션 |

> **판단 불가 시**: `/tmp/repro.log` + `/tmp/preflight.log` 첨부하여 GitHub Issue 등록 (`[env-debug]` 레이블)

---

## 4. 코드 문제 시그니처 예시

### 예시 1 — AssertionError (로직 오류)

```
FAILED tests/unit/test_pm_dispatch.py::test_route_to_engineering - AssertionError
AssertionError: assert 'aiorg_design_bot' == 'aiorg_engineering_bot'
```

**특징**:
- `pytest tests/unit/` 단독 실행에서 재현됨 (외부 연결 불필요)
- 동일 환경에서 항상 실패
- 최근 커밋의 라우팅 로직 변경과 연관

**조치**:
```bash
git log --oneline -5               # 최근 변경 확인
git diff HEAD~1 HEAD -- core/pm_dispatcher.py  # 코드 변경 비교
# 핫픽스 브랜치 생성 → 단위 테스트 추가 → PR 머지
```

---

### 예시 2 — ImportError (의존성/모듈 오류)

```
ImportError: cannot import name 'ContextDB' from 'core.context_db'
```

**특징**:
- 로컬·CI 모두 실패 (환경 무관)
- 최근 리팩토링 커밋과 연관
- `grep "class ContextDB" core/context_db.py` 로 클래스 존재 확인 가능

**조치**:
```bash
git log --oneline --follow -- core/context_db.py  # 파일 이력 확인
git stash && pytest tests/unit/ -q                 # 스태시 후 재확인
```

---

### 예시 3 — AttributeError (인터페이스 불일치)

```
AttributeError: 'BotDispatcher' object has no attribute 'dispatch_collab'
```

**특징**:
- 코드 수정 후 새로 발생
- 모듈 분리(리팩토링) 중 메서드가 이동·삭제된 케이스
- `grep -rn "dispatch_collab" core/` 로 위치 탐색

**조치**:
```bash
# 메서드 위치 탐색
grep -rn "def dispatch_collab" core/ bots/
# 리팩토링 커밋에서 변경 이력 확인
git log -p --all -S "dispatch_collab" -- core/ bots/
```

---

## 5. 인프라 문제 시그니처 예시

### 예시 1 — Timeout 초과

```
asyncio.TimeoutError
E2E 시나리오 S-P1: FAILED (timeout after 60s)
```

**특징**:
- 로컬 느린 네트워크에서 발생, 빠른 네트워크에서는 통과
- CI 에서도 불규칙하게 실패
- `infra-baseline.yaml` 의 `timeout: 60` (부족)

**조치**:
```bash
# infra-baseline.yaml 수정 (timeout: 60 → 120)
# version bump 후 PR 생성
# 재실행
pytest tests/e2e/ --timeout=120 -q
```

---

### 예시 2 — 환경변수 미설정

```
ValueError: 필수 환경변수 'TELEGRAM_BOT_TOKEN' 가 설정되지 않았습니다
KeyError: 'ANTHROPIC_API_KEY'
```

**특징**:
- `.env` 파일 없이 실행하거나 `.env.example` 값을 채우지 않은 경우
- CI secrets 설정 누락 시 동일 증상

**조치**:
```bash
# 누락 변수 확인
for var in TELEGRAM_BOT_TOKEN TELEGRAM_GROUP_CHAT_ID ANTHROPIC_API_KEY GEMINI_API_KEY; do
  echo "$var: ${!var:+[SET]}${!var:-[MISSING]}"
done
# .env 재설정
cp .env.example .env && vim .env
bash scripts/preflight_check.sh
```

---

### 예시 3 — 네트워크/API 연결 오류

```
httpx.ConnectError: [Errno 111] Connection refused
TelegramNetworkError: Cannot connect to host api.telegram.org
```

**특징**:
- 단위 테스트는 통과하지만 E2E 에서만 실패
- Docker 내부 DNS 미설정 또는 프록시 설정 오류
- CI 방화벽 규칙으로 외부 API 차단

**조치**:
```bash
# API 엔드포인트 연결 확인
curl -s --max-time 5 https://api.telegram.org
curl -s --max-time 5 -H "x-api-key: $ANTHROPIC_API_KEY" https://api.anthropic.com/v1/models

# Docker 네트워크 확인
docker network ls
docker compose run --rm bot-pm curl -s https://api.telegram.org
```

---

## 6. 팀 공유 절차

### 원인 분류 후 레이블 태깅 컨벤션

이슈 해결 후 Slack 또는 GitHub Issue에 **반드시 레이블을 명시**한다.

#### Slack 공유 포맷

```
[env-debug] 원인 분류 완료

환경: 로컬 / Docker / CI  (해당 항목 표시)
분류: [코드 버그] 또는 [인프라 문제]
증상: (1줄 요약)
체크포인트: Q{번호} — {Yes/No} 에서 확정
조치: (실행한 명령어 또는 파일 변경 요약)
재발 방지: infra-baseline.yaml 갱신 완료 / 단위 테스트 추가 완료

로그 첨부: /tmp/repro.log, /tmp/preflight.log
```

#### GitHub Issue 레이블

| 원인 분류 | 적용 레이블 |
|-----------|------------|
| 코드 버그 | `bug` + `code` |
| 인프라 문제 | `infra` + `env-debug` |
| 판단 불가 (에스컬레이션) | `needs-triage` + `env-debug` |
| infra-baseline 갱신 필요 | `infra-baseline` |

#### 로그 수집 명령어 (이슈 등록 전 필수)

```bash
# 1) 재현 로그
pytest tests/<실패_파일> -q --tb=long -s 2>&1 | tee /tmp/repro.log

# 2) pre-flight 스냅샷
python scripts/preflight_check.py --format json 2>&1 | tee /tmp/preflight.json

# 3) baseline 스냅샷
cp infra-baseline.yaml /tmp/baseline_snapshot.yaml

# 4) 위 3개 파일을 GitHub Issue에 첨부
gh issue create \
  --title "[env-debug] <증상 1줄 요약>" \
  --label "env-debug,infra" \
  --body "$(cat /tmp/repro.log | head -50)"
```

### infra-baseline.yaml 갱신 절차 (인프라 경로 확정 시)

```bash
# 1) 변경 이유 주석 추가
# 2) version semver bump
# 3) 변경된 파라미터 반영
# 4) 팀 Slack 공유 (위 포맷 사용)
git add infra-baseline.yaml
git commit -m "fix(infra): <변경 내용> — baseline v{X.Y.Z}"
```

### 재발 방지 기록

장애 해결 후 `docs/lessons_learned/` 에 마크다운으로 기록한다.

```bash
# 파일 이름 형식: YYYY-MM-DD_<증상_키워드>.md
touch docs/lessons_learned/$(date +%Y-%m-%d)_timeout_s-p1.md
```

기록 항목: 증상 / 체크포인트 분기 경로 / 근본 원인 / 조치 / 재발 방지책

---

## 빠른 참조 — 5분 디버깅 플로우

```
[실패 발생]
    │
    v
[1] bash scripts/preflight_check.sh   ← FAIL 있으면 → 인프라 경로
    │  PASS/WARN
    v
[2] pytest tests/unit/ -q             ← 실패 있으면 → 코드 경로
    │  전부 PASS
    v
[3] git log --oneline -10             ← 파일 겹치면 → 코드 경로
    │  겹치지 않음
    v
[4] cat infra-baseline.yaml           ← 불일치 / 없으면 → 인프라 경로
    │  일치
    v
[5] 환경변수 일괄 확인 + GitHub Issue 등록 (env-debug 레이블)
```

---

## 참조 파일

| 파일 | 역할 |
|------|------|
| `scripts/preflight_check.sh` | Bash pre-flight 체크 스크립트 (RETRO-01) |
| `scripts/preflight_check.py` | Python pre-flight 체크 (JSON 출력 지원) |
| `infra-baseline.yaml` | 인프라 기준 파라미터 명세 |
| `docs/pre_flight_checklist.md` | Pre-flight 상세 절차서 |
| `docs/env_isolation_debug_guide.md` | 증상별 심층 디버깅 트리 |
| `core/env_guard.py` | 런타임 환경변수 가드 |
