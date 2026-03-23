# PM 보고 품질 진단 보고서

> 작성일: 2026-03-23 | 작성: aiorg_research_bot (Phase 1-3 수행)
> 태스크: T-aiorg_pm_bot-351

---

## 1. Executive Summary (요약)

현행 PM 최종보고는 **3가지 구조적 결함**으로 인해 사용자가 "뭘 읽어야 할지 헷갈리고, 눈에 안 들어오고, 기억에 안 남는" 상태다.

| 결함 | 심각도 | 근본 위치 |
|------|--------|-----------|
| **중복**: 같은 내용이 2~3회 반복 | 상 | `_SYNTHESIS_PROMPT`, `_write_unified_report_artifact` |
| **비정제**: 조직 원문이 그대로 노출 | 상 | `ensure_user_friendly_output` 프롬프트 |
| **바이패싱**: 보고 형식·구조 지시 부재 | 중 | 두 프롬프트 모두 구조 템플릿 없음 |

핵심 원인은 **"내용을 빠뜨리지 말라"는 지시가 "모두 그대로 붙여넣으라"로 해석되는 LLM 동작**이다.
synthesis 프롬프트에 보고서 구조 템플릿을 강제하고, 중복 금지 규칙을 명시하면 즉시 해결 가능하다.

---

## 2. 방법론

| 단계 | 수행 내용 | 수집 결과 |
|------|-----------|-----------|
| 코드 수집 | `core/result_synthesizer.py`, `core/pm_orchestrator.py`, `core/telegram_user_guardrail.py`, `core/structured_prompt.py` 전수 열람 | 보고 흐름 완전 파악 |
| 샘플 수집 | `.omx/reports/` 3건 + `reports/` 5건 열람 | T-221, T-233, T-237 3건 상세 분석 |
| 교차 분석 | 프롬프트 지시 ↔ 실제 보고 출력 대조 | 이슈 4종 식별 |

### 보고 생성 흐름 (현재)

```
[사용자 요청]
    ↓
PM 분해 → 부서 배분 (structured_prompt.render())
    ↓
부서별 실행 → 결과 반환
    ↓
ResultSynthesizer.synthesize() — _SYNTHESIS_PROMPT 기반 LLM 합성
    ↓
ensure_user_friendly_output() — 재작성 프롬프트
    ↓
_write_unified_report_artifact() — 파일 생성 (최종본 + 원문 부록)
    ↓
Telegram 전송: "✅ 모든 부서 작업 완료!\n\n{report}"
```

---

## 3. 문제 유형별 상세 분석

### ① 중복 (Duplication) — 영향도: 상

**발생 위치**: `core/result_synthesizer.py:40-74` + `core/pm_orchestrator.py:1010-1042`

**재현 조건**: 멀티 조직(2개 이상) 완료 후 `SUFFICIENT` 판정 시 항상 발생

**근거 — T-237 보고 파일 분석**:
```
## 최종 전달본          ← LLM 합성본
  [수정된 파일 10개 표 + 내용 요약]

## 조직별 핵심 결과 → 리서치실   ← 조직 원문
  [수정된 파일 5개 표 — 합성본과 70% 동일]

## 조직별 핵심 결과 → 개발실    ← 조직 원문
  [수정된 파일 7개 표 — 합성본과 80% 동일]

## 조직별 핵심 결과 → 운영실    ← 조직 원문
  [결과 요약 — 합성본과 90% 동일]
```
→ 동일 내용이 파일 내 **3~4회 반복** 출현. 읽는 사람이 무엇이 최종인지 판단 불가.

**직접 원인**:
1. `_SYNTHESIS_PROMPT` L62: `"Include ALL key findings from every department — do NOT summarize away details."` → LLM이 부서 출력을 **그대로 복사**하는 동작으로 해석
2. `_write_unified_report_artifact()` L1031-1041: 합성 후에도 **원문을 무조건 추가** — 결과 파일에 항상 중복 발생

---

### ② 비정제 (Unrefined) — 영향도: 상

**발생 위치**: `core/telegram_user_guardrail.py:68-86` (ensure_user_friendly_output 프롬프트)

**재현 조건**: 부서 결과에 내부 운영 메모가 섞인 경우 항상 발생

**근거 — T-237 조직별 결과 원문 노출**:
```
### 개발실
개발실 역할은 여기서 끝. 머지·푸시·재기동은 아래와 같이 운영실에 위임합니다:
[COLLAB:...]
```
→ 이런 **내부 운영 메모**가 사용자 보고서에 그대로 노출됨.

**근거 — T-221 비정제 fallback**:
```
## 조직별 핵심 결과 → 개발실
삭제 완료되었습니다. 결과를 요약합니다.
[중복 표 전체]
```
→ 부서가 생성한 "완료" 선언 + 중복 표가 사용자에게 노출됨.

**직접 원인**:
`ensure_user_friendly_output` 프롬프트(L68-86)가 "Organize findings clearly"라고만 명시하고
**보고서 구조 템플릿** 없이 재작성 → LLM이 "내용을 유지하면서 정리"를 "원문 그대로 유지"로 해석.

---

### ③ 바이패싱 (Bypassing) — 영향도: 중

**발생 위치**: `core/result_synthesizer.py` `_SYNTHESIS_PROMPT` REPORT 섹션

**재현 조건**: 복합 태스크에서 LLM이 REPORT를 생성할 때

**설명**:
`_SYNTHESIS_PROMPT`의 REPORT 지시가:
```
"REPORT:\nfinal integrated report for the user\nEND_REPORT"
```
→ 구조가 전혀 없음. LLM이 임의 형식으로 보고서를 생성.
"answer-first" 규칙은 있으나 그 다음 섹션(근거, 판단, 다음 조치)이 무엇인지 지정 없음.
→ 어떤 보고에서는 비교표가 앞에 오고, 어떤 보고에서는 결론이 맨 뒤에 오는 **형식 불일치** 발생.

---

### ④ 기타 — 형식 불일치 + 메시지 노이즈 — 영향도: 하

**발생 위치**: `core/pm_orchestrator.py:1724-1728`

**근거**:
```python
await self._send(
    chat_id,
    f"✅ 모든 부서 작업 완료!\n\n{report}{_artifact_list_note}\n\n"
    f"통합 보고서를 첨부합니다.\n[ARTIFACT:{artifact_path}]{subtask_artifact_markers}",
)
```
→ "✅ 모든 부서 작업 완료!" 가 보고서 첫 줄을 점령함.
사용자 입장에서 이 문구는 **내부 운영 상태** 메시지이지 **답변**이 아님.
진짜 답변(결론)이 두 번째 단락부터 시작되는 구조.

---

## 4. 근본 원인 추론

| # | 원인 | 영향 이슈 |
|---|------|-----------|
| **RC-1** | `_SYNTHESIS_PROMPT` REPORT 섹션에 구조 템플릿 없음 + "ALL key findings" 지시가 중복 유발 | ①②③ |
| **RC-2** | `ensure_user_friendly_output` 재작성 프롬프트에 "보고서 형식" 템플릿 없음 | ②③ |
| **RC-3** | `_write_unified_report_artifact()`가 합성 완료 후에도 원문을 무조건 추가 | ① |
| **RC-4** | 최종 Telegram 메시지가 내부 운영 상태 문구("작업 완료!")로 시작 | ④ |

**공통 패턴**: 두 프롬프트 모두 "무엇을 포함하라"는 내용 지시는 있지만
**"어떤 형식으로 구조화하라"**는 템플릿 지시가 없다.
LLM은 형식 지시가 없으면 입력 형식을 그대로 유지하는 경향이 있어,
부서 출력 형식이 보고서에 그대로 반영된다.

---

## 5. 우선순위별 개선 권고사항

### 단기 (즉시 구현 — 이번 태스크에서 코드 반영)

#### [S-1] `_SYNTHESIS_PROMPT` — REPORT 구조 템플릿 강제 + 중복 금지

```python
# 변경 위치: core/result_synthesizer.py, _SYNTHESIS_PROMPT
# 추가 규칙:
"- The REPORT must follow this EXACT structure:\n"
"  ## 결론\n  [한 문장 핵심 결론 — 무엇이 어떻게 됐는지]\n\n"
"  ## 핵심 내용\n  [PM 관점에서 부서별 결과를 통합 정리. 중복 없이 가장 중요한 것만.]\n\n"
"  ## 판단 근거 (선택)\n  [왜 이 결론인지. 충돌/이슈 있으면 명시.]\n\n"
"  ## 다음 조치 (있을 때만)\n  [후속 태스크 명시. 없으면 이 섹션 생략.]\n"
"- DO NOT copy department outputs verbatim. Synthesize and condense.\n"
"- DO NOT repeat the same finding across sections.\n"
```

#### [S-2] `ensure_user_friendly_output` — 보고 형식 강제 + 원문 금지

```python
# 변경 위치: core/telegram_user_guardrail.py, ensure_user_friendly_output()
# 프롬프트 추가:
"- Structure the output as a proper report: 결론 first, then organized body, then next steps.\n"
"- DO NOT copy raw department outputs. Extract and condense the key points.\n"
"- Remove internal operational notes (COLLAB tags, '개발실 역할은 여기서 끝' etc.).\n"
```

#### [S-3] `_synthesize_and_act` — 메시지 형식 개선

```python
# 변경 위치: core/pm_orchestrator.py, _synthesize_and_act()
# 현재: f"✅ 모든 부서 작업 완료!\n\n{report}..."
# 변경: report가 먼저, 운영 상태는 맨 마지막 줄로
```

#### [S-4] `_write_unified_report_artifact` — 원문 부록 명확히 구분

```python
# 변경 위치: core/pm_orchestrator.py
# "## 조직별 핵심 결과" → "## 부록: 조직 원문 (참고용)"으로 레이블 변경
```

### 중기 (다음 스프린트)

#### [M-1] 보고서 퀄리티 자가 평가 step
- 합성 완료 후 LLM에게 "이 보고서에 중복이 있는가?" 자가 검토 실행
- CRAP score처럼 "중복률" 지표 도입

#### [M-2] 템플릿 파일 외부화
- 보고서 구조 템플릿을 `skills/_shared/report-template.md`로 분리
- 프롬프트에서 파일 읽기로 주입 → 사용자가 템플릿 커스텀 가능

---

## 6. 개선 전후 예상 비교

| 항목 | 개선 전 | 개선 후 |
|------|--------|--------|
| 보고서 길이 | 500~1500자 (원문 반복) | 200~400자 (핵심만) |
| 중복 섹션 | 2~4회 동일 내용 | 0회 |
| 구조 일관성 | 보고마다 다름 | 결론→근거→조치 고정 |
| 내부 메모 노출 | 자주 발생 | 제거됨 |
| 첫 문장 | "✅ 모든 부서 작업 완료!" | 결론 직접 서술 |

---

*진단 완료. 다음 단계: 코드 개선 구현.*
