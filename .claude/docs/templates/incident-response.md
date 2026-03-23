# Incident Response Report

> 템플릿 사용법: 봇 장애 발생 즉시 이 파일을 복사하여 `docs/incidents/YYYY-MM-DD-<봇명>.md`로 저장 후 작성.

---

## 기본 정보

| 항목 | 내용 |
|------|------|
| **인시던트 ID** | INC-YYYY-NNNN |
| **발생 시각** | YYYY-MM-DD HH:MM (KST) |
| **감지 시각** | YYYY-MM-DD HH:MM (KST) |
| **복구 시각** | YYYY-MM-DD HH:MM (KST) |
| **총 다운타임** | N분 |
| **심각도** | P0 / P1 / P2 / P3 |
| **작성자** | @봇명 or 담당자 |

---

## 영향 봇

| 봇 ID | 상태 | 영향 범위 |
|-------|------|----------|
| aiorg_engineering_bot | DOWN / DEGRADED / UNAFFECTED | 설명 |
| aiorg_product_bot | DOWN / DEGRADED / UNAFFECTED | 설명 |
| aiorg_design_bot | DOWN / DEGRADED / UNAFFECTED | 설명 |
| aiorg_ops_bot | DOWN / DEGRADED / UNAFFECTED | 설명 |
| aiorg_research_bot | DOWN / DEGRADED / UNAFFECTED | 설명 |
| aiorg_growth_bot | DOWN / DEGRADED / UNAFFECTED | 설명 |

---

## 증상

- [ ] 텔레그램 메시지 무응답
- [ ] 오류 메시지 반환 (내용: )
- [ ] 봇 프로세스 종료 (PID: )
- [ ] 크론 잡 미실행
- [ ] 기타:

**첫 증상 보고 원문**:
```
(사용자/시스템 첫 보고 메시지 붙여넣기)
```

---

## 원인 분석

### 즉각 원인 (Direct Cause)

```
(로그, 에러 메시지, 트레이스백 등)
```

### 근본 원인 (Root Cause)

1.

### 기여 요인 (Contributing Factors)

-

---

## 타임라인

| 시각 | 이벤트 | 담당 |
|------|--------|------|
| HH:MM | 장애 최초 감지 | |
| HH:MM | 원인 파악 시작 | |
| HH:MM | 임시 조치 적용 | |
| HH:MM | 서비스 복구 확인 | |
| HH:MM | 인시던트 종료 선언 | |

---

## 즉시 조치 (Immediate Actions)

1. **HH:MM** — 조치 내용
2. **HH:MM** — 조치 내용

---

## 재발 방지 액션 아이템

| # | 조치 항목 | 담당 | 기한 | 상태 |
|---|----------|------|------|------|
| 1 | | | YYYY-MM-DD | OPEN |
| 2 | | | YYYY-MM-DD | OPEN |

---

## 체크리스트

- [ ] 인시던트 원인이 명확히 특정됨
- [ ] 영향 범위 전체 파악 완료
- [ ] 복구 확인 (모든 영향 봇 정상 응답)
- [ ] 재발 방지 액션 아이템 최소 1개 이상 등록
- [ ] MEMORY.md 또는 gotchas.md에 교훈 추가
- [ ] PM에게 최종 보고 완료
