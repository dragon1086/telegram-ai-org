# 비즈니스 보고서 작성 가이드라인

> 기준일: 2026-03-23 | 작성: aiorg_research_bot (PM 리서치 산출물)
> 목적: PM이 다부서 의견을 취합 후 최종 보고 시 중복 없고 정제된 형태로 전달하기 위한 기준 문서

---

## 레퍼런스 목록 (Phase 1 산출물)

| # | 출처 | 유형 | 핵심 원칙 |
|---|------|------|-----------|
| 1 | [Pyramid Principle — McKinsey/SlideWorks](https://slideworks.io/resources/the-pyramid-principle-mckinsey-toolbox-with-examples) | 컨설팅 방법론 | 결론 먼저, 하향식 구조 |
| 2 | [Executive Summary 완전 가이드 — Board Intelligence](https://www.boardintelligence.com/blog/the-definitive-guide-to-writing-an-executive-summary) | 실무 가이드 | CQC 공식, 1페이지 원칙 |
| 3 | [HBR — Writing an Executive Summary That Means Business](https://store.hbr.org/product/writing-an-executive-summary-that-means-business/C0308E) | 학술·실무 | 3~5개 핵심 포인트 |
| 4 | [BLUF — Animalz Blog](https://www.animalz.co/blog/bottom-line-up-front) | 커뮤니케이션 기법 | 첫 문장에 핵심 결론 배치 |
| 5 | [BLUF — The Persimmon Group](https://thepersimmongroup.com/bluf-how-these-4-letters-simplify-communication/) | 리더십 커뮤니케이션 | 군사→기업 적용 사례 |
| 6 | [Visual Hierarchy — NN/g Nielsen Norman Group](https://www.nngroup.com/articles/visual-hierarchy-ux-definition/) | 가독성 설계 | 스캔 가능성, 시각 계층 |
| 7 | [White Space — Venngage](https://venngage.com/blog/white-space-design/) | 디자인 원칙 | 여백이 가독성 20% 향상 |
| 8 | [Analyst Academy — Slide Readability](https://www.theanalystacademy.com/designing-readability-effective-slides/) | 컨설팅 실무 | 슬라이드 당 1개 메시지 |
| 9 | [MECE — Management Consulted](https://managementconsulted.com/pyramid-principle/) | 논리 구조 | 상호 배타·전체 포괄 |
| 10 | [Executive Summary — USC Research Guide](https://libguides.usc.edu/writingguide/executivesummary) | 학술 기준 | 독립 가독성, 300~500단어 |

---

## 항목별 원칙 분류표 (Phase 1 산출물)

| 항목 | 핵심 기법 | 출처 |
|------|-----------|------|
| Executive Summary | BLUF + CQC 공식 | HBR, Board Intelligence |
| 중복 제거 | MECE 원칙 | McKinsey Pyramid Principle |
| 계층적 정보 구조 | Pyramid Principle (Barbara Minto) | McKinsey/SlideWorks |
| 가독성 설계 | 여백·시각 계층·1슬라이드 1메시지 | NN/g, Venngage, Analyst Academy |

---

## 1. 보고서 구조 원칙

### 핵심 원칙: 피라미드 구조 (Pyramid Principle)

> **"Think bottom-up, present top-down"** — Barbara Minto, McKinsey & Co.

**근거**: 바쁜 의사결정자는 결론부터 원한다. 분석 과정보다 판단 결과를 먼저 전달해야 집중력을 유지한다.

**구조 (3층 피라미드)**:
```
              [결론/권고]
           ↓            ↓
    [논거 A]    [논거 B]    [논거 C]
      ↓            ↓            ↓
  [데이터] [데이터] [데이터] [데이터]
```

**예시**:
- ❌ 잘못된 순서: "A 팀은 이런 분석을 했고, B 팀은 저런 조사를 했으며, C 팀은 검토 결과... 따라서 결론은 X입니다."
- ✅ 올바른 순서: "결론은 X입니다. 근거는 세 가지입니다: ① A의 분석 ② B의 조사 ③ C의 검토."

### Do / Don't

| Do | Don't |
|----|-------|
| 결론을 첫 문단에 배치 | 분석 과정을 시간순으로 나열 |
| 3~5개 핵심 논거만 선택 | 모든 팀 의견을 빠짐없이 나열 |
| 각 섹션에 소제목(헤더) 부여 | 긴 단락만으로 구성 |
| 논거 간 연결 논리 명시 | 각 부서 의견을 독립적으로 붙여넣기 |

---

## 2. Executive Summary 작성법

### 핵심 원칙: BLUF + CQC 공식

**BLUF (Bottom Line Up Front)**: 첫 문장에서 "무엇을 결정해야 하는가"와 "PM의 권고"를 즉시 전달.

**CQC 공식**:
1. **Context (맥락)**: 왜 이 보고가 필요한가? 어떤 배경에서 나왔는가?
2. **Questions (핵심 질문)**: 이 보고서가 답하는 3~5개 질문
3. **Conclusions (결론)**: 각 질문에 대한 명확한 답 + PM 의견

**길이**: A4 1페이지 / 텍스트 기준 300~500자 (텔레그램 기준 10~15줄)

**근거**: HBR 연구 — 인간 단기기억은 약 5개 개념을 동시에 처리. 5개 이상은 기억 잔류율 급감.

**예시**:

✅ **좋은 Executive Summary**:
```
[결론] 이번 스프린트는 목표 대비 70% 달성. 핵심 병목은 배포 자동화 미비.
[권고] 다음 스프린트 전 CI/CD 파이프라인 구축 우선 착수 권고.

[근거 3가지]
① Engineering: API 구현 완료, 배포 단계에서 수동 작업 2~3시간 소요
② Design: 와이어프레임 검수 완료, 개발 연계 대기 중
③ Growth: 베타 유저 피드백 20건 수집, 상위 이슈 3개 도출 완료
```

❌ **나쁜 Executive Summary**:
```
Engineering 팀 보고: API 구현을 완료했습니다. 배포 과정에서 여러 가지...
Design 팀 보고: 와이어프레임 작업을 진행했으며 현재 검수가...
Growth 팀 보고: 베타 유저 대상으로 피드백을 수집한 결과...
(각 팀 보고를 그대로 붙여넣은 형태)
```

### Do / Don't

| Do | Don't |
|----|-------|
| 첫 줄에 결론과 권고 배치 | 배경 설명으로 시작 |
| PM의 종합 판단을 명시 | 각 팀 내용 단순 요약 |
| 독자가 본문 없이도 이해 가능하게 작성 | 본문 읽어야 의미 파악 가능한 구성 |
| 긍정·부정 정보 모두 포함 | 좋은 소식만 부각 |

---

## 3. 중복 제거 및 MECE 적용법

### 핵심 원칙: MECE (Mutually Exclusive, Collectively Exhaustive)

- **Mutually Exclusive (상호 배타)**: 각 섹션의 내용이 서로 겹치지 않아야 함
- **Collectively Exhaustive (전체 포괄)**: 빠진 관점이 없어야 함

**근거**: McKinsey의 구조화 사고 핵심 원칙. 중복이 있으면 메시지가 희석되고 독자가 "이미 읽었다"고 느껴 집중력 저하.

**적용 방법 (다부서 취합 시)**:

```
1단계: 각 팀 산출물 수신
2단계: 토픽 클러스터링 (비슷한 내용 묶기)
3단계: 중복 제거 → 대표 문장 1개로 통합
4단계: 빠진 관점 확인 (전체 포괄 점검)
5단계: MECE 구조로 재배치
```

**예시 (3팀 → 1보고서)**:

| 팀 | 원문 내용 | MECE 처리 |
|----|-----------|-----------|
| Engineering | "API 완료, 배포 지연" | → [이슈] 배포 자동화 부재 |
| Ops | "배포 파이프라인 수동 작업 과다" | → 위와 동일 → **통합** |
| PM | "스프린트 속도 저하 원인 파악 필요" | → [권고] CI/CD 구축 |

### Do / Don't

| Do | Don't |
|----|-------|
| 같은 이슈가 여러 팀에서 나오면 1개로 통합 | 팀별로 동일 내용 반복 나열 |
| 섹션 간 내용 겹침 여부 최종 점검 | 각 팀 원문 그대로 첨부 |
| 빠진 시각(리스크 등) 있으면 PM이 직접 추가 | 팀이 안 다룬 건 그냥 생략 |

---

## 4. 계층적 정보 배치 방법

### 핵심 원칙: 정보의 3단계 계층화

```
Level 1 — 결론/권고 (Executive Layer)
  → 읽는 데 30초 이내 / 의사결정에 바로 활용 가능

Level 2 — 핵심 근거 (Management Layer)
  → 읽는 데 2~3분 / 판단 근거 확인용

Level 3 — 상세 데이터·부록 (Detail Layer)
  → 필요 시 참고 / 검증·딥다이브용
```

**근거**: NN/g 연구 — 독자는 F자 패턴으로 스캔. 첫 문단과 첫 단어를 가장 오래 본다.

**배치 원칙**:
1. **헤더 자체가 메시지**: "현황" ❌ → "배포 자동화 부재가 핵심 병목" ✅
2. **섹션당 1개 포인트**: 한 단락에 여러 주제 혼재 금지
3. **부록 분리**: 원문 데이터, 팀별 전체 보고는 별첨으로

**예시**:

✅ 계층 분리된 보고서 구조:
```
## [결론] 이번 분기 목표 70% 달성, 병목 1건 식별

### 달성 현황 (3줄)
### 핵심 이슈 (3줄)
### 권고 사항 (2줄)

--- (구분선 이후 상세 내용)

### 부록 A: Engineering 상세 보고
### 부록 B: Design 상세 보고
```

### Do / Don't

| Do | Don't |
|----|-------|
| 헤더에 결론을 담은 명사구/동사구 사용 | "현황", "이슈", "검토" 같은 빈 헤더 |
| Level 1~2만으로 보고서 완결 가능하게 구성 | 모든 내용을 동일 위계로 나열 |
| 상세 내용은 부록 또는 접기(Collapsed) 처리 | 팀별 원문을 본문에 전부 포함 |

---

## 5. 가독성 설계 체크리스트

### 핵심 원칙: 스캔 가능성 (Scannability)

**근거**: 적절한 여백이 가독성을 최대 20% 향상 (Venngage 연구). 독자는 읽기 전에 "읽을 만한가"를 0.5초에 판단.

### 텍스트 가독성

- [ ] 한 문단 = 최대 3~4줄
- [ ] 한 섹션 = 최대 5개 항목(bullet)
- [ ] 핵심 단어/숫자는 **굵게** 처리
- [ ] 전문 용어에는 간단한 설명 병기
- [ ] 수치는 단위와 함께 (70% ✅ / 70 ❌)

### 구조 가독성

- [ ] 섹션 구분: `##` H2 헤더 사용
- [ ] 소항목: `###` H3 또는 bullet
- [ ] 구분선(`---`)으로 주요 섹션 시각 분리
- [ ] 표(table)로 비교 정보 정리
- [ ] 코드블록으로 구조/예시 시각화

### 내용 가독성

- [ ] Executive Summary가 독립적으로 이해 가능한가
- [ ] 결론이 첫 문단에 있는가
- [ ] 권고 사항이 구체적이고 실행 가능한가
- [ ] 중복 섹션이 없는가 (MECE 점검)
- [ ] 팀별 원문 나열이 아닌 PM 통합 관점인가

---

## 모범 사례 vs 실패 사례 비교 (Phase 2 산출물)

### 사례 A — Executive Summary

| 항목 | 실패 사례 | 모범 사례 |
|------|-----------|-----------|
| 시작 | "이번 분기 여러 팀이 다양한 작업을..." | "이번 분기 목표 70% 달성, 핵심 리스크 1건" |
| 길이 | 각 팀 보고 합산 → 20줄+ | 3~5줄 핵심 요약 |
| 결론 위치 | 마지막 문단 | 첫 문단 |
| PM 관점 | 없음 (팀 보고 bypass) | 명시적 권고 포함 |

### 사례 B — 중복 처리

| 항목 | 실패 사례 | 모범 사례 |
|------|-----------|-----------|
| 동일 이슈 | Engineering/Ops 각각 2번 언급 | 통합 1회 언급 + 출처 병기 |
| 팀별 구분 | 팀 이름으로 섹션 나눔 | 주제(이슈/근거/권고)로 섹션 나눔 |

### 사례 C — 헤더 설계

| 항목 | 실패 사례 | 모범 사례 |
|------|-----------|-----------|
| 헤더 | "3. 검토 내용" | "3. 배포 지연의 원인: 자동화 도구 부재" |
| 서브헤더 | "3.1 세부 사항" | "3.1 CI/CD 부재로 배포당 3시간 수동 작업" |

---

## 실무 적용 체크리스트 (1분 자가 점검용)

보고서 작성 완료 후 아래 7개 항목을 순서대로 점검한다:

```
[ ] 1. 첫 3줄만 읽어도 결론을 알 수 있는가?
[ ] 2. Executive Summary가 1페이지 이내인가?
[ ] 3. 같은 내용이 두 번 이상 나오는 섹션이 있는가? (있으면 통합)
[ ] 4. 각 헤더가 내용을 담은 문장(명사구)인가?
[ ] 5. 팀별 원문을 그대로 붙여넣은 섹션이 있는가? (있으면 재작성)
[ ] 6. PM의 종합 판단/권고가 명시되어 있는가?
[ ] 7. 부록/상세 내용이 본문과 명확히 분리되어 있는가?
```

7개 중 5개 이상 통과 시 발송 가능.
5개 미만이면 구조 재설계 필요.

---

*참고 문헌*
- Minto, B. (1987). *The Pyramid Principle: Logic in Writing and Thinking*. McKinsey & Company.
- Board Intelligence. (2024). *The Definitive Guide to Writing an Executive Summary*.
- Harvard Business Publishing. *Writing an Executive Summary That Means Business* (C0308E).
- Nielsen Norman Group. *Visual Hierarchy in UX* (2024).
- Venngage. *Using White Space in Design: A Complete Guide* (2024).
