# 환경 격리 디버깅 가이드 (RETRO-02)

> 작성: 개발실 | 2026-03-27
> 목적: 코드 버그 vs 인프라/환경 문제를 빠르게 이분하는 구조적 디버깅 방법론.

---

## 1. 핵심 원칙: 이분법 (Binary Search)

장애 발생 시 **"코드가 문제인가, 환경이 문제인가"** 를 가장 먼저 판단한다.

```
장애 발생
    │
    ├─ 환경 체크 먼저 (preflight_check.py)
    │       ├─ FAIL → 환경 문제 → 인프라 수정
    │       └─ PASS → 코드 문제 → 코드 디버깅
    │
    └─ 증상 분류
            ├─ "항상 실패" → 코드 버그 가능성 높음
            ├─ "가끔 실패" → 타임아웃/race condition 가능성
            └─ "특정 환경에서만 실패" → 환경 문제 확실
```

---

## 2. 단계별 이분 프로세스

### Step 1: 환경 스냅샷 확보 (30초)

```bash
# 현재 환경 상태 전체 덤프
.venv/bin/python scripts/preflight_check.py --format json > /tmp/env_snapshot.json
cat /tmp/env_snapshot.json
```

체크리스트:
- [ ] API 키 유효한가?
- [ ] 타임아웃 설정이 충분한가? (≥120s)
- [ ] deprecated 모델을 사용하고 있지 않은가?
- [ ] 다른 봇 프로세스가 충돌하고 있지 않은가?

### Step 2: 최소 재현 (Minimal Reproducible)

```bash
# 가장 단순한 테스트부터 실행
.venv/bin/python -c "from core.telegram_relay import TelegramRelay; print('import OK')"

# 단위 테스트 (인프라 불필요)
.venv/bin/pytest tests/unit/ -x -q

# E2E 단일 테스트 (전체 스위트 아님)
.venv/bin/pytest tests/e2e/test_pm_dispatch_e2e.py::test_simple_pm_dispatch -xvs
```

### Step 3: 격리 레이어 (Isolation Layers)

```
레이어 1: Python 코드만    → pytest tests/unit/
레이어 2: 봇 없이 API만    → python -c "import anthropic; ..."
레이어 3: 단일 봇만        → SINGLE_BOT=1 python main.py
레이어 4: 전체 시스템      → bash scripts/bot_control.sh start
```

각 레이어를 순서대로 확인하여 어느 레이어에서 실패하는지 특정.

---

## 3. 증상별 디버깅 트리

### 3.1 타임아웃 (exit code 143, SIGTERM)

```
타임아웃 발생
    │
    ├─ PM_CHAT_REPLY_TIMEOUT_SEC 확인
    │       echo $PM_CHAT_REPLY_TIMEOUT_SEC  # 300 이상 권장
    │
    ├─ Claude subprocess timeout 확인
    │       grep "timeout" tools/claude_subprocess_runner.py
    │
    ├─ E2E pytest timeout 확인
    │       grep "timeout" pytest.ini conftest.py
    │
    └─ 해결책
            export PM_CHAT_REPLY_TIMEOUT_SEC=600
            pytest --timeout=300 tests/e2e/
```

**근본 원인 기록**: `lessons_learned/` 에 추가
**예방**: `infra-baseline.yaml`의 `timeout_sec` 필드 업데이트

### 3.2 메시지 필터링 오류 (cross-contamination)

```
다른 테스트 메시지가 현재 테스트에 영향
    │
    ├─ min_id 필터 확인
    │       grep "min_id\|offset_id" core/telegram_relay.py
    │
    ├─ 테스트 격리 확인
    │       # 각 테스트마다 새 message_id 기록
    │       grep "min_id" tests/e2e/
    │
    └─ 해결책
            # Telethon listener에 min_id 파라미터 전달
            await client.get_messages(chat_id, min_id=start_msg_id)
```

### 3.3 COLLAB 태그 미실행 (PM 답변 후 무반응)

```
PM이 [COLLAB:...] 태그로 위임했는데 실행 안 됨
    │
    ├─ context_db 접속 확인
    │       .venv/bin/python -c "from core.context_db import ContextDB; ContextDB()"
    │
    ├─ pm_orchestrator 활성화 여부
    │       grep "ENABLE_PM_ORCHESTRATOR" core/pm_orchestrator.py
    │       echo $ENABLE_PM_ORCHESTRATOR
    │
    ├─ target_org 추론 성공 여부 (로그 확인)
    │       grep "collab PM dispatch\|target_org\|infer_collab" logs/
    │
    └─ 해결책
            # _handle_collab_tags 로그 레벨 DEBUG로 올리기
            export LOG_LEVEL=DEBUG
            # 또는 target_org 직접 지정
            [COLLAB:작업 내용|맥락: ...|target:aiorg_engineering_bot]
```

### 3.4 모델 오류 (API Error)

```
LLM 호출 실패
    │
    ├─ deprecated 모델 사용 확인
    │       grep -r "gemini-2.0-flash" core/ scripts/
    │
    ├─ API 키 유효성 확인
    │       curl -H "x-api-key: $ANTHROPIC_API_KEY" https://api.anthropic.com/v1/models
    │
    ├─ Rate limit 확인
    │       grep "429\|rate_limit\|quota" logs/
    │
    └─ 해결책
            # gemini-2.0-flash → gemini-2.5-flash 교체
            grep -r "gemini-2.0-flash" core/ | xargs sed -i 's/gemini-2.0-flash/gemini-2.5-flash/g'
```

---

## 4. 환경 격리 체크리스트 (실제 장애 시)

```bash
# === 장애 발생 시 실행할 명령어 순서 ===

# 1. 현재 시간 기록 (로그 범위 특정용)
echo "장애 시작: $(date -Iseconds)"

# 2. 프리플라이트 체크
.venv/bin/python scripts/preflight_check.py 2>&1 | tee /tmp/preflight_$(date +%Y%m%d_%H%M).log

# 3. 프로세스 상태
ps aux | grep -E "python|claude|gemini" | grep -v grep

# 4. 최근 에러 로그
tail -50 logs/self-improve/cron.log 2>/dev/null
tail -50 ~/.ai-org/watchdog.log 2>/dev/null

# 5. DB 상태
sqlite3 tasks.db "SELECT status, COUNT(*) FROM tasks GROUP BY status;"

# 6. 환경변수 덤프 (토큰 제외)
env | grep -v "TOKEN\|KEY\|SECRET\|PASSWORD" | sort
```

---

## 5. 디버깅 결과 기록 규칙

장애 해결 후 반드시 아래 위치에 기록:

```bash
# lesson_memory에 기록 (자동 검색 가능)
.venv/bin/python -c "
from core.lesson_memory import LessonMemory
lm = LessonMemory()
lm.add(
    category='infra_timeout',
    error_pattern='exit code 143',
    root_cause='PM_CHAT_REPLY_TIMEOUT_SEC 미설정',
    fix='export PM_CHAT_REPLY_TIMEOUT_SEC=600',
    file='core/telegram_relay.py',
)
"

# 또는 docs/lessons_learned/ 에 마크다운으로 저장
```

---

## 6. 관련 도구

| 도구 | 용도 |
|------|------|
| `scripts/preflight_check.py` | 환경 자동 검증 |
| `tools/orchestration_cli.py validate-config` | 오케스트레이션 설정 검증 |
| `scripts/health_check.py` | 봇 프로세스 상태 확인 |
| `scripts/bot_control.sh status` | 전체 봇 상태 |
| `core/lesson_memory.py` | 과거 오류 패턴 검색 |
| `infra/infra-baseline.yaml` | 인프라 파라미터 기준값 |

---

## 관련 항목
- RETRO-01: Pre-flight 자동화 체크리스트
- `infra/infra-baseline.yaml`: 인프라 파라미터 명세
- `docs/pre_flight_checklist.md`: 이 가이드의 Pre-flight 버전
