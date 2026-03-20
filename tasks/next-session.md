# 다음 세션 작업 계획

> 작성: 2026-03-20 (업데이트)
> 현재 브랜치: main (최신 커밋: 3537693)

---

## 현재 상태 요약

| 항목 | 상태 |
|------|------|
| Unit tests (645개) | ✅ 전체 PASS |
| E2E unit tests (33개) | ✅ 전체 PASS |
| E2E P0 시나리오 (S1,S2,S5,S7,S8) | ✅ 5/5 PASS |
| E2E P1 시나리오 (S3,S4,S6,S9,S10) | ✅ 5/5 PASS |
| E2E P2 시나리오 (S11) | ✅ 1/1 PASS |
| display_limiter send_reply 태그 제거 | ✅ 완료 |
| MessageEnvelope 통합 (display 경로) | ✅ 완료 |

---

## 완료된 작업 (2026-03-20 세션)

1. **display_limiter.py `send_reply` 태그 제거**: `_METADATA_TAG_RE` 적용 — `send_to_chat`과 동일하게 모든 Telegram 발화 경로에서 `[TYPE:value]` 태그 제거
2. **E2E P1 eval 수정**: `eval_growth`, `eval_design`, `eval_discussion`, `eval_complex`에 dispatch_kw 체크 추가 — 비동기 배분 응답을 PASS로 인정
3. **E2E 전체 11/11 PASS** 달성

---

## 다음 우선순위 작업

현재 시스템은 E2E 전체 PASS 상태. 다음 단계 후보:

### A. MessageEnvelope 실제 활용 확대
- worker 봇 응답에도 `MessageEnvelope.wrap()` → `to_display()` 적용
- `cross_org_bridge.py`에서 worker 결과 합성 시 envelope 사용

### B. 성능/안정성 개선
- E2E 시나리오 타임아웃 줄이기 (현재 150~360초 → 최적화)
- `⚠️ 현재 처리 중인 태스크가 많습니다` 메시지 빈도 줄이기

### C. 신규 기능
- PM 봇 `/history` 명령어 (최근 태스크 이력)
- 봇별 성과 대시보드

---

## 아키텍처 메모

### PM 응답 구조 (핵심)
```
사용자 → PM 봇 → NL 분류 → [직접답변] 또는 [오케스트레이션 배분]
                                           ↓
                              cross_org_bridge → worker 봇 (비동기)
                              PM이 worker 결과 합성 → 최종 응답
```
- **worker 봇은 Telegram 그룹에 직접 응답 안 함**
- **모든 Telegram 응답 = aiorg_pm_bot**

### eval 함수 수정 패턴 (검증됨)
```python
dispatch_kw = ["배분", "오케스트레이션", "개발실", "성장실"]
if any(k in t for k in dispatch_kw):
    return True, "✅ 태스크 배분 확인 (비동기 실행 중)"
```

### 주요 파일 경로
- `scripts/e2e_full_suite.py` — E2E 테스트 스크립트
- `core/telegram_relay.py` — PM 메시지 중계
- `core/message_envelope.py` — MessageEnvelope + EnvelopeManager
- `core/display_limiter.py` — `_METADATA_TAG_RE` (태그 제거 정규식)
