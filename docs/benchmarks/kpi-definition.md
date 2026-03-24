# KPI 정의서 및 단일 세션 기준선 측정 실험 설계서

> 버전: v1.0
> 작성 기준: 2026-03-23
> 작성자: aiorg_growth_bot (성장실 PM)
> 목적: 단일 Claude Code 세션 대비 멀티에이전트 시스템(telegram-ai-org)의 성능 우위를 정량적으로 측정하기 위한 KPI 체계 및 기준선(baseline) 측정 방법 정의
> 참조: docs/gap-analysis-vs-single-claude.md, docs/improvement-plan.md

---

## 1. KPI 체계 개요

측정 차원은 5개로 분류한다. 각 차원은 독립적으로 측정 가능하며, 종합 점수(Composite Score)로 집계된다.

| 차원 ID | 차원명 | 약칭 | 가중치 |
|---------|--------|------|--------|
| KPI-01 | 작업 완료 속도 | TTD | 25% |
| KPI-02 | 산출물 품질 | QS | 30% |
| KPI-03 | 병렬 처리 효율 | PPE | 20% |
| KPI-04 | 컨텍스트 보존율 | CTX | 15% |
| KPI-05 | 오류 복구율 | ERR | 10% |

**종합 점수(Composite Score)** = Σ(KPI 정규화 점수 × 가중치)
- 정규화 기준: 100점 만점
- "압도적 우위" 판정 기준: 종합 점수 멀티에이전트 ≥ 단일 세션 × 1.30 (30% 이상 우위)

---

## 2. KPI 상세 정의

---

### KPI-01: 작업 완료 속도 (Time-to-Done, TTD)

**정의**: 태스크 수신 시각부터 최종 산출물 확정 및 사용자 전달 완료 시각까지의 경과 시간.

**측정 방법**

```
TTD = T_완료 - T_수신

측정 단위: 분(minute)
측정 방식: 로그 타임스탬프 자동 추출
```

- **단일 세션**: 사용자가 프롬프트 입력 후 응답 완료 시각 (Claude Code 세션 내 타임스탬프)
- **멀티에이전트**: 태스크 DB(ai_org.db) `created_at` → `completed_at` 차이

**서브 지표**

| 서브 KPI | 설명 | 단위 |
|---------|------|------|
| TTD-Simple | 단순 코딩 태스크 완료 시간 | 분 |
| TTD-Multi | 멀티팀 조율 태스크 완료 시간 | 분 |
| TTD-Long | 장기 프로젝트 태스크 완료 시간 | 시간 |
| TTD-P50 | 중앙값 완료 시간 | 분 |
| TTD-P90 | 90분위 완료 시간 (SLA 기준) | 분 |

**수집 주기**: 실험 시마다 (n≥5 반복 후 평균)

**데이터 소스**:
- 멀티에이전트: `ai_org.db` tasks 테이블 `created_at`, `completed_at` 컬럼
- 단일 세션: 실험 로그 파일 (`logs/baseline_experiments/`)
- 보조: 텔레그램 메시지 타임스탬프 (사용자 전달 시각 기준)

**현재 추정 기준선**:

| 태스크 유형 | 단일 세션 예상 TTD | 비고 |
|-----------|---------------|------|
| 단순 코딩 (파일 1-3개 수정) | 3-8분 | 단일 세션 강점 구간 |
| 멀티팀 조율 (2개 이상 도메인) | 30-90분 | 컨텍스트 전환 비용 |
| 장기 프로젝트 (3+ 단계) | 2-8시간 | 세션 한계 초과 위험 |

---

### KPI-02: 산출물 품질 (Quality Score, QS)

**정의**: 최종 산출물이 요구사항을 충족하는 정도. 정확도·완성도·일관성 3개 서브 지표로 측정.

**측정 방법**

품질 점수는 루브릭(rubric) 기반 평가표를 사용한다:

```
QS = (Accuracy × 0.4) + (Completeness × 0.35) + (Consistency × 0.25)
최대 100점
```

**서브 지표 루브릭**

| 서브 KPI | 설명 | 측정 방법 | 척도 |
|---------|------|---------|------|
| QS-Accuracy | 요구사항 대비 정확도 | 체크리스트 (AC 항목 충족 수 / 전체 AC 수) | 0-100 |
| QS-Completeness | 산출물 완성도 | 필수 섹션 포함 여부 (누락 섹션당 -10점) | 0-100 |
| QS-Consistency | 다중 산출물 간 일관성 | 상충하는 내용 발생 횟수 (건당 -15점) | 0-100 |

**자동 측정 항목**:
- `quality-gate` 스킬 실행 결과 (ruff PASS/FAIL, pytest PASS 건수)
- AC 체크리스트 자동 검증 스크립트 (`tools/orchestration_cli.py validate-config`)

**수동 측정 항목**:
- QS-Completeness: 인간 평가자(PM) 검토 (2인 이상 합의)
- QS-Consistency: 산출물 간 교차 검토

**수집 주기**: 각 실험 완료 후 24시간 이내

**데이터 소스**:
- 자동: `logs/quality-gate-results/` (quality-gate 스킬 실행 로그)
- 자동: `reports/` 디렉토리 내 산출물 파일
- 수동: `docs/benchmarks/eval-sheets/` (평가자 루브릭 시트)

---

### KPI-03: 병렬 처리 효율 (Parallel Processing Efficiency, PPE)

**정의**: 단위 시간당 동시 처리 가능한 태스크 수 및 병렬 처리로 인한 시간 절감률.

**측정 방법**

```
PPE = (동시 처리된 태스크 수) / (총 소요 시간, 분)
병렬 시간 절감률 = 1 - (병렬 TTD / 순차 TTD 합산)
```

**서브 지표**

| 서브 KPI | 설명 | 측정 방법 |
|---------|------|---------|
| PPE-MaxParallel | 동시 활성 태스크 최대 수 | ai_org.db 태스크 상태 스냅샷 |
| PPE-TimeReduction | 병렬 처리 시간 절감률 | (순차 예상 시간 - 실제 시간) / 순차 예상 시간 |
| PPE-BotUtilization | 봇 평균 활용률 | 활성 시간 / 총 실험 시간 (6개 봇 평균) |

**단일 세션 기준값**: PPE-MaxParallel = 1 (병렬 처리 불가)

**수집 주기**: 실험 시마다 (5분 간격 스냅샷)

**데이터 소스**:
- `ai_org.db` tasks 테이블 (status=running 쿼리)
- `logs/bot-activity/` 디렉토리
- P2PMessenger 메시지 로그

---

### KPI-04: 컨텍스트 보존율 (Context Retention Rate, CTX)

**정의**: 이전 세션 또는 이전 단계에서 생성된 정보가 이후 단계에서 정확하게 참조되는 비율.

**측정 방법**

```
CTX = (올바르게 참조된 이전 컨텍스트 항목 수) / (전체 참조 시도 항목 수) × 100
```

**테스트 시나리오**: 3단계 태스크(Phase 1→2→3)에서 Phase 1 결과물의 특정 수치(n=5개)가 Phase 2, 3에서 정확히 인용되는지 확인.

**서브 지표**

| 서브 KPI | 설명 | 측정 방법 |
|---------|------|---------|
| CTX-CrossSession | 세션 재시작 후 정보 보존율 | 봇 재기동 전후 컨텍스트 참조 정확도 |
| CTX-CrossBot | 봇 간 정보 전달 정확도 | P2PMessenger 전달 메시지 vs 수신 내용 비교 |
| CTX-LongTask | 장기 태스크(3단계+) 컨텍스트 연속성 | Phase 간 핵심 수치 인용 정확도 |

**단일 세션 약점**: 컨텍스트 창 초과 시 이전 내용 손실. 세션 재시작 시 완전 초기화.

**수집 주기**: 실험 시마다 (3단계 이상 태스크에서만 측정)

**데이터 소스**:
- `core/shared_memory.py` 저장 데이터
- `core/context_cache.py` 캐시 항목
- `memory/MEMORY.md` 참조 내용
- 실험 체크리스트 (평가자 수동 확인)

---

### KPI-05: 오류 복구율 (Error Recovery Rate, ERR)

**정의**: 실행 중 발생한 오류를 자동으로 감지하고 수정하여 태스크를 완료하는 비율.

**측정 방법**

```
ERR-Detection = (자동 감지된 오류 수) / (전체 발생 오류 수) × 100
ERR-Recovery = (자동 복구 성공 수) / (자동 감지된 오류 수) × 100
ERR-MTTR = 오류 발생부터 복구까지 평균 시간 (분)
```

**오류 유형 분류**

| 오류 유형 | 자동 감지 방법 | 자동 복구 방법 |
|---------|-------------|-------------|
| 코드 린트 오류 | PostToolUse ruff 훅 | 에이전트 자동 수정 루프 |
| 테스트 실패 | quality-gate 스킬 | 에이전트 자동 수정 |
| 위험 패턴 (glob/walk) | PreToolUse 훅 | 즉시 차단 (exit 2) |
| 봇 크래시 | bot-triage 스킬 | 프로세스 재시작 |
| 스키마 오류 | validate-config | 에이전트 수정 요청 |

**단일 세션 기준**: 모든 오류 감지/복구가 사용자 수동 개입에 의존 → ERR-Detection = 0% (자동), ERR-Recovery = 0% (자동)

**수집 주기**: 실험 시마다 + 월간 집계

**데이터 소스**:
- `scripts/hooks/log-agent.sh` 감사 로그
- `logs/` 디렉토리 오류 로그
- `quality-gate` 스킬 실행 결과
- `bot-triage` 인시던트 리포트

---

## 3. 종합 KPI 대시보드 템플릿

```markdown
## 실험 결과 요약 (날짜: YYYY-MM-DD)

| KPI | 단일 세션 | 멀티에이전트 | 개선률 | 목표 충족 |
|-----|---------|------------|--------|---------|
| TTD-P50 (분) | [값] | [값] | [%] | ≥20% ✓/✗ |
| TTD-P90 (분) | [값] | [값] | [%] | ≥20% ✓/✗ |
| QS 종합 (점) | [값] | [값] | [점 차이] | ≥15점 ✓/✗ |
| PPE-MaxParallel | 1 | [값] | N/A | ≥4 ✓/✗ |
| CTX-CrossSession (%) | ~30% | [값] | [%] | ≥80% ✓/✗ |
| ERR-Detection (%) | 0% | [값] | [%] | ≥70% ✓/✗ |
| ERR-Recovery (%) | 0% | [값] | [%] | ≥60% ✓/✗ |
| **종합 점수** | [값] | [값] | [%] | ≥30% ✓/✗ |
```

---

## 4. 단일 세션 기준선(Baseline) 측정 실험 설계서

### 4-1. 실험 목적

단일 Claude Code 세션(사용자 1명 + Claude 1개 세션)의 성능 기준값을 통제된 조건에서 측정하여, 멀티에이전트 시스템과의 비교 기준으로 활용한다.

### 4-2. 실험 통제 조건

| 변수 | 단일 세션 설정 | 멀티에이전트 설정 |
|------|-------------|---------------|
| Claude 모델 | claude-sonnet-4.6 | claude-sonnet-4.6 (동일) |
| 시스템 프롬프트 | Claude Code 기본 | orchestration.yaml 기반 |
| 컨텍스트 초기화 | 매 실험마다 새 세션 | 매 실험마다 공통 상태 초기화 |
| 입력 프롬프트 | 동일한 태스크 지시문 | 동일한 태스크 지시문 |
| 외부 도구 | Bash, Read, Write, Edit 허용 | 동일 + P2PMessenger |
| 사용자 개입 | 오류 시 수동 수정 허용 | 금지 (자율 실행만) |
| 시간 제한 | 없음 (자연 완료) | 없음 (자연 완료) |

### 4-3. 실험 태스크 세트 (통제 태스크 3종)

**실험 태스크 A — 단순 코딩 (Simple Coding)**
```
지시문: "core/shared_memory.py의 get() 메서드에 TTL(Time-to-Live) 파라미터를 추가하라.
기존 인터페이스 호환성을 유지하고, 단위 테스트를 작성하라."
예상 산출물: 수정된 shared_memory.py + test_shared_memory.py
AC: (1) TTL 파라미터 기본값=None으로 하위 호환, (2) pytest 통과, (3) ruff 오류 없음
```

**실험 태스크 B — 멀티팀 조율 (Multi-team Coordination)**
```
지시문: "신규 봇 'review-bot'을 추가하라. bots/ YAML 설정, orchestration.yaml 봇 등록,
README 업데이트, 기본 테스트 3개를 모두 포함하라."
예상 산출물: bots/review_bot.yaml + orchestration.yaml 수정 + README 수정 + tests/test_review_bot.py
AC: (1) YAML 스키마 검증 통과, (2) validate-config PASS, (3) 테스트 3개 PASS
```

**실험 태스크 C — 장기 프로젝트 (Long-term Project)**
```
지시문: "봇 성능 대시보드를 설계하고 구현 계획을 3단계로 분해하라.
Phase 1: 데이터 수집 설계, Phase 2: 집계 로직, Phase 3: 보고서 출력.
각 단계 산출물을 순차적으로 생성하라."
예상 산출물: 설계 문서 + 3단계 구현 파일 세트
AC: (1) Phase 간 데이터 스키마 일관성, (2) 각 단계 독립 실행 가능, (3) 전체 통합 테스트 PASS
```

### 4-4. 실험 절차

```
[단일 세션 기준선 측정 절차]

1. 환경 초기화
   - Claude Code 새 세션 시작 (이전 컨텍스트 없음)
   - 프로젝트 디렉토리: /Users/rocky/telegram-ai-org
   - git checkout -b baseline/experiment-{날짜}-{n}

2. 태스크 실행
   - 표준화된 지시문 복사-붙여넣기 (한 번에 전체)
   - 사용자 추가 개입 최소화 (오류 시 1회만 수동 힌트 허용)
   - 완료 선언 시 시각 기록

3. 측정 기록
   - T_수신: 지시문 입력 시각 (초 단위)
   - T_완료: 최종 답변 완료 시각
   - AC 체크리스트 수동 평가 (1=충족, 0=미충족)
   - 오류 발생 횟수 및 유형 기록

4. 산출물 저장
   - 결과 파일: logs/baseline_experiments/exp-{태스크ID}-{날짜}-{n}.md
   - 형식: TTD, QS 서브점수, 오류 로그 포함

5. 5회 반복 (n=5)
   - 각 실험 간 git reset --hard origin/main으로 상태 초기화
   - 동일 지시문으로 5번 반복
```

### 4-5. 기준선 예상값 (사전 추정)

> 주의: 아래 값은 실험 전 추정치이며, 실험 완료 후 실측값으로 대체한다.

| KPI | 단일 세션 추정값 | 근거 |
|-----|--------------|------|
| TTD-Simple (분) | 5-10 | 단일 파일 수정 + 테스트 작성 |
| TTD-Multi (분) | 45-90 | 다중 파일 + 오류 반복 수정 |
| TTD-Long (시간) | 2-6 | Phase 간 컨텍스트 재구축 비용 |
| QS-Accuracy (점) | 70-85 | AC 충족률 예상 |
| QS-Completeness (점) | 60-80 | 필수 섹션 누락 빈번 |
| PPE-MaxParallel | 1 | 단일 세션 구조적 한계 |
| CTX-CrossSession (%) | 20-40 | 세션 재시작 시 손실 |
| ERR-Detection (%) | 0 | 자동 감지 불가 |
| ERR-Recovery (%) | 0 | 사용자 수동 의존 |

### 4-6. 실험 로그 저장 경로

```
logs/baseline_experiments/
├── exp-A-simple-coding/
│   ├── run-01.md
│   ├── run-02.md
│   ├── ...
│   └── summary.md      ← 5회 평균값
├── exp-B-multi-team/
│   └── ...
├── exp-C-long-project/
│   └── ...
└── baseline-aggregate.md  ← 전체 기준선 집계
```

### 4-7. 최초 실험 실행 일정

| 단계 | 작업 | 담당 | 목표 일자 |
|------|------|------|---------|
| 환경 준비 | 실험 디렉토리 생성 + 로그 템플릿 | aiorg_engineering_bot | 즉시 |
| 태스크 A 기준선 | 단순 코딩 5회 반복 | 성장실 PM 관찰 | 1주 내 |
| 태스크 B 기준선 | 멀티팀 조율 5회 반복 | 성장실 PM 관찰 | 1주 내 |
| 태스크 C 기준선 | 장기 프로젝트 5회 반복 | 성장실 PM 관찰 | 2주 내 |
| 기준선 집계 | baseline-aggregate.md 작성 | aiorg_growth_bot | 2주 내 |

---

*이 문서는 Phase 2 비교 프레임워크 문서(`comparison-framework.md`)와 연동된다.*
*기준선 실측 완료 후 `improvement_thresholds.yaml`에 기준값 반영 예정.*
