# 멀티봇 그룹채팅 참여 설계 의도 & 갭 분석
**작성일**: 2026-03-22 | **작성자**: PM (aiorg_product_bot)

---

## 결론 요약

**첨부파일 안 오는 이유 (즉시 확인 가능)**: `prepare_upload_bundle()`이 파일 미존재 시 경고 없이 `[]` 반환 → 업로드 시도 자체가 무음 실패. 로그에 "업로드 실패" 메시지도 안 남음.

**멀티봇 그룹채팅 설계 vs. 현실**: 설계 의도(모든 봇이 자율 채팅 참가 + PM 중재)는 **현재 구현되어 있지 않음**. OrgScheduler는 PM봇 단독 `send_text`에만 연결되어 있고, 부서봇들은 정기 활동에 능동적으로 참가하는 메커니즘이 없음.

---

## Phase 1: 설계 의도 정의서

### 1-A. 원래 의도한 구조 (사용자 명시 요구사항)

```
[텔레그램 그룹방]
  ↓ 트리거 (크론/이벤트)
  ├── PM봇: "주간회의 시작합니다. 각 팀 한 주 성과 공유해주세요."
  ├── engineering봇: (자율 발언) "이번 주 완료: ... / 이슈: ..."
  ├── design봇: (자율 발언) "디자인 리뷰 3건 완료, 다음 주 목표..."
  ├── growth봇: (자율 발언) "지표 분석 결과..."
  ├── research봇: (자율 발언) "시장조사 완료..."
  └── PM봇: (중재·취합) "종합하면: ... / 다음 주 팀 목표: ..."
```

### 1-B. 이상적 시퀀스 (멀티봇 Discussion 흐름)

```
Step 1. [트리거] 크론스케줄 or 사용자 "@pm봇 주간회의"
   └─ PM봇: 회의 어젠다 발표 + 각 부서봇에 [PM_TASK:weekly_standup] 브로드캐스트

Step 2. [각 부서봇 자율 발언 — 병렬 또는 순차]
   └─ engineering/design/growth/research 봇이 각자 그룹방에 주간 성과 발언

Step 3. [PM봇 중재 라운드]
   └─ 발언 취합 → Discussion Protocol 적용 → 합의 확인 또는 추가 질문

Step 4. [PM봇 취합 발언]
   └─ 종합 요약 + 다음 주 목표 선언 → 텔레그램 전송

Step 5. [종료 조건]
   └─ max_rounds 도달 or 합의 감지 → 회의 종료 메시지
```

### 1-C. 이미 논의된 맥락과의 연결

| 항목 | 메모리 내용 | 연관성 |
|------|------------|--------|
| Discussion 멀티라운드 핑퐁 | 완료 (commit f927c10) | 부서봇간 핑퐁 기반은 구현됨 |
| `[PM_TASK:]` 태그 처리 | 부서봇에 구현됨 | 트리거 전달 채널로 활용 가능 |
| `_handle_discussion_message` | telegram_relay.py 1513 | 토론 메시지 수신 메커니즘 존재 |
| `OrgScheduler.weekly_standup` | scheduler.py 191 | PM봇 단독 발언만 구현됨 |

---

## Phase 2: 현재 구현 현황 + 갭 분석

### 2-A. 첨부파일 전송 현황 (즉시 점검)

#### 현재 플로우
```
LLM 응답 → extract_local_artifact_paths() → prepare_upload_bundle() → upload_file()
```

#### 발견된 버그/갭

| # | 위치 | 문제 | 심각도 |
|---|------|------|--------|
| A1 | `artifact_pipeline.py:prepare_upload_bundle()` | 파일 미존재 시 `[]` 반환 + **경고 로그 없음** → 무음 실패 | 🔴 HIGH |
| A2 | `telegram_user_guardrail.py:LOCAL_PATH_RE` | `(?:(?<=\s)\|^)` — `^`는 멀티라인 미적용 → 첫 번째 경로만 `^`에 매칭, 나머지는 `\s` lookbehind 의존 | 🟡 MEDIUM |
| A3 | `telegram_relay.py:_auto_upload()` | `prepare_upload_bundle()` 반환값이 빈 리스트일 때 로그 없이 스킵 → 디버그 불가 | 🔴 HIGH |
| A4 | LLM 응답 포맷 | `[ARTIFACT:경로]` 마커 사용이 강제되지 않음 → LLM이 경로를 인라인 텍스트로 쓰면 감지 가능하나 guarantee 없음 | 🟡 MEDIUM |
| A5 | `scheduler.py` 정기 활동 | `morning_goals.py`, `daily_retro.py` 등 스크립트가 파일 생성 후 경로를 `_auto_upload`에 전달하지 않음 | 🔴 HIGH |

#### 가장 유력한 원인 (지금 바로 확인 필요)
```
prepare_upload_bundle()이 source.exists() == False로 [] 반환
→ path_text 계산 시 ~이 있으면 expanduser() 처리 됨
→ 하지만 실제 파일이 없거나 경로가 틀리면 무음 스킵
```

**즉시 진단 방법**: `logs/` 에서 `[auto_upload:` 검색 — "업로드 완료" 없고 "업로드 실패"도 없으면 A1/A3 확인

---

### 2-B. 멀티봇 그룹채팅 참여 현황 요약표

| 구현 항목 | 설계 의도 | 현재 구현 상태 | 갭 |
|----------|---------|--------------|-----|
| PM봇 정기 발언 (주간회의·회고) | PM봇이 그룹방에 발언 | ✅ 구현됨 (OrgScheduler + send_text) | - |
| 부서봇 자율 발언 트리거 | 크론/이벤트 수신 후 각 봇이 자율 발언 | ❌ 미구현 | 전체 부재 |
| 그룹방 메시지 수신 필터 | 자기 채팅방 ID 일치 시에만 처리 | ✅ `allowed_chat_id` 체크 구현 | - |
| 봇 메시지 수신·반응 | 봇이 보낸 메시지에도 반응 가능 | 🟡 부분 구현 (`[PM_TASK:]`, `[COLLAB:]` 한정) | 자율 발언 트리거 없음 |
| PM 중재 로직 (발언 순서 제어) | PM이 각 봇 발언 수집 후 종합 | ❌ 미구현 | 수집·순서제어 전무 |
| Discussion 멀티라운드 | 합의/충돌 감지 + 라운드 진행 | ✅ 구현됨 (commit f927c10) | 정기 활동에 연결 안 됨 |
| 주간회의 시 모든 봇 발언 | engineering/design/growth/research 봇 각각 발언 | ❌ 미구현 | 브로드캐스트 메커니즘 없음 |
| 회고 취합 | 각 봇 회고 → PM 종합 발언 | ❌ 미구현 | PM 단독 회고만 존재 |

---

### 2-C. 갭 분석 테이블 (Gap Analysis Table)

| GAP ID | 구성요소 | 설계 의도 | 현재 상태 | 우선순위 | 구현 난이도 | 필요 변경 |
|--------|---------|---------|---------|---------|-----------|---------|
| G1 | 부서봇 주간회의 자율 발언 | 모든 봇이 각자 그룹방에 주간 성과 발언 | ❌ 완전 미구현 | 🔴 HIGH | 중간 | OrgScheduler에 "broadcast to dept bots" 로직 추가 |
| G2 | PM 브로드캐스트 메커니즘 | PM이 [PM_TASK:weekly_standup] 각 봇에 전달 | ❌ 완전 미구현 | 🔴 HIGH | 낮음 | P2PMessenger 활용해 all orgs에 태스크 발송 |
| G3 | 부서봇 발언 취합 | PM이 각 봇 발언 수집 후 종합 | ❌ 완전 미구현 | 🔴 HIGH | 높음 | 발언 대기 + 타임아웃 + 취합 로직 |
| G4 | 첨부파일 무음 실패 | 파일 업로드 성공/실패 로그 | ❌ 경고 없이 스킵 | 🔴 HIGH | 낮음 | `prepare_upload_bundle()` 실패 시 경고 로그 추가 |
| G5 | Discussion ↔ 정기활동 연결 | 주간회의가 Discussion 프로토콜 사용 | ❌ 미연결 | 🟡 MEDIUM | 중간 | `weekly_standup()`에서 `discussion_dispatch()` 호출 |
| G6 | 부서봇 OrgScheduler 부재 | 각 봇도 정기 활동 인지 | ❌ PM봇만 스케줄러 있음 | 🟡 MEDIUM | 중간 | 부서봇에 경량 스케줄러 또는 P2P 수신 대기 |
| G7 | `[ARTIFACT:]` 마커 비강제 | LLM이 파일 경로를 마커로 감싸야 함 | 🟡 관례만 존재, 강제 안 됨 | 🟡 MEDIUM | 낮음 | 시스템 프롬프트에 마커 사용 강제 지시 추가 |
| G8 | 회고 멀티봇 참여 | 금요일 회고 시 각 팀 기여 | ❌ PM봇 단독 회고 | 🟡 MEDIUM | 중간 | G1·G2 해결 후 회고 스크립트 확장 |

---

### 2-D. 우선순위별 미구현 항목 목록

#### 🔴 HIGH (즉시 조치 권고)

1. **[G4] 첨부파일 무음 실패 로그 추가**
   - 파일: `core/artifact_pipeline.py` — `prepare_upload_bundle()` 내 `return []` 전에 `logger.warning(f"파일 없음: {source}")` 추가
   - 파일: `core/telegram_relay.py` — `_auto_upload()` 내 bundle이 빈 리스트일 때 `logger.warning(f"업로드 대상 없음: {path_text}")` 추가
   - 예상 공수: 30분

2. **[G2] PM 브로드캐스트 메커니즘 구현**
   - `P2PMessenger.send_to_all_orgs(task_type, payload)` 메서드 추가 또는 기존 `p2p_messenger.py` 활용
   - `OrgScheduler.weekly_standup()` 에서 각 부서봇에 `[PM_TASK:weekly_standup_contribution]` 전송
   - 예상 공수: 반나절

3. **[G1] 부서봇 주간회의 자율 발언**
   - 부서봇이 `[PM_TASK:weekly_standup_contribution]` 수신 시 자기 주간 실적 LLM 생성 후 그룹방 발언
   - 예상 공수: 1일

#### 🟡 MEDIUM (G2·G1 완료 후 순차 진행)

4. **[G3] PM 발언 취합 로직** — 부서봇 발언 수집 대기 + 타임아웃 + 종합 발언 (예상 공수: 1일)
5. **[G5] Discussion ↔ 정기활동 연결** — `weekly_standup()`에서 `discussion_dispatch()` 호출 (예상 공수: 반나절)
6. **[G7] `[ARTIFACT:]` 마커 강제** — 시스템 프롬프트 수정 (예상 공수: 30분)

#### 🟢 LOW (향후)

7. **[G6] 부서봇 경량 스케줄러** — P2P 수신 대기로 대체 가능해 우선순위 낮음
8. **[G8] 회고 멀티봇 참여** — G1~G3 완료 후 자동 해결

---

## 다음 조치 권고 (즉시)

1. **첨부파일 진단**: `grep -r "auto_upload\|upload_file" logs/` 로 실제 에러 확인 후 G4 패치
2. **G4 패치 (30분)**: `@aiorg_engineering_bot` 에 위임 권고
3. **G2 설계 검토**: P2PMessenger 활용 브로드캐스트 → 별도 PRD 작성 후 engineering 위임

---

*이 문서는 `/Users/rocky/telegram-ai-org/docs/multibot_group_chat_gap_analysis.md`에 저장됨*
