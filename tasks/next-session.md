# 다음 세션 작업 계획

> 작성: 2026-03-20
> 현재 브랜치: main (최신 커밋: 76834d4)

---

## 현재 상태 요약

| 항목 | 상태 |
|------|------|
| Unit tests (612개) | ✅ 전체 PASS |
| E2E unit tests (33개) | ✅ 전체 PASS |
| E2E P0 시나리오 (S1,S2,S5,S7,S8) | ✅ 5/5 PASS |
| E2E P1 시나리오 (S3,S4,S6,S9,S10) | ❌ 미실행 |
| MessageEnvelope E1 (parser) | ✅ 완료 |
| EnvelopeManager (DB) | ✅ 완료 |
| display_limiter tag strip | ✅ 완료 (_METADATA_TAG_RE) |
| telegram_relay.py MessageEnvelope 통합 | ❌ 미완료 |

---

## 우선순위 1: telegram_relay.py MessageEnvelope 통합

**목표**: 봇이 Telegram에 보내는 메시지에서 `[TYPE:value]` 태그 제거

**작업 내용**:
```
core/telegram_relay.py 의 PM 발화 경로에 MessageEnvelope.wrap() → to_display() 적용
- _pm_send_message 또는 send_message 호출 직전
- display_limiter.py의 _METADATA_TAG_RE 이미 존재함 — 활용 가능
- 봇 간 내부 통신(to_wire)은 유지
```

**검증**: `.venv/bin/pytest tests/ -q` 회귀 없음 + 실제 Telegram 메시지에 `[TAG:]` 없음 확인

---

## 우선순위 2: E2E P1 시나리오 실행

**실행 명령**:
```bash
PYTHONUNBUFFERED=1 .venv/bin/python -u scripts/e2e_full_suite.py --priority P1
```

**P1 시나리오 목록** (`scripts/e2e_full_suite.py` 참조):
- S3 (P1)
- S4 (P1)
- S6 (P1)
- S9 (P1)
- S10 (P1)

각 실패 시 eval 함수 분석 → dispatch-based 평가로 수정 (P0 수정 패턴 동일 적용)

---

## 우선순위 3: E2E P2 시나리오

```bash
PYTHONUNBUFFERED=1 .venv/bin/python -u scripts/e2e_full_suite.py --priority P2
# S11: 에러 핸들링 — 빈 의미 메시지 (크래시 없음 확인)
```

---

## 아키텍처 메모 (다음 세션에서 참고)

### PM 응답 구조 (핵심)
```
사용자 → PM 봇 → NL 분류 → [직접답변] 또는 [오케스트레이션 배분]
                                           ↓
                              cross_org_bridge → worker 봇 (비동기)
                              PM이 worker 결과 합성 → 최종 응답
```
- **worker 봇은 Telegram 그룹에 직접 응답 안 함**
- **모든 Telegram 응답 = aiorg_pm_bot**

### eval 함수 수정 패턴 (P0에서 검증됨)
```python
dispatch_kw = ["배분", "오케스트레이션", "개발실", "성장실"]
if any(k in t for k in dispatch_kw):
    return True, "✅ 태스크 배분 확인 (비동기 실행 중)"
```

### 주요 파일 경로
- `scripts/e2e_full_suite.py` — E2E 테스트 스크립트
- `core/telegram_relay.py` — PM 메시지 중계 (MessageEnvelope 통합 필요)
- `core/message_envelope.py` — MessageEnvelope + EnvelopeManager
- `core/display_limiter.py` — `_METADATA_TAG_RE` (태그 제거 정규식)
- `docs/retros/2026-03-20-e2e-final-report.md` — P0 완료 보고서

---

## 다음 세션 시작 프롬프트

```
지금 telegram-ai-org 프로젝트에서 이어서 작업.

현재 상태:
- Unit tests 612개 전체 PASS
- E2E P0 시나리오 5/5 PASS (S1,S2,S5,S7,S8)
- tasks/next-session.md 에 다음 작업 정리됨

할 일:
1. core/telegram_relay.py에 MessageEnvelope 통합
   - PM 발화 시 [TAG:value] 형식 태그 제거하여 자연스러운 한국어 출력
   - display_limiter.py의 _METADATA_TAG_RE 활용
   - 변경 후 pytest tests/ 회귀 없음 확인

2. E2E P1 시나리오 실행
   PYTHONUNBUFFERED=1 .venv/bin/python -u scripts/e2e_full_suite.py --priority P1
   - 실패 시 dispatch-based eval 수정 (P0 패턴 동일 적용)

3. E2E P2 시나리오 (S11)

각 완료 후 git commit. AskUserQuestion 금지, 자율 실행.
```
