# Weekly Multibot Discussion - Gap Analysis & Implementation Plan

> 2026-03-22 기준 분석

## 1. 현재 상태 (What Exists)

### GroupChatHub (`core/group_chat_hub.py`)
- **TurnManager.start_meeting()**: 참가 봇들에게 순서대로 발언 요청, 타임아웃 처리, 컨텍스트 공유 지원
- **GroupChatHub.register_participant()**: 봇별 speak_callback + domain_keywords 등록
- **GroupChatHub.start_meeting()**: 토픽 + 참여자 목록으로 구조화된 회의 실행
- 시작/종료 메시지 자동 전송, 봇 간 컨텍스트(이전 발언) 공유

### PMOrchestrator (`core/pm_orchestrator.py`)
- **discussion_dispatch()**: 자유 토론 모드. 참여 봇별 서브태스크 생성 + Telegram 알림 발송
- **_discussion_summarize()**: 라운드별 합성, 충돌/합의 감지, 핑퐁 재발행
- **_debate_synthesize()**: 관점 비교 후 PM 종합 판단 전송
- interaction_mode: "discussion" | "debate" 지원

### OrgScheduler (`core/scheduler.py`)
- **weekly_standup()** (매주 월 09:00): GroupChatHub 있으면 start_meeting() 호출 후 weekly_standup.py 실행
- **friday_retro()** (매주 금 18:00): GroupChatHub 있으면 start_meeting() 호출 후 retro 스크립트 실행
- GroupChatHub는 선택적 주입 (없으면 스킵)

### weekly_standup.py (`scripts/weekly_standup.py`)
- PM 봇 혼자 DB에서 지난 주 완료 태스크 집계 → 봇별 기여 요약 → Telegram 전송 + MD 저장
- 멀티봇 발언 없음 (단일 봇 보고서)

### weekly-review 스킬 (`skills/weekly-review/SKILL.md`)
- Step 1~5 정의: 데이터 수집(병렬) → 통합 보고서 → 하이라이트 → Rocky 보고 → 로그 저장
- "모든 부서 봇에게 동시에 요청"이라고 명시되어 있으나, 실제 구현은 PM이 단독 집계

## 2. 갭 (What's Missing)

| # | Gap | 설명 |
|---|-----|------|
| G1 | **speak_callback 미등록** | GroupChatHub에 봇들이 실제 등록되지 않음. TelegramRelay에서 hub 생성은 하지만 각 봇의 speak callback이 없음 |
| G2 | **봇별 주간보고 생성 로직** | 각 봇이 "이번 주 자기 부서 성과"를 자율적으로 생성하는 callback이 없음. DB 쿼리 + LLM 요약 필요 |
| G3 | **weekly-review → GroupChatHub 연결** | weekly-review 스킬 실행 시 GroupChatHub.start_meeting()을 트리거하는 연결 코드 없음 |
| G4 | **PM 종합 마무리** | 모든 봇 발언 후 PM이 종합 요약하는 로직 없음 (TurnManager는 단순 "완료" 메시지만 전송) |
| G5 | **봇 이모지/이름 포맷** | 현재 `**[bot_id]**` 형태. "Engineering Bot", "Design Bot" 등 사용자 친화적 이름 + 이모지 미적용 |

## 3. 구현 필요 최소 변경사항

### 3-1. `core/bot_weekly_speaker.py` (신규) — **Size: M**
- 각 봇의 주간보고 speak callback 구현
- DB에서 해당 봇의 지난 주 완료 태스크 조회
- LLM(또는 템플릿)으로 200자 이내 보고 생성
- `async def speak(topic, ctx) -> str` 시그니처

### 3-2. `core/telegram_relay.py` 수정 — **Size: S**
- GroupChatHub 생성 시 각 봇의 speak callback 등록
- organizations.yaml에서 봇 목록 로드 → register_participant() 호출

### 3-3. `core/scheduler.py` 수정 — **Size: S**
- weekly_standup()에서 GroupChatHub.start_meeting() 호출 후 PM 종합 요약 추가
- 또는 weekly-review 스킬에서 discussion_dispatch() 호출로 대체

### 3-4. `core/group_chat_hub.py` 수정 — **Size: S**
- TurnManager.start_meeting() 종료 시 PM 종합 요약 callback 지원
- 봇 display_name + 이모지 매핑 (organizations.yaml의 identity.display_name 활용)

### 3-5. `skills/weekly-review/` 스킬 로직 수정 — **Size: S**
- SKILL.md Step 1의 "모든 부서 봇에게 동시에 요청"을 GroupChatHub 기반 순차 발언으로 전환
- discussion_dispatch() 또는 start_meeting() 중 택 1

## 4. 구현 전략 권장

**Option A: GroupChatHub 기반 (권장)**
- 이미 TurnManager + start_meeting() 인프라가 있음
- 각 봇에 speak_callback만 등록하면 순차 발언 + 컨텍스트 공유 즉시 가능
- PM 종합 요약은 start_meeting() 완료 후 별도 호출

**Option B: discussion_dispatch 기반**
- 더 유연한 멀티라운드 핑퐁 가능
- 하지만 Telegram에서 실시간 순차 발언 UX보다는 태스크 기반 비동기 처리에 적합
- 주간회의의 "회의 느낌"과는 맞지 않음

**권장: Option A** — GroupChatHub + 봇별 speak_callback 등록

## 5. 예상 작업량 요약

| 항목 | Size | 비고 |
|------|------|------|
| bot_weekly_speaker.py 신규 | M | 봇별 DB 쿼리 + 보고 생성 |
| telegram_relay.py 수정 | S | register_participant 호출 추가 |
| scheduler.py 수정 | S | PM 종합 요약 추가 |
| group_chat_hub.py 수정 | S | display_name + 이모지 |
| weekly-review 스킬 수정 | S | start_meeting 연결 |
| **총합** | **M** | 핵심은 speak_callback 구현 |
