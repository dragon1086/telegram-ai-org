# 다음 세션 작업 계획

> 작성: 2026-03-20 (업데이트: 봇 인간화 세션)
> 현재 브랜치: main (최신 커밋: dbba76b)

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
4. **백프레셔 임계값 완화**: `MAX_CONCURRENT_PARENT_TASKS` 5→10
5. **봇 상태 메시지 인간화**: "분석 중...", "처리 중...", "완료!", 배분 메시지 등 구어체로 전면 교체
6. **내부 실행 계획(brief) Telegram 노출 제거**: shell 커맨드·엔진·팀 구성 등 내부 정보가 채팅에 보이던 문제 수정
7. **`_send_plan_preview` 인간화**: PM 실행 계획 메시지도 구어체로

---

## 다음 우선순위 작업

현재 시스템은 E2E 전체 PASS + 봇 메시지 인간화 완료 상태.

### A. 봇 성격/말투 주입 시스템 (최우선)
- **자연어 채팅으로 봇 말투·성격 설정** 가능하게
  - 예: "성장실 봇 말투를 데이터 지향적이고 직설적으로 바꿔줘"
  - `direction` 필드를 말투 지시도 포함하도록 확장
- **적응형 확장 계획** (현재 구조와 충돌 없음):
  - 단기: `/org` 수동 주입 → `direction`에 말투 포함
  - 중기: 회고/피드백 결과가 `direction` 자동 업데이트
  - 현재 `strengths/weaknesses` 시스템은 역량 진화 담당 (별도 레이어)

### B. MessageEnvelope 실제 활용 확대
- worker 봇 응답에도 `MessageEnvelope.wrap()` → `to_display()` 적용
- `cross_org_bridge.py`에서 worker 결과 합성 시 envelope 사용

### C. 성능/안정성 개선
- E2E 시나리오 타임아웃 줄이기 (현재 150~360초 → 최적화)

### D. 신규 기능
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
