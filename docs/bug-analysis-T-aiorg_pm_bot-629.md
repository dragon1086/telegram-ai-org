# 잔여 버그 3건 상세 원인 분석 및 수정 방안 보고서

**태스크 ID**: T-aiorg_pm_bot-629
**작성일**: 2026-03-26
**근거 소스**: `core/telegram_relay.py`, `core/collab_request.py`, T-aiorg_pm_bot-624 보고서

---

## Phase 1 — 버그 현황 요약표

| 버그 ID | 명칭 | 최초 보고 | 영향 모듈 | 재현 여부 | 증상 요약 |
|---------|------|----------|-----------|-----------|-----------|
| **BUG-01** ⚠️ | **한국어 조사 미분리** | T-aiorg_pm_bot-624 (2026-03-25) | `_infer_collab_target_org()` (`telegram_relay.py:651`) | ✅ 항상 재현 | "개발실에" 등 조사 포함 토큰이 haystack의 "개발실"과 불일치 → `target_org = None` 반환 가능 |
| **BUG-02** | 플레이스홀더 필터 오탐 | T-aiorg_pm_bot-624 (2026-03-25) | `is_placeholder_collab()` (`collab_request.py:62`) | ⚠️ 조건부 재현 | LLM이 시스템 프롬프트 예시 문구("현재 작업 요약")를 컨텍스트에 그대로 출력하면 정상 COLLAB 태그가 무음 드롭 |
| **BUG-03** | 부서봇 PM 오케스트레이터 미연결 | T-aiorg_pm_bot-624 (2026-03-25) | `_pm_orchestrator` 초기화 (`telegram_relay.py:173,205`) | ✅ 항상 재현 | 부서 봇의 `_pm_orchestrator = None` → COLLAB 태그 감지 후 실제 태스크 생성 불가, 채팅 메시지 폴백만 발생 |

---

### ⚠️ BUG-01 한국어 조사 미분리 — 증상 예시 샘플

**입력 예시 1:**
```
사용자 발화: "개발실에 버그 수정 요청"
re.split(r"\W+", ...) 결과 토큰: {"개발실에", "버그", "수정", "요청"}
haystack (개발실): "개발실 개발/코딩/api 구현/버그 수정 ..."
매칭 결과:
  - "개발실에" in haystack → ❌ False  (조사 "에" 포함)
  - "버그" in haystack     → ✅ True
  - "수정" in haystack     → ✅ True
score = 2 → 통과 (아슬아슬)
```

**입력 예시 2 (짧은 메시지):**
```
사용자 발화: "개발실에 부탁해"
토큰: {"개발실에", "부탁해"}
매칭:
  - "개발실에" → ❌
  - "부탁해" → ❌
score = 0 → target_org = None → 위임 실패
```

**입력 예시 3 (다양한 조사 변형):**
```
"디자인실의 UI 검토" → "디자인실의" ≠ "디자인실" → score 손실
"운영실에서 확인" → "운영실에서" ≠ "운영실" → score 손실
"기획실로 전달" → "기획실로" ≠ "기획실" → score 손실
```

---

## Phase 2 — 버그별 상세 원인 분석

---

### BUG-01: 한국어 조사 미분리

#### 직접 원인 (Proximate Cause)
`_infer_collab_target_org()` (line 651)에서 `re.split(r"\W+", task.lower())`를 사용해 입력 텍스트를 토크나이즈한다. Python의 `\W`는 **ASCII 기준**으로 `[^a-zA-Z0-9_]`를 의미하는데, 유니코드 모드에서는 한글을 포함한 모든 유니코드 단어 문자를 단일 토큰으로 묶는다. 결과적으로 "개발실에"는 분리되지 않고 하나의 토큰으로 유지된다.

```python
# 현재 코드 (line 651)
words = {w for w in re.split(r"\W+", task.lower()) if len(w) >= 2}
# "개발실에" → split 불가 → 단일 토큰으로 유지
```

#### 근본 원인 (Root Cause) — 가설 3개

**가설 A: 한국어 형태소 분석 부재**
한국어는 교착어(agglutinative language)로, 조사·어미가 어절에 직접 결합된다. `re.split()`은 공백/구두점 기반 단순 분리만 수행하므로, 형태소 단위 분리가 없으면 "개발실에", "개발실의", "개발실을" 등 조사 변형이 모두 별개 토큰이 된다. 근본적으로 형태소 분석 없이 키워드 매칭을 시도한 설계 한계.

**가설 B: score >= 2 임계값의 이분법 과다**
현재 score threshold가 `>= 2`이므로 첫 번째 토큰(org명 포함 어절)이 매칭 실패하면 남은 일반 단어로만 점수를 채워야 한다. 짧은 문장이거나 전문 키워드가 적은 경우 임계값 미달 → `None` 반환. 조사 미분리가 score를 기계적으로 1점 감소시키는 구조.

**가설 C: haystack 구성에 조사 변형 미포함**
haystack은 `org.dept_name + org.role + org.direction + org.specialties`의 조합이다. "개발실"은 있지만 "개발실에", "개발실의" 등 조사 변형은 haystack에 없다. 검색 방향(입력→haystack)만 있고 역방향 normalize(haystack→입력 정규화)는 없음.

#### 원인 레이어 분류
| 레이어 | 해당 여부 | 설명 |
|--------|----------|------|
| 로직(Logic) | ✅ 주원인 | 토크나이즈 정규화 로직 결여 |
| 데이터(Data) | ⬜ 부원인 | haystack에 조사 변형 없음 |
| 환경(Env) | ❌ 해당 없음 | — |

---

### BUG-02: 플레이스홀더 필터 오탐

#### 직접 원인 (Proximate Cause)
`is_placeholder_collab()` (collab_request.py:62-66)이 `context_norm in _PLACEHOLDER_CONTEXTS`로 **완전 일치(exact match)** 검사를 수행한다. `_PLACEHOLDER_CONTEXTS`에는 `"현재 작업 요약"`이 등록되어 있는데, PM 시스템 프롬프트 예시 템플릿이 그대로 `[COLLAB:...|맥락: 현재 작업 요약]` 형태이므로, LLM이 이를 그대로 복사 출력하면 정상 태그임에도 드롭된다.

```python
# collab_request.py:15-21
_PLACEHOLDER_CONTEXTS = {
    "ctx",
    "context",
    "맥락",
    "현재 작업 요약",           # ← 시스템 프롬프트 예시 문구와 동일
    "python jwt 로그인 라이브러리 v1.0, b2b 타겟",
}

# collab_request.py:62-66
def is_placeholder_collab(task: str, context: str = "") -> bool:
    task_norm = " ".join(task.strip().lower().split())
    context_norm = " ".join(context.strip().lower().split())
    return task_norm in _PLACEHOLDER_TASKS or context_norm in _PLACEHOLDER_CONTEXTS
    # ↑ exact match: "현재 작업 요약" == "현재 작업 요약" → True → 태그 드롭
```

#### 재현 시나리오
```
LLM 출력 (시스템 프롬프트 예시 기반):
[COLLAB:UI/UX 검토 요청|맥락: 현재 작업 요약]

is_placeholder_collab("UI/UX 검토 요청", "현재 작업 요약") 호출
→ context_norm = "현재 작업 요약"
→ "현재 작업 요약" in _PLACEHOLDER_CONTEXTS → True
→ 정상 COLLAB 태그임에도 무음 드롭
```

#### 근본 원인 (Root Cause)
시스템 프롬프트에서 LLM에게 COLLAB 태그 예시를 보여줄 때, 실제 `_PLACEHOLDER_CONTEXTS`에 등록된 예시 문구를 그대로 사용한 것이 원인. LLM이 템플릿을 모방할 경우 오탐이 발생하는 구조. 필터 등록 기준과 프롬프트 예시 문구 간 역참조 메커니즘이 없음.

#### 원인 레이어 분류
| 레이어 | 해당 여부 | 설명 |
|--------|----------|------|
| 로직(Logic) | ✅ 주원인 | exact match → 오탐 가능 |
| 데이터(Data) | ✅ 부원인 | 프롬프트 예시 = 필터 등록 문구 동일 |
| 환경(Env) | ❌ 해당 없음 | — |

---

### BUG-03: 부서봇 PM 오케스트레이터 미연결

#### 직접 원인 (Proximate Cause)
`_pm_orchestrator`는 `__init__`에서 `None`으로 초기화된 후(line 173), `self._is_pm_org and context_db is not None` 조건을 만족해야만 실제로 생성된다(line 205).

```python
# line 179-180
self._is_pm_org = ENABLE_PM_ORCHESTRATOR and org_id not in KNOWN_DEPTS
self._is_dept_org = ENABLE_PM_ORCHESTRATOR and org_id in KNOWN_DEPTS

# line 205: PM 봇에만 오케스트레이터 생성
if self._is_pm_org and context_db is not None:
    self._pm_orchestrator = PMOrchestrator(...)

# 부서 봇: _is_pm_org = False → _pm_orchestrator = None 유지
```

`_handle_collab_tags()` 내 dispatch 분기(line 1331):
```python
if target_org is not None and self._pm_orchestrator is not None:
    # 실제 PM 태스크 생성 (PM 봇만 진입)
    await self._pm_orchestrator.collab_dispatch(...)
# 부서 봇은 위 조건 불충족 → 이 블록 전혀 실행 안 됨
# 폴백: make_collab_request_v2() (채팅 메시지만 전송, 태스크 미생성)
```

#### 재현 시나리오
```
부서봇(예: aiorg_engineering_bot)이 COLLAB 태그 포함 응답 생성
→ _handle_collab_tags() 호출됨
→ is_placeholder_collab() 통과
→ _infer_collab_target_org() 호출 → target_org = "aiorg_design_bot"
→ if target_org is not None and self._pm_orchestrator is not None:
   → self._pm_orchestrator = None → 조건 실패
→ make_collab_request_v2()로 채팅 메시지만 전송
→ PM 봇이 해당 채팅 메시지를 COLLAB 요청으로 감지/처리하는 로직 없음
→ 위임 루프 미완성
```

#### 근본 원인 (Root Cause)
부서 봇의 COLLAB 처리 경로가 PM 봇을 경유하지 않고 독립 실행을 가정한 설계 → PM 봇만 실제 태스크 생성 권한을 갖는 구조에서, 부서 봇이 COLLAB을 감지했을 때 PM 봇에게 위임하는 중간 경로가 없음.

#### 원인 레이어 분류
| 레이어 | 해당 여부 | 설명 |
|--------|----------|------|
| 로직(Logic) | ✅ 주원인 | 부서봇 COLLAB → PM봇 라우팅 경로 미구현 |
| 데이터(Data) | ❌ 해당 없음 | — |
| 환경(Env) | ❌ 해당 없음 | — |

---

## Phase 3 — 수정 방안 비교표 및 종합 제언서

---

### BUG-01: 한국어 조사 미분리 — 수정 방안 비교

| 방안 | 구현 방법 | 예상 효과 | 난이도 | 부작용 리스크 |
|------|-----------|----------|--------|--------------|
| **방안 A** 규칙 기반 후처리 (권장) | `re.split()` 후 각 토큰 말미의 조사 패턴 제거<br>`re.sub(r'[은는이가을를에서으로의와과도만도로까지부터]$', '', word)` | 가장 빈번한 조사 처리 가능, 즉시 적용 가능 | 하 | 일부 고유 명사 변형(예: "로" 로 끝나는 이름) 오처리 가능 — 목록 세밀 조정 필요 |
| **방안 B** 형태소 분석 라이브러리 교체 | `konlpy(KoNLPy)` 또는 `kiwipiepy` 도입, `_infer_collab_target_org`에서 명사 추출 후 매칭 | 가장 정확한 처리, 복합어도 처리 | 상 | 추가 의존성(Java JVM 필요 등), 초기화 오버헤드(수백ms), Docker 이미지 크기 증가 |
| **방안 C** haystack에 조사 변형 추가 | org config의 dept_name에 조사 변형 문자열 추가(e.g. "개발실 개발실에 개발실의...") | 조사 문제만 해결, 코드 변경 최소화 | 하 | config 관리 부담, 신규 조직 추가 시 누락 위험 |

**권장**: **방안 A** 우선 적용 (즉시 효과, 낮은 위험), 중장기적으로 방안 B 검토.

---

### BUG-02: 플레이스홀더 필터 오탐 — 수정 방안 비교

| 방안 | 구현 방법 | 예상 효과 | 난이도 | 부작용 리스크 |
|------|-----------|----------|--------|--------------|
| **방안 A** `_PLACEHOLDER_CONTEXTS` 에서 일반 문구 제거 (권장) | `"현재 작업 요약"` 항목을 `_PLACEHOLDER_CONTEXTS`에서 삭제, 진짜 플레이스홀더(1~2단어 이하)만 유지 | 오탐 즉시 해소 | 하 | 잔여 플레이스홀더 오탐 가능성(단 _PLACEHOLDER_TASKS로 추가 방어) |
| **방안 B** 길이 기반 필터 추가 | `len(task_norm) <= 5` 이하이거나 `len(context_norm) <= 5` 이하일 때만 플레이스홀더로 간주 | 짧은 문구만 필터링 → 오탐 감소 | 하 | 짧은 실제 태스크(예: "QA 요청") 드롭 가능 |
| **방안 C** 접두사 매칭 완화 | exact match → `any(ctx.startswith(norm) for ctx in _PLACEHOLDER_CONTEXTS)` 역방향 검사 | 없음 (오히려 오탐 증가 가능) | 중 | 추천하지 않음 — 실제 태스크가 플레이스홀더 접두사를 포함하면 드롭 위험 |

**권장**: **방안 A** 즉시 적용. `"현재 작업 요약"`은 일반 업무 용어이므로 필터에서 제거하고, 진짜 플레이스홀더(한 단어, 영문 메타변수)만 유지.

---

### BUG-03: 부서봇 PM 오케스트레이터 미연결 — 수정 방안 비교

| 방안 | 구현 방법 | 예상 효과 | 난이도 | 부작용 리스크 |
|------|-----------|----------|--------|--------------|
| **방안 A** PM 봇 채널 폴백 경로 추가 (권장) | `_handle_collab_tags()`에서 `_pm_orchestrator is None`일 때 PM 봇 채팅 채널(group chat)로 `make_collab_request_v2()` 전송 후, PM 봇이 수신해 `_handle_pm_task()`로 처리하는 경로 연결 | 기존 채팅 메시지 폴백을 PM 봇이 실제 처리하도록 연결 — 구조 변경 최소화 | 중 | PM 봇이 채팅 메시지를 COLLAB 요청으로 파싱하는 안정성 의존 |
| **방안 B** 부서봇에 `context_db` 기반 COLLAB 요청 직접 쓰기 | `_pm_orchestrator` 없이도 `context_db.create_pm_task()`를 직접 호출해 태스크 생성 | 부서봇이 독립적으로 태스크 생성 가능 | 상 | context_db 접근 권한 확인 필요, TaskPoller 연동 별도 검증 필요 |
| **방안 C** BotBus P2P 메시지로 PM 봇에 직접 위임 | `self._p2p.send(pm_org_id, collab_request_msg)` 방식으로 PM 봇에 직접 전달 | 채팅 채널 우회, 확실한 전달 보장 | 중 | P2P 라우팅 구성 검증 필요, PM 봇 P2P 수신 핸들러 추가 필요 |

**권장**: **방안 A** 우선 적용 (기존 채팅 폴백 경로 활용, 최소 변경). 이후 방안 C를 병행 검토.

---

## 종합 제언서 — 수정 우선순위 및 권장 순서

| 우선순위 | 버그 ID | 분류 | 권장 방안 | 이유 |
|---------|---------|------|----------|------|
| 🔴 **1순위 (High)** | BUG-01 한국어 조사 미분리 | HIGH | 방안 A (규칙 기반 조사 제거) | 조사 포함 단어가 매 요청마다 score를 감소시켜 위임 실패 빈도가 가장 높음. 구현 난이도 낮음 |
| 🔴 **2순위 (High)** | BUG-02 플레이스홀더 오탐 | HIGH | 방안 A (`_PLACEHOLDER_CONTEXTS` 정리) | 정상 태그가 무음 드롭되는 보이지 않는 버그. 1줄 수정으로 해소 가능 |
| 🟡 **3순위 (Medium)** | BUG-03 부서봇 PM 미연결 | MEDIUM | 방안 A (채팅 채널 폴백 연결) | 구조적 미완성이지만 현재 위임 주체는 PM 봇 직접 경로이므로 운영 영향은 제한적. 단계적 수정 가능 |

### 권장 수정 순서

```
Step 1 (즉시, 난이도 하)
  → BUG-02: collab_request.py에서 "현재 작업 요약" 항목 제거
  → 예상 시간: 10분 이내

Step 2 (즉시, 난이도 하)
  → BUG-01: _infer_collab_target_org() 내 words 생성 직후
    조사 제거 후처리 1줄 추가
  → 예상 시간: 30분 이내 (테스트 포함)

Step 3 (차주, 난이도 중)
  → BUG-03: _handle_collab_tags()에 _pm_orchestrator=None 폴백 경로 추가
    + PM 봇 COLLAB 메시지 수신 처리 검증
  → 예상 시간: 2~4시간 (연동 테스트 포함)
```

### 리스크 요약

- **BUG-01 방안 A 적용 시**: 한글 조사 목록이 불완전하면 일부 어절이 남을 수 있음. 보완책: 조사 목록을 충분히 넓게 작성하거나 정규식 패턴을 형태소 클래스 기반으로 구성.
- **BUG-02 방안 A 적용 시**: 삭제 후 실제 플레이스홀더 방어가 약화될 수 있음. 보완책: `_PLACEHOLDER_TASKS`에 세밀한 항목 추가로 보완.
- **BUG-03 방안 A 적용 시**: 채팅 메시지 기반 폴백은 PM 봇이 해당 채널을 모니터링 중이어야 함. 보완책: P2P 방안(방안 C)을 병행 구현해 안정성 확보.

---

*산출물: 이 파일은 분석 문서 전용 — 코드·파일 변경 없음*
