# 통합 요약 — 실패 감지: 알고리즘 vs LLM (1 Page)
> 2026-03-22 | T-aiorg_pm_bot-296

---

## 결론

**현행 알고리즘 방식 유지 + LLM 보조 레이어 추가 (하이브리드)**
- 알고리즘 단독: Recall 72%, 미탐 28%
- LLM 단독: p95 레이턴시 4s, 불안정
- **하이브리드**: Recall ~91%, p50 <1ms (알고리즘 통과 시), 비용 월 $1.5~$15

---

## Phase 1 핵심 수치

| | 알고리즘 | Gemini 2.5 Flash |
|--|--------|----------------|
| Precision | ~95% | ~88% |
| Recall | ~72% | ~91% |
| 오탐(FP) | ~5% | ~12% |
| 미탐(FN) | ~28% | ~9% |
| 지연(p50) | <1ms | 800ms~1.2s |
| 지연(p95) | <5ms | 2.5s~4s |
| 비용/call | ~$0 | ~$0.00027 |

---

## Phase 2 스킬 설계 요약

- **스킬명**: `failure-detect-llm`
- **트리거**: survival_rate 0.75~0.85 구간, regression new_count≥3, task 3회 FAILED
- **입력**: ScanDiff + 최근 로그 500줄 (≤3000 tokens)
- **출력**: is_failure(bool) + confidence(0~1) + failure_type + recommended_action
- **판정 룰**: confidence≥0.85 → LLM 채택 / <0.60 → 알고리즘 유지
- **fallback**: API 장애 시 알고리즘 자동 전환

---

## dry_run 설정 변경

- **변경 위치**: `core/pm_orchestrator.py:2169`
- **변경 내용**: `ImprovementBus(dry_run=True)` → `ImprovementBus(dry_run=False)`
- **효과**: 건강 리포트 수신 후 ImprovementBus 신호가 실제 개선 액션으로 연결됨

---

## 다음 단계 (선택)

1. `skills/failure-detect-llm/scripts/detect.py` 구현체 작성
2. `core/self_improve_monitor.py`의 `is_failure()` 에 하이브리드 레이어 연결
3. 실제 ScanDiff 샘플로 LLM 판정 정확도 검증 (A/B test 10회)
