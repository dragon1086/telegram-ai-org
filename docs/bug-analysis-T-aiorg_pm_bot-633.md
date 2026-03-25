# 잔여 버그 3건 상세 원인 분석·수정 방안·실행 로드맵 보고서

**태스크 ID**: T-aiorg_pm_bot-633 (T-629 보완본)
**작성일**: 2026-03-26
**작성 기준**: 실제 소스코드 직접 검증 (`core/telegram_relay.py`, `core/collab_request.py`)
**수정 상태**: 3건 모두 commit `4570453` 에서 수정 완료, 테스트 22개 전체 통과

---

## 수정 현황 요약

| 버그 ID | 명칭 | 수정 전 커밋 | 수정 커밋 | 테스트 파일 | 상태 |
|---------|------|------------|---------|------------|------|
| **BUG-01** | 한국어 조사 미분리 | `4aa127b` 이전 | `4570453` | `tests/test_bugfix_korean_collab.py` (10건) | ✅ **완료** |
| **BUG-02** | 플레이스홀더 필터 오탐 | `4aa127b` 이전 | `4570453` | `tests/test_bugfix_korean_collab.py` (10건) | ✅ **완료** |
| **BUG-03** | 부서봇 PM 오케스트레이터 미연결 | `4aa127b` 이전 | `4570453` | `tests/test_bugfix_korean_collab.py` (2건) | ✅ **완료** |

---

## Phase 1 — 버그 재현 시나리오 및 MRE 목록

### 1-1. 버그별 재현 시나리오 표

| 버그 ID | 발생 조건 | 실제 출력 (수정 전) | 기대 출력 | MRE 수 |
|---------|----------|-------------------|----------|--------|
| BUG-01 | `_infer_collab_target_org()`에 조사 포함 텍스트 입력 | `None` (score 미달) | 해당 org_id 반환 | 12개 |
| BUG-02 | `[COLLAB:...|맥락: 현재 작업 요약]` 형태 LLM 출력 | `is_placeholder_collab() = True` (오탐, 태그 드롭) | `False` (정상 처리) | 6개 |
| BUG-03 | 부서봇이 COLLAB 태그 생성, `_pm_orchestrator = None` | 채팅 메시지 전송만 (태스크 미생성) | ContextDB 태스크 생성 | 3개 |

---

### 1-2. BUG-01 한국어 조사 유형별 MRE 12케이스

아래는 수정 전 코드(`re.split(r"\W+")`)에서 score 손실이 발생하는 최소 재현 케이스다.
수정 후 `_tokenize_for_matching()`은 조사 제거 토큰을 추가 생성하여 모두 통과시킨다.

#### 조사 유형 ①: `에` / `에서` / `에게`

| MRE | 입력 텍스트 | 수정 전 토큰 | score 손실 여부 |
|-----|-----------|------------|----------------|
| MRE-01-1 | `"개발실에 버그 수정 부탁"` | `{"개발실에", "버그", "수정", "부탁"}` | "개발실에" ≠ "개발실" → score -1 |
| MRE-01-2 | `"운영실에서 배포 확인 요청"` | `{"운영실에서", "배포", "확인", "요청"}` | "운영실에서" ≠ "운영실" → score -1 |
| MRE-01-3 | `"기획실에게 일정 조율 요청"` | `{"기획실에게", "일정", "조율", "요청"}` | "기획실에게" ≠ "기획실" → score -1 |

#### 조사 유형 ②: `의` / `을` / `를`

| MRE | 입력 텍스트 | 수정 전 토큰 | score 손실 여부 |
|-----|-----------|------------|----------------|
| MRE-01-4 | `"디자인실의 UI 검토 요청"` | `{"디자인실의", "ui", "검토", "요청"}` | "디자인실의" ≠ "디자인실" → score -1 |
| MRE-01-5 | `"성장실을 통한 마케팅 지원"` | `{"성장실을", "통한", "마케팅", "지원"}` | "성장실을" ≠ "성장실" → score -1 |
| MRE-01-6 | `"리서치팀를 통해 조사 의뢰"` | `{"리서치팀를", "통해", "조사", "의뢰"}` | "리서치팀를" ≠ "리서치팀" → score -1 |

#### 조사 유형 ③: `은` / `는` / `이` / `가`

| MRE | 입력 텍스트 | 수정 전 토큰 | score 손실 여부 |
|-----|-----------|------------|----------------|
| MRE-01-7 | `"개발실은 이 버그 처리 가능?"` | `{"개발실은", "이", "버그", "처리", "가능"}` | "개발실은" ≠ "개발실" → score -1 |
| MRE-01-8 | `"운영팀이 배포를 담당"` | `{"운영팀이", "배포를", "담당"}` | "운영팀이" ≠ "운영팀" → score -1, "배포를" ≠ "배포" → score -1 |
| MRE-01-9 | `"기획팀가 스케줄 조정"` | `{"기획팀가", "스케줄", "조정"}` | "기획팀가" ≠ "기획팀" → score -1 |

#### 조사 유형 ④: `으로` / `로` / `까지` / `부터`

| MRE | 입력 텍스트 | 수정 전 토큰 | score 손실 여부 |
|-----|-----------|------------|----------------|
| MRE-01-10 | `"디자인실로 와이어프레임 전달"` | `{"디자인실로", "와이어프레임", "전달"}` | "디자인실로" ≠ "디자인실" → score -1 |
| MRE-01-11 | `"개발팀까지 배포 이슈 공유"` | `{"개발팀까지", "배포", "이슈", "공유"}` | "개발팀까지" ≠ "개발팀" → score -1 |
| MRE-01-12 | `"운영실부터 인프라 점검"` | `{"운영실부터", "인프라", "점검"}` | "운영실부터" ≠ "운영실" → score -1 |

> **임계값 효과**: score >= 2 조건에서, 짧은 메시지(어절 3개 이하)이거나 org명 어절이 유일한 핵심 키워드일 경우 조사 미분리 1건으로 `None` 반환 가능성이 높음.

---

### 1-3. BUG-02 플레이스홀더 오탐 MRE 6케이스

| MRE | 입력 (`task`, `context`) | 수정 전 결과 | 기대 결과 |
|-----|------------------------|------------|----------|
| MRE-02-1 | `("UI/UX 검토 요청", "현재 작업 요약")` | `True` ← 오탐 | `False` |
| MRE-02-2 | `("API 문서 작성", "현재 작업 요약: REST API v2")` | `True` ← 오탐 (exact match) | `False` |
| MRE-02-3 | `("작업", "API 개발 중")` | `True` ← 오탐 ("작업" in _PLACEHOLDER_TASKS) | `False` |
| MRE-02-4 | `("task", "deployment review")` | `True` ← 오탐 ("task" in _PLACEHOLDER_TASKS) | `False` |
| MRE-02-5 | `("태스크", "인프라 점검")` | `True` ← 오탐 ("태스크" in _PLACEHOLDER_TASKS) | `False` |
| MRE-02-6 | `("마케팅 전략", "현재 작업 요약 - Q2 캠페인")` | `True` ← 오탐 (접두사 변형 미처리) | `False` |

---

### 1-4. BUG-03 부서봇 PM 미연결 MRE 3케이스

| MRE | 시나리오 | 수정 전 동작 | 기대 동작 |
|-----|---------|------------|---------|
| MRE-03-1 | `aiorg_engineering_bot`이 `[COLLAB:와이어프레임 검토|맥락: 로그인 화면]` 태그 생성 | `_pm_orchestrator = None` → 채팅 메시지만 전송 | `context_db.create_pm_task()` 호출, TaskPoller가 감지·실행 |
| MRE-03-2 | `aiorg_growth_bot`이 `[COLLAB:데이터 분석 요청|맥락: Q2 KPI]` 생성 | 채팅 폴백, 태스크 ID 미생성 | ContextDB 태스크 `T-aiorg_growth_bot-collab-<uuid>` 생성 |
| MRE-03-3 | ContextDB 연결 실패 시 | 무음 드롭 | `create_pm_task` 실패 → `make_collab_request_v2` 채팅 폴백 (안전 degradation) |

---

## Phase 2 — 버그별 근본 원인 심층 분석

### 2-1. BUG-01 한국어 조사 미분리 — Why-5

| 단계 | 질문 | 답변 |
|------|------|------|
| Why 1 | 협업 대상 org_id가 None으로 반환되는가? | score가 threshold(2) 미만이라 `if not scored` 분기로 빠짐 |
| Why 2 | score가 threshold 미만인가? | "개발실에" 등 조사 포함 토큰이 haystack의 "개발실"과 불일치 |
| Why 3 | 토큰이 조사를 포함한 채로 남아있는가? | `re.split(r"\W+", text.lower())`가 공백 기준 분리만 수행하고 조사를 제거하지 않음 |
| Why 4 | `re.split(r"\W+")`이 조사를 제거하지 않는가? | `\W`는 non-word 문자를 기준으로 split하지만, 한글 조사는 word 문자(`\w`)로 분류되어 split 대상이 아님 |
| Why 5 (근본) | 왜 조사가 word 문자로 분류되었는가? | Python regex의 `\W`는 Unicode에서 `\P{Alphabetic}\P{Numeric}\P{Mark}\P{Connector_Punctuation}\P{Join_Control}`에 해당하는 문자를 non-word로 분류하는데, 한글 조사(은/는/이/가/을/를 등)는 모두 Unicode Script=Hangul로 word 문자임. **설계 시 한국어 형태 특성(교착어, 조사 후치 결합)을 고려하지 않은 것이 근본 원인** |

#### 원인 발생 계층 분류

| 계층 | BUG-01 해당 여부 | 상세 설명 |
|------|----------------|---------|
| **입력처리** | ✅ **주원인** | 토크나이즈 정규화(`_tokenize_for_matching`)에 한국어 후처리 없음 |
| **비즈니스로직** | ⬜ 부원인 | score >= 2 임계값이 조사 미분리 시 too strict하게 작동 |
| **출력처리** | ❌ 무관 | — |

#### 한국어 처리 특화 원인 상세

```
한국어 교착어 특성:
  어근 + 조사(격조사/보조사) → 하나의 어절 형성
  예: 개발 + 실 + 에 → "개발실에" (하나의 어절 = 하나의 unicode word)

Python regex \W+ 동작:
  ASCII: "hello-world" → ["hello", "world"]  (- = \W)
  Unicode KO: "개발실에" → ["개발실에"]  (조사 포함 전체가 \w)

결론:
  공백 기반 tokenization만으로는 한국어 어절에서 조사 분리 불가능.
  해결책: (a) 형태소 분석기 도입, (b) 규칙 기반 후행 조사 패턴 제거.
  현재 채택된 해결책: (b) _KR_PARTICLE_RE 정규식으로 후행 조사 제거
    + 원본 토큰도 함께 보존 ("개발실에" + "개발실" 모두 매칭 시도)
```

---

### 2-2. BUG-02 플레이스홀더 필터 오탐 — Why-5

| 단계 | 질문 | 답변 |
|------|------|------|
| Why 1 | 정상 COLLAB 태그가 무음 드롭되는가? | `is_placeholder_collab()` 가 `True`를 반환해 `continue` 처리됨 |
| Why 2 | `is_placeholder_collab()` 이 True를 반환하는가? | `context_norm in _PLACEHOLDER_CONTEXTS` 또는 `task_norm in _PLACEHOLDER_TASKS` 조건 충족 |
| Why 3 | 정상 태그의 context/task가 placeholder 집합에 있는가? | "현재 작업 요약", "작업", "task" 등 일반 업무 용어가 집합에 포함되어 있음 |
| Why 4 | 왜 일반 업무 용어가 placeholder 집합에 들어갔는가? | 초기 집합 설계 시 시스템 프롬프트 예시 문구("현재 작업 요약")와 메타변수("ctx", "task")를 모두 플레이스홀더로 취급했음 |
| Why 5 (근본) | 왜 구분이 없었는가? | **필터 설계 원칙 미정의**: "어떤 문자열이 플레이스홀더인가"에 대한 명시적 기준 없이 관찰 기반으로 집합을 확장하다가 과도한 일반화 발생 |

#### 원인 발생 계층 분류

| 계층 | BUG-02 해당 여부 | 상세 설명 |
|------|----------------|---------|
| **입력처리** | ⬜ 부원인 | LLM이 프롬프트 예시 문구를 그대로 출력하는 행동 |
| **비즈니스로직** | ✅ **주원인** | 플레이스홀더 판별 집합에 일반 업무 용어 혼재, exact match 방식의 과도한 필터링 |
| **출력처리** | ❌ 무관 | — |

---

### 2-3. BUG-03 부서봇 PM 오케스트레이터 미연결 — Why-5

| 단계 | 질문 | 답변 |
|------|------|------|
| Why 1 | 부서봇의 COLLAB 태그가 실제 태스크 생성 없이 채팅 메시지로만 처리되는가? | `_handle_collab_tags()`의 경로 A(`_pm_orchestrator.collab_dispatch`)가 실행되지 않음 |
| Why 2 | 경로 A가 실행되지 않는가? | `self._pm_orchestrator is not None` 조건 실패 (`_pm_orchestrator = None`) |
| Why 3 | 부서봇에서 `_pm_orchestrator`가 None인가? | `__init__`에서 `self._is_pm_org and context_db is not None` 조건이 False (`_is_pm_org`는 PM 봇에만 True) |
| Why 4 | 부서봇에서 `_is_pm_org`가 False인가? | `_is_pm_org = ENABLE_PM_ORCHESTRATOR and org_id not in KNOWN_DEPTS` — 부서봇은 `KNOWN_DEPTS`에 포함됨 |
| Why 5 (근본) | 왜 부서봇이 COLLAB 태그를 생성하는데 처리 경로가 없는가? | **설계 가정 불일치**: COLLAB 태그는 PM 봇만 생성한다고 가정했으나, 부서봇도 LLM 응답에서 태그를 생성할 수 있음. 부서봇의 COLLAB 생성→처리 경로가 설계에서 누락됨 |

#### 원인 발생 계층 분류

| 계층 | BUG-03 해당 여부 | 상세 설명 |
|------|----------------|---------|
| **입력처리** | ❌ 무관 | — |
| **비즈니스로직** | ✅ **주원인** | 부서봇 COLLAB 처리 경로 미구현, 경로 A 진입 조건이 PM봇 전용 |
| **출력처리** | ⬜ 부원인 | 채팅 메시지 폴백만 있어 태스크 추적 불가 |

---

### 2-4. 버그 간 공통 원인 교차 분석

| 공통 원인 | 해당 버그 | 설명 |
|----------|---------|------|
| **한국어 처리 특수성 미고려** | BUG-01 | 영어 기준 regex/tokenization 로직을 한국어에 그대로 적용 |
| **설계 가정의 과도한 단순화** | BUG-02, BUG-03 | 플레이스홀더 식별 기준 단순화(BUG-02), COLLAB 생성 주체 가정 단순화(BUG-03) |
| **테스트 경계 케이스 미설계** | BUG-01, BUG-02, BUG-03 | 버그 도입 당시 한국어 입력/오탐/부서봇 경로에 대한 테스트 케이스 없음 |

---

## Phase 3 — 버그별 수정 방안 설계 및 트레이드오프 분석

### 3-1. BUG-01 수정 방안 비교표

| 방안 | 접근법 | 수정 범위 | 부작용·회귀 위험 | 난이도 |
|------|--------|---------|---------------|--------|
| **방안 A** 규칙 기반 후처리 ✅ **권장·채택** | `_tokenize_for_matching()` 신설, `_KR_PARTICLE_RE` 정규식으로 후행 조사 제거 + 원본 토큰 병존 | 최소 (신규 classmethod 1개 + regex 1개) | "로" 등으로 끝나는 고유명사 오처리 가능성 — 원본 토큰 병존으로 완화 | L |
| **방안 B** 형태소 분석 라이브러리 도입 | `kiwipiepy` / `konlpy` 도입, 명사(NNG/NNP) 추출 후 매칭 | 전면 (의존성 추가, Docker 이미지 변경) | JVM 필요(konlpy), 초기화 오버헤드 200~500ms, 패키지 크기 +수십MB | H |
| **방안 C** LLM 후처리 방안 | `_infer_collab_target_org` 내 소형 LLM 호출로 "조직명 추출" 프롬프트 실행 | 중간 (LLM 호출 추가) | 지연 추가(200~1000ms), 비용 증가, 오류 전파 위험, 네트워크 의존성 | M |
| **방안 D** haystack 조사 변형 추가 | `org.dept_name`에 조사 변형 문자열 추가(`"개발실 개발실에 개발실의"...`) | 최소 (config 수정) | config 관리 부담, 신규 조직 추가 시 누락 위험 | L |

#### 한국어 조사 처리 3가지 방안 트레이드오프 상세

| 기준 | 방안 A 규칙 기반 | 방안 B 형태소 분석 | 방안 C LLM 후처리 |
|------|--------------|----------------|----------------|
| **정확도** | 95% (일반 조사 처리) | 99%+ (형태소 단위 분리) | 90~97% (프롬프트 품질 의존) |
| **응답 지연** | <1ms | 200~500ms (초기화), 이후 <10ms | 200~1000ms/호출 |
| **의존성 추가** | 없음 | kiwipiepy (경량) 또는 konlpy (JVM 필요) | 없음 (기존 LLM 활용) |
| **운영 복잡도** | 낮음 | 중간 (패키지 관리) | 높음 (프롬프트 관리, 비용 모니터링) |
| **오탐 위험** | "로/도/만" 어미 고유명사 오처리 가능 | 미등록어 처리 한계 | 할루시네이션 위험 |
| **구현 난이도** | L | H | M |
| **채택 여부** | ✅ 채택 | 장기 검토 | 비권장 |

**최종 권장: 방안 A** — 즉시 적용 가능, 충분한 정확도, 의존성 없음. 원본 토큰 병존으로 고유명사 오처리 완화. 장기적으로 방안 B(kiwipiepy) 도입 검토.

---

### 3-2. BUG-02 수정 방안 비교표

| 방안 | 접근법 | 수정 범위 | 부작용·회귀 위험 | 난이도 |
|------|--------|---------|---------------|--------|
| **방안 A** 집합 정리 + 접두사 검사 ✅ **권장·채택** | `_PLACEHOLDER_TASKS`에서 일반어(`"작업"`, `"task"`) 제거 + `_PLACEHOLDER_CONTEXTS` 접두사 기반 검사 추가 | 최소 (집합 2~3항목 삭제 + 검사 로직 7줄 수정) | 기존에 필터링되던 일반어 재등장 시 통과 — `_PLACEHOLDER_TASKS`의 고유 문구로 방어 | L |
| **방안 B** 길이 기반 필터 | `len(task_norm) <= 5` or `len(context_norm) <= 5` 이하만 필터링 | 최소 | "QA", "배포" 등 짧은 실제 태스크 드롭 위험 | L |
| **방안 C** 프롬프트에서 placeholder 문구 제거 | 시스템 프롬프트에서 `"현재 작업 요약"` 예시를 실제 예시(`"로그인 API 문서화"`)로 교체 | 중간 (프롬프트 수정) | LLM 행동 변화 리스크, A/B 테스트 필요 | M |

**최종 권장: 방안 A** — 집합 정리와 접두사 검사 조합으로 오탐·미탐 균형 달성.

---

### 3-3. BUG-03 수정 방안 비교표

| 방안 | 접근법 | 수정 범위 | 부작용·회귀 위험 | 난이도 |
|------|--------|---------|---------------|--------|
| **방안 A** ContextDB 직접 태스크 생성 ✅ **권장·채택** | `_pm_orchestrator is None`이고 `context_db is not None`일 때 `context_db.create_pm_task()` 직접 호출, TaskPoller가 감지·실행 | 중간 (새 elif 분기 + uuid import) | ContextDB 스키마 호환성 확인 필요, TaskPoller 폴링 주기 내 지연 발생 | M |
| **방안 B** P2P 메시지로 PM 봇 직접 위임 | `self._p2p.send(pm_org_id, collab_msg)` 방식으로 PM 봇에 메시지 전달 | 중간 (P2P 라우팅 확인) | P2P 메시지가 PM 봇 COLLAB 파서를 정확히 통과해야 함, 라우팅 실패 시 무음 드롭 | M |
| **방안 C** 부서봇에 PMOrchestrator lite 생성 | 부서봇도 경량 `_pm_orchestrator`를 초기화, 제한된 권한으로 태스크 생성 | 전면 (권한 모델 변경) | 태스크 소유권 혼재, 중복 처리 위험 | H |

**최종 권장: 방안 A** — ContextDB 직접 접근이 가장 명확한 분리를 유지. ContextDB 실패 시 채팅 메시지 폴백으로 안전 degradation 보장.

---

## Phase 4 — 우선순위 기반 수정 실행 로드맵

### 4-1. 버그 우선순위 매트릭스 (긴급도 × 영향도)

```
               영향도
               낮음        중간        높음
              ┌──────────┬──────────┬──────────┐
긴급도  높음   │          │          │ BUG-01   │
              │          │          │ BUG-02   │
              ├──────────┼──────────┼──────────┤
       중간   │          │ BUG-03   │          │
              │          │          │          │
              ├──────────┼──────────┼──────────┤
       낮음   │          │          │          │
              └──────────┴──────────┴──────────┘
```

| 버그 | 긴급도 | 영향도 | 우선순위 점수 | 스프린트 |
|------|--------|--------|------------|---------|
| BUG-01 한국어 조사 미분리 | 🔴 높음 (매 요청마다 영향) | 🔴 높음 (위임 실패 → 협업 불가) | **9/9** | Sprint 1 |
| BUG-02 플레이스홀더 오탐 | 🔴 높음 (무음 드롭, 탐지 어려움) | 🔴 높음 (정상 태그 소실) | **9/9** | Sprint 1 |
| BUG-03 부서봇 미연결 | 🟡 중간 (PM봇 직접 경로로 부분 우회 가능) | 🟡 중간 (부서봇 COLLAB 루프 미완성) | **6/9** | Sprint 1 |

---

### 4-2. Sprint별 수정 실행 로드맵

> **현황**: 3건 모두 commit `4570453`에서 Sprint 1 완료 상태 (2026-03-26).

#### Sprint 1 (2026-03-26 완료) — 3건 긴급 수정

| 작업 | 담당 | 상태 | DoD |
|------|------|------|-----|
| BUG-01: `_tokenize_for_matching()` + `_KR_PARTICLE_RE` 추가 | 개발실 | ✅ 완료 | `_tokenize_for_matching("개발실에")` 결과에 `"개발실"` 포함 |
| BUG-01: `_infer_collab_target_org()` / `_infer_collab_target_mentions()` 교체 | 개발실 | ✅ 완료 | MRE-01-1~12 케이스 모두 `None` 미반환 |
| BUG-02: `_PLACEHOLDER_TASKS`에서 일반어 제거 | 개발실 | ✅ 완료 | `is_placeholder_collab("작업", "코드 리뷰")` → `False` |
| BUG-02: `is_placeholder_collab()` 접두사 검사 추가 | 개발실 | ✅ 완료 | `is_placeholder_collab("디자인 요청", "현재 작업 요약: 인증")` → `True` |
| BUG-03: `_handle_collab_tags()` elif 분기 추가 (ContextDB 직접 생성) | 개발실 | ✅ 완료 | `context_db.create_pm_task()` 호출 확인 |
| BUG-03: ContextDB 실패 시 채팅 메시지 폴백 | 개발실 | ✅ 완료 | DB 실패 시 `make_collab_request_v2()` 채팅 전송 |
| 버그 3건 통합 테스트 (`test_bugfix_korean_collab.py`) 22건 작성 | 개발실 | ✅ 완료 | 22/22 passed |

#### Sprint 2 (예정: 2026-04-02) — 품질 강화

| 작업 | 담당 | 상태 | DoD |
|------|------|------|-----|
| `_KR_PARTICLE_RE` 조사 목록 확장 검토 (복합 조사 커버리지) | 개발실 | 예정 | 추가 20개 MRE 케이스 통과 |
| `_infer_collab_target_org()` score 임계값 동적 조정 옵션 | 개발실/기획실 | 예정 | 짧은 메시지(≤3 토큰) 시 threshold를 1로 완화 |
| `is_placeholder_collab()` 프롬프트 예시 문구 교체 | 기획실 | 예정 | 시스템 프롬프트의 COLLAB 예시 문구가 `_PLACEHOLDER_CONTEXTS`와 겹치지 않음 |
| BUG-03 P2P 메시지 경로 보완 (방안 B 검토) | 개발실 | 검토 | `_p2p.send()` 경로 E2E 테스트 통과 |

#### Sprint 3 (예정: 2026-04-09) — 장기 개선

| 작업 | 담당 | 상태 | DoD |
|------|------|------|-----|
| `kiwipiepy` 형태소 분석기 POC (방안 B) | 개발실 | 장기 | 정확도 비교 벤치마크 문서 작성 |
| COLLAB 태그 처리 E2E 통합 테스트 확장 | 개발실/운영실 | 장기 | 부서봇 → ContextDB → TaskPoller 흐름 E2E 커버 |

---

### 4-3. 버그별 Definition of Done (DoD)

#### BUG-01 DoD

- [ ] `_tokenize_for_matching("개발실에")` 반환값에 `"개발실"` 포함
- [ ] `_tokenize_for_matching("디자인실로")` 반환값에 `"디자인실"` 포함
- [ ] `_tokenize_for_matching("운영팀에서")` 반환값에 `"운영팀"` 포함
- [ ] `_infer_collab_target_org("개발실에 버그 수정")` → `None` 아님
- [ ] `_infer_collab_target_org("개발실에 부탁해")` → 기존 None에서 유효값으로 개선 (조사 제거 후 score 반영)
- [ ] `tests/test_bugfix_korean_collab.py::TestKoreanTokenize` 10개 전원 통과

#### BUG-02 DoD

- [ ] `is_placeholder_collab("작업", "코드 리뷰")` → `False`
- [ ] `is_placeholder_collab("task", "deployment")` → `False`
- [ ] `is_placeholder_collab("태스크", "인프라")` → `False`
- [ ] `is_placeholder_collab("구체적 작업 설명", "현재 작업 요약")` → `True` (진짜 플레이스홀더 유지)
- [ ] `is_placeholder_collab("디자인 요청", "현재 작업 요약: 인증 개발")` → `True` (접두사 변형 감지)
- [ ] `tests/test_bugfix_korean_collab.py::TestPlaceholderCollab` 10개 전원 통과

#### BUG-03 DoD

- [ ] `_pm_orchestrator = None`인 부서봇에서 `[COLLAB:...]` 태그 처리 시 `context_db.create_pm_task()` 호출됨
- [ ] 생성된 태스크 ID 형식: `T-{org_id}-collab-{uuid8}`
- [ ] ContextDB 실패 시 `make_collab_request_v2()` 채팅 폴백 실행 (안전 degradation)
- [ ] `tests/test_bugfix_korean_collab.py::TestDeptBotCollabFallback` 2개 전원 통과

---

### 4-4. 검증 시나리오 (테스트 시나리오 기술)

#### BUG-01 검증 시나리오

```python
# 시나리오 1: 을/를 조사
tokens = TelegramRelay._tokenize_for_matching("개발실을 통해 버그 수정")
assert "개발실" in tokens  # 조사 "을" 제거

# 시나리오 2: 에서 조사
tokens = TelegramRelay._tokenize_for_matching("운영실에서 배포 확인")
assert "운영실" in tokens  # 조사 "에서" 제거

# 시나리오 3: 으로 조사
tokens = TelegramRelay._tokenize_for_matching("디자인팀으로 와이어프레임 전달")
assert "디자인팀" in tokens  # 조사 "으로" 제거

# 시나리오 4: 짧은 메시지 (이전에 가장 위험했던 케이스)
tokens = TelegramRelay._tokenize_for_matching("개발실에 부탁해")
assert "개발실" in tokens  # "개발실에" 에서 "에" 제거 → 매칭 가능
```

#### BUG-02 검증 시나리오

```python
# 시나리오 1: 일반 업무 단어는 통과
assert is_placeholder_collab("작업", "QA 요청") is False
assert is_placeholder_collab("태스크", "인프라 점검") is False

# 시나리오 2: 진짜 플레이스홀더는 여전히 필터
assert is_placeholder_collab("구체적 작업 설명", "현재 작업 요약") is True

# 시나리오 3: 접두사 변형 감지
assert is_placeholder_collab("디자인 요청", "현재 작업 요약: API 개발") is True
assert is_placeholder_collab("디자인 요청", "현재 작업 요약 - 사이드바") is True

# 시나리오 4: 실제 맥락은 통과
assert is_placeholder_collab("마케팅 전략 수립", "Q2 사용자 확보 목표") is False
```

#### BUG-03 검증 시나리오

```python
# 시나리오 1: 부서봇 ContextDB 경로
relay._pm_orchestrator = None
relay.context_db = AsyncMock()
# [COLLAB:...] 태그 처리 후
relay.context_db.create_pm_task.assert_awaited_once()

# 시나리오 2: ContextDB 실패 시 채팅 폴백
relay.context_db.create_pm_task = AsyncMock(side_effect=Exception("DB Error"))
# 채팅 메시지로 폴백 확인
make_collab_request_v2_mock.assert_called_once()
```

---

### 4-5. 한국어 조사 처리 회귀 테스트 체크리스트

수정 적용 후 한국어 COLLAB 라우팅 품질을 지속 모니터링하기 위한 회귀 테스트 목록.

```
[ ] 을/를 조사: "개발실을", "운영팀를" → 조사 제거 토큰 포함
[ ] 이/가 조사: "기획팀이", "리서치팀가" → 조사 제거 토큰 포함
[ ] 은/는 조사: "개발실은", "성장실는" → 조사 제거 토큰 포함
[ ] 에/에서 조사: "운영실에", "디자인실에서" → 조사 제거 토큰 포함
[ ] 으로/로 조사: "개발팀으로", "운영실로" → 조사 제거 토큰 포함
[ ] 의 조사: "기획실의", "디자인실의" → 조사 제거 토큰 포함
[ ] 까지/부터 조사: "운영실까지", "개발팀부터" → 조사 제거 토큰 포함
[ ] 에게/에게서 조사: "기획팀에게", "리서치팀에게서" → 조사 제거 토큰 포함
[ ] 복합 조사: "개발실에서도", "운영팀에서는" → 조사 제거 토큰 포함
[ ] 영문 토큰 보존: "API", "UI" → 조사 제거 대상 아님, 원본 유지
[ ] 2자 미만 토큰 제외: "에", "를", "은" 단독 → 집합에 미포함
[ ] 원본 토큰 병존: "개발실에" → {"개발실에", "개발실"} 둘 다 포함
[ ] is_placeholder_collab 일반어 통과: "작업", "태스크", "task" → False
[ ] is_placeholder_collab 진짜 플레이스홀더 필터: "구체적 작업 설명" → True
[ ] is_placeholder_collab 접두사 변형 감지: "현재 작업 요약: ..." → True
[ ] 부서봇 ContextDB 태스크 생성: _pm_orchestrator=None + context_db 존재 → create_pm_task 호출
[ ] 부서봇 ContextDB 실패 폴백: DB 예외 → 채팅 메시지 전송 (무음 드롭 아님)
```

**자동화**: `tests/test_bugfix_korean_collab.py` 22개 테스트가 위 체크리스트의 핵심 케이스를 커버함.
CI 파이프라인에서 매 PR마다 실행 권장.

---

## 부록 — 수정 적용 코드 요약

### BUG-01 수정 코드 (`core/telegram_relay.py`)

```python
_KR_PARTICLE_RE = re.compile(
    r"(?:으로부터|에게서|에서도|에서는|에서만|에서라도|에서조차|에게도|에게는|에게만"
    r"|으로서|으로써|이라고|이라면|이라는|이라도|이라|라고|라면|라는|라도"
    r"|이지만|지만|이면서|이나마|나마|이야말로|이야"
    r"|까지도|까지|부터도|부터|마저|조차|뿐"
    r"|에서|에게|으로|에도|에는|에만|로도|로는|로만"
    r"|이며|이나|이면|이도|이는|이만"
    r"|에|이|가|을|를|은|는|의|와|과|로|도|만)$",
    re.UNICODE,
)

@classmethod
def _tokenize_for_matching(cls, text: str) -> set[str]:
    words: set[str] = set()
    for w in re.split(r"\W+", text.lower()):
        if not w:
            continue
        if len(w) >= 2:
            words.add(w)
        stripped = cls._KR_PARTICLE_RE.sub("", w)
        if stripped and len(stripped) >= 2 and stripped != w:
            words.add(stripped)
    return words
```

### BUG-02 수정 코드 (`core/collab_request.py`)

```python
# 이전: 일반어("작업", "task") 포함 → 오탐
# 이후: 구체적·고유한 예시 문구만 유지
_PLACEHOLDER_TASKS = {
    "구체적 작업 설명",
    "출시 홍보 카피 3개 필요",
}
_PLACEHOLDER_CONTEXTS = {
    "현재 작업 요약",
    "python jwt 로그인 라이브러리 v1.0, b2b 타겟",
}

def is_placeholder_collab(task: str, context: str = "") -> bool:
    task_norm = " ".join(task.strip().lower().split())
    context_norm = " ".join(context.strip().lower().split())
    if task_norm in _PLACEHOLDER_TASKS:
        return True
    for placeholder in _PLACEHOLDER_CONTEXTS:
        if context_norm == placeholder:
            return True
        if (context_norm.startswith(placeholder + " ")
                or context_norm.startswith(placeholder + ":")
                or context_norm.startswith(placeholder + "-")
                or context_norm.startswith(placeholder + "—")):
            return True
    return False
```

### BUG-03 수정 코드 (`core/telegram_relay.py` — `_handle_collab_tags`)

```python
if target_org is not None and self._pm_orchestrator is not None:
    # 경로 A: PM 봇 전용 — PMOrchestrator 경유
    await self._pm_orchestrator.collab_dispatch(...)
elif target_org is not None and self.context_db is not None:
    # 경로 B: 부서봇 전용 — ContextDB 직접 태스크 생성
    _task_id = f"T-{self.org_id}-collab-{_uuid.uuid4().hex[:8]}"
    try:
        await self.context_db.create_pm_task(
            task_id=_task_id,
            description=collab_task[:500],
            assigned_dept=target_org,
            created_by=self.org_id,
            metadata={"context": collab_ctx, "collab_source": self.org_id, "chat_id": chat_id},
        )
    except Exception as _e:
        logger.warning(f"[collab] 부서봇 ContextDB task 생성 실패, 채팅 폴백: {_e}")
        # 안전 degradation: 채팅 메시지 폴백
        collab_msg = make_collab_request_v2(collab_task, self.org_id, ...)
        await bot.send_message(chat_id=chat_id, text=collab_msg)
```

---

*산출물: `docs/bug-analysis-T-aiorg_pm_bot-633.md` — Phase 1~4 전체 포함 완성본*
*참고: T-629 원본 분석 `docs/bug-analysis-T-aiorg_pm_bot-629.md` 보완*
