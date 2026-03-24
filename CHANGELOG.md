# CHANGELOG

## [Unreleased]

---

## [2026-03-23] PM 최종보고 품질 개선 (T-353)

### 핵심 변경 요약
PM이 다부서 의견을 취합해 최종보고 시 **중복·비정제·바이패싱** 문제를 구조적으로 해결했다.

---

### 변경 파일 및 내용

#### `core/result_synthesizer.py`
- **`_SYNTHESIS_PROMPT`**: 3섹션 표준 포맷(`## 결론` / `## 핵심 내용` / `## 다음 조치`) 적용
  - Pyramid Principle (BLUF + MECE) 기반 Step 1 Pre-synthesis 지시 추가
  - 부서명 기준 섹션 헤더 금지 규칙 추가 (`NEVER use department names as section headers`)
  - 중복 병합 명시 (`Merge duplicates: if 2+ departments mention the same issue, write it ONCE`)
- **`_build_fallback_public_report`**: LLM fallback 경로에도 3섹션 표준 포맷 적용
  - 기존: 단순 문장 + 부서별 나열 → 개선: `## 결론` / `## 핵심 내용` / `## 다음 조치` 구조
  - 누락 부서 있을 때만 `## 다음 조치` 섹션 자동 생성
- **`_result_excerpt`**: `limit` 기본값 2200 → 3000 (부서 결과 컨텍스트 확보)

#### `core/telegram_user_guardrail.py`
- **`is_already_structured_report()`**: `## 결론` 구조 감지 헬퍼 추가
- **`ensure_user_friendly_output()`**: 이미 구조화된 보고서는 LLM 재작성 생략 (이중 호출 방지)
  - `full_context` 있을 때만 재작성 수행 (합성 fallback 케이스 한정)
- **`ensure_user_friendly_output` 프롬프트**: 3섹션 구조 적용 + Pyramid Principle 명시

#### `core/pm_orchestrator.py`
- `_synthesize_and_act`: `original_request` 컨텍스트 500 → 1500자 확장
- `NEEDS_INTEGRATION` 케이스: `'📋 결과 통합 보고서:\n\n'` 노이즈 프리픽스 제거
- 합성 성공 시 `full_context` 미전달 (이중 LLM 재작성 방지)

#### `core/pm_identity.py`
- **`build_system_prompt()`**: `## 다부서 취합 최종 보고 형식 (필수)` 섹션 추가
  - 보고서 구조 (3섹션 고정 순서), 절대 금지 패턴, 올바른 패턴 명시
  - 모든 PM 봇 직접 응답에도 동일한 포맷 적용

#### 테스트 (`tests/test_result_synthesizer.py`, `tests/test_telegram_user_guardrail.py`)
- `TestReportSectionFormat`: 3섹션 포맷 준수, 구 섹션명 제거 확인
- `TestFallbackReportStructure`: fallback 보고서 구조화 검증 (6개 테스트)
- `is_already_structured_report` 테스트: 감지/비감지/이중 재작성 방지 케이스

#### 문서 (`docs/`)
- `docs/business-report-guideline.md`: 글로벌 컨설팅 표준 기반 PM 보고서 가이드라인
- `docs/pm-report-prd-v1.md`: 취합·정제·중복제거 원칙 + GAP 매핑 + 체크리스트 통합 PRD

---

### 개선 전/후 비교

| 항목 | 개선 전 | 개선 후 |
|------|---------|---------|
| 보고서 구조 | 없음 (자유형) | 3섹션 고정 순서 |
| 바이패싱 | 팀별 원문 나열 | 주제별 통합, 팀명 헤더 금지 |
| 중복 | 동일 내용 2~3회 반복 | MECE 클러스터링으로 1회로 통합 |
| LLM 이중 호출 | 합성 후 항상 재작성 | 구조화 감지 후 불필요 시 생략 |
| 결론 위치 | 하단에 묻힘 | 항상 첫 섹션 |
| PM 권고 | 없거나 묻힘 | 결론 섹션에 필수 포함 |
| fallback 구조 | 단순 나열 | 3섹션 표준 준수 |

---

### 운영 유의사항

- **섹션명 일관성 필수**: `_SYNTHESIS_PROMPT`, `ensure_user_friendly_output`, `pm_identity.py` 3곳의 섹션명이 동일해야 함 (`## 결론` / `## 핵심 내용` / `## 다음 조치`)
- **섹션명 변경 시**: 위 3개 파일을 동시 업데이트할 것 (PRD `§6 개정 절차` 참조)
- **LLM 교체 시**: `_SYNTHESIS_PROMPT`와 `ensure_user_friendly_output` 프롬프트를 캘리브레이션할 것
- **사용자 피드백 기준**: `docs/pm-report-prd-v1.md` §6 운영 지침의 개정 트리거 기준 참고

---

### 참고 문서
- `docs/pm-report-prd-v1.md` — 취합·정제·중복제거 원칙 통합 PRD
- `docs/business-report-guideline.md` — 보고서 작성 가이드라인 (McKinsey Pyramid Principle 기반)
- `reports/pm_report_quality_diagnosis_20260323.md` — 현행 PM 보고 품질 진단 보고서
