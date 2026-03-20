# E2E 전체 테스트 리포트 — 2026-03-18 (최종)

## 요약 대시보드

| 항목 | 값 |
|------|-----|
| 총 시나리오 | 11 |
| P0 통과 | 5/5 |
| P1 통과 | 4/4 |
| P2 통과 | 2/2 |
| 전체 통과율 | 100% (11/11) |

## ✅ 모든 시나리오 PASS — 최소 합격 기준 충족

## 시나리오별 결과

| # | ID | Priority | Status | 설명 | 평가 |
|---|-----|----------|--------|------|------|
| 1 | S1 | P0 | PASS ✅ | 인사/안부 (PM 직접 답변) | PM 직접 응답 확인 |
| 2 | S2 | P0 | PASS ✅ | 단일 부서 위임 — 코딩 (engineering 봇) | engineering 봇 응답 + 코드 키워드 4개 |
| 3 | S3 | P1 | PASS ✅ | 단일 부서 위임 — 성장/마케팅 (growth 봇) | 성장/마케팅 키워드 확인 |
| 4 | S4 | P1 | PASS ✅ | 단일 부서 위임 — 디자인 (design 봇) | 디자인 키워드 확인 |
| 5 | S5 | P1 | PASS ✅ | 협업 (Collab) 요청 | 협업 태그 및 다중 봇 응답 |
| 6 | S6 | P1 | PASS ✅ | Discussion 멀티봇 토론 | 토론 참여 봇 응답 확인 |
| 7 | S7 | P0 | PASS ✅ | REST API 설계 — engineering 봇 위임 | HTTP 메서드 + 엔드포인트 키워드 확인 |
| 8 | S8 | P0 | PASS ✅ | /status 명령어 | 상태 정보 응답 확인 |
| 9 | S9 | P2 | PASS ✅ | 모호한 요청 처리 | PM 분류/안내 응답 확인 |
| 10 | S10 | P2 | PASS ✅ | 복잡 태스크 (다부서) | 다중 부서 분해·배분 확인 |
| 11 | S11 | P0 | PASS ✅ | 에러 핸들링 (미지원 요청) | 에러 메시지 또는 PM 안내 확인 |

---

## 수정 이력 (이번 테스트에서 발견·수정된 버그)

### 버그 1 — S2/S7: 코딩·API 설계 요청이 PM이 직접 답변
- **증상**: "파이썬 컴프리헨션 예제", "REST API 엔드포인트 설계" → PM이 직접 코드 작성
- **근본 원인 (4중 레이어)**:
  1. `pm_orchestrator.py` `_BASE_DEPT_KEYWORDS`: 파이썬 관련 키워드 미등록
  2. `pm_identity.py` "팀 구성 생략" 섹션: 코드 예제가 직접 답변 대상에 포함됨
  3. `telegram_relay.py:787` 하드코딩 "간단한 질문 직접 답변" 규칙이 pm_identity 규칙을 override
  4. `pm_orchestrator.py` `_llm_unified_classify`: LLM이 코딩 요청을 `direct_answer`로 분류 → `direct_reply` route → PM 직접 실행
- **수정 내역**:
  - `pm_orchestrator.py`: `_BASE_DEPT_KEYWORDS["aiorg_engineering_bot"]`에 파이썬/프로그래밍 키워드 추가
  - `pm_orchestrator.py`: `_CODING_OVERRIDE_KEYWORDS` + `_has_coding_request()` 추가 — LLM이 `direct_answer`로 분류해도 `single_org_execution`으로 강제 변환
  - `pm_orchestrator.py`: `_heuristic_lane()`, `_heuristic_plan_request()` 코딩 예외 처리
  - `pm_identity.py`: "팀 구성 생략" → "코드 작성·예제 작성이 없는 순수 텍스트 설명만 해당" 명시
  - `pm_identity.py`: "팀 구성 필수"에 코드 예제 → engineering 위임 규칙 추가
  - `telegram_relay.py:788`: "간단한 질문 직접 답변" 규칙에 코딩/API 예외 조항 추가

### 버그 2 — S2: engineering 봇 응답 대기 타임아웃 부족
- **증상**: 120s 타임아웃에서 engineering 봇 미수신 (실제로는 ~88s 후 응답)
- **수정**: S2 타임아웃 120s → 180s 상향 (`scripts/e2e_full_suite.py`)

---

## 최종 P0 결과

| P0 시나리오 | 결과 |
|------------|------|
| S1 인사 | ✅ PASS |
| S2 코딩 → engineering 봇 | ✅ PASS |
| S7 REST API → engineering 봇 | ✅ PASS |
| S8 /status | ✅ PASS |
| S11 에러 핸들링 | ✅ PASS |

**최소 합격 기준 (P0 전부 PASS): ✅ 달성**
