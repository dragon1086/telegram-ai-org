# 리서치 산출물 표준 (Research Standards)

> **버전**: 1.0.0 | **최초 작성**: 2026-03-26 | **소유**: 리서치실 / PM
> **관련 파일**: `docs/research_context_template.yaml`, `docs/infra-baseline.yaml`

---

## 핵심 원칙

**모든 리서치 산출물은 반드시 `research_context.yaml`을 동반해야 한다.**

리서치 결과는 조사 시점·사용 모델·인프라 환경에 따라 달라진다.
`research_context.yaml` 없는 산출물은 **재현 불가 결과**로 간주하며,
PM 검토 및 팀 공유 대상에서 제외될 수 있다.

---

## 적용 범위

| 산출물 유형 | 적용 여부 | 비고 |
|------------|----------|------|
| 시장 조사 보고서 | ✅ 필수 | |
| 경쟁사 분석 문서 | ✅ 필수 | |
| 레퍼런스 수집 결과 | ✅ 필수 | |
| 문서 요약 (외부 소스 기반) | ✅ 필수 | |
| 내부 문서 요약 | ⚠️ 권장 | 외부 소스 없을 경우 선택 |
| 코드 구현 산출물 | ❌ 해당 없음 | 개발실 표준 적용 |
| 디자인 산출물 | ❌ 해당 없음 | 디자인실 표준 적용 |

---

## 파일 생성 방법

### Step 1 — 템플릿 복사

```bash
# 산출물 디렉토리에 research_context.yaml 생성
cp docs/research_context_template.yaml <산출물_디렉토리>/research_context.yaml
```

### Step 2 — 필드 작성

`research_context.yaml` 을 열고 아래 필수 필드를 모두 작성한다.

| 필드 | 필수 여부 | 설명 |
|------|----------|------|
| `research_date` | ✅ 필수 | 조사 시작 일시 (ISO 8601) |
| `researcher_agent` | ✅ 필수 | 조사 수행 에이전트/모델 식별자 |
| `model_version` | ✅ 필수 | 사용 언어 모델 버전 (구체적 버전 문자열) |
| `infra_baseline_version` | ✅ 필수 | 인프라 기준 버전 (`unversioned` 임시 허용) |
| `query_summary` | ✅ 필수 | 조사 질의 요약 (100자 이내) |
| `data_sources` | ✅ 필수 | 참조 소스 1개 이상 |
| `context_notes` | ⚠️ 권장 | 환경 특이사항·조사 한계 |

### Step 3 — 산출물과 함께 커밋

```bash
git add <산출물_디렉토리>/research_context.yaml
git add <산출물_파일들>
git commit -m "research: <조사 주제> (with research_context)"
```

---

## 파일 배치 규칙

```
# 단일 산출물의 경우
docs/research/<조사명>/
├── report.md                  ← 산출물 본문
└── research_context.yaml      ← 메타데이터 (필수)

# 여러 파일로 구성된 산출물
docs/research/<조사명>/
├── market-analysis.md
├── competitor-comparison.md
├── data/                      ← 원시 데이터
└── research_context.yaml      ← 디렉토리당 1개 (공통 메타데이터)
```

---

## 필드별 작성 기준

### `research_date`
- **형식**: `YYYY-MM-DDTHH:MM:SS+09:00` (KST 권장)
- **기준 시점**: 조사 *시작* 시각
- **금지**: "오늘", "최근", 날짜만 기재 (`2026-03-26` → ❌, `2026-03-26T09:00:00+09:00` → ✅)

### `model_version`
- **현행 표준 모델** (2026-03-26 기준):

| 조직 | 기본 모델 | 비고 |
|------|----------|------|
| 리서치실, 성장실 | `gemini-2.5-flash` | Google 검색 내장, GA 버전 |
| 개발실, 기획실, 디자인실, PM | `claude-sonnet-4-5` | 복잡한 추론 |
| 운영실 | `codex` 계열 | 경량 DevOps |

- **사용 금지**: `gemini-2.0-flash` (2026-06-01 서비스 종료)
- **Preview 버전**: 프로덕션 산출물에 사용 시 반드시 `context_notes`에 명시

### `infra_baseline_version`
- `docs/infra-baseline.yaml` 생성 전까지 `"unversioned"` 기재 허용
- `infra-baseline.yaml` 생성 후에는 해당 파일의 `version` 필드값 그대로 기재
- 목적: 인프라 파라미터(timeout, filter, env) 변경이 결과에 미친 영향을 사후 추적

### `data_sources`
- **최소 1개** 이상 기재 필수
- `url` 없는 내부 문서는 `ref` 필드에 상대 경로 기재
- 웹 소스는 `accessed_at` 기재 권장 (시점 추적용)

---

## 완성도 체크리스트

산출물 제출 전 아래 항목을 확인한다.

- [ ] `research_context.yaml` 파일이 산출물 디렉토리에 존재하는가?
- [ ] `research_date`가 ISO 8601 형식으로 기재되었는가?
- [ ] `researcher_agent`가 구체적 에이전트명으로 기재되었는가?
- [ ] `model_version`이 구체적 버전 문자열인가? (`gemini-2.0-flash` 금지 확인)
- [ ] `infra_baseline_version`이 기재되었는가? (최소 `"unversioned"`)
- [ ] `query_summary`가 100자 이내로 작성되었는가?
- [ ] `data_sources`에 1개 이상의 소스가 기재되었는가?
- [ ] `context_notes`에 조사 한계 또는 환경 특이사항이 기재되었는가?

---

## 개정 이력

| 버전 | 날짜 | 변경 내용 |
|------|------|----------|
| 1.0.0 | 2026-03-26 | 최초 작성 — RETRO-08 이행 (리서치 산출물 재현성 표준화) |
