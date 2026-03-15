# ROADMAP.md — telegram-ai-org 자율 협업 AI 조직 로드맵

> **미션**: 단순 봇 모음에서 "진짜 회사처럼 자율 협업하는 AI 조직"으로 진화

---

## 현재 상태 (2026-03-16)

### 이미 구현된 것
| 컴포넌트 | 설명 | 상태 |
|---|---|---|
| `MessageBus` | 18종 이벤트 타입 async pub/sub | ✅ 완료 |
| `CrossOrgBridge` | 조직 간 Telegram 라우팅 | ✅ 완료 |
| `CollabRequest` | 이모지 기반 협업 요청 프로토콜 | ✅ 완료 |
| `DiscussionManager` | 5라운드 부서 간 토론 (PROPOSE/COUNTER/OPINION/REVISE/DECISION) | ✅ 완료 |
| `PMOrchestrator` | 사용자 요청 → 부서별 서브태스크 분해 | ✅ 완료 |
| `DispatchEngine` | 의존성 기반 자동 배분 | ✅ 완료 |
| `TaskGraph` | 태스크 의존성 그래프 | ✅ 완료 |
| `GoalTracker` | 목표 달성 추적 + 정체 감지 | ✅ 완료 |

### 아직 없는 것 (이 로드맵의 대상)
- 봇끼리 PM 없이 직접 통신 (P2P)
- 봇들이 공유하는 메모리 공간
- 자동 실행되는 팀 문화 (주간 회의, 회고)
- 봇 스스로 개선 제안 + 실험
- PM 없이 자율 태스크 분배

---

## Phase 1: P2P 협업 기반 (즉시 — 2026 W12)

> **테마**: 봇들이 PM을 거치지 않고 직접 협업

### 구현 완료
- [x] `P2P_MESSAGE` 이벤트 타입 추가 (`message_bus.py`)
- [x] `core/p2p_messenger.py` — 직접 봇 간 메시지 교환
  - `send(from, to, payload)` — 1:1 전송
  - `broadcast(from, payload)` — 전체 공지
  - `notify_task_done(from, task_id, summary)` — 완료 후 자동 알림
  - `request_collab(from, to, task)` — 협업 요청
- [x] `core/shared_memory.py` — 봇 간 공유 인메모리 상태
  - 네임스페이스 기반 키-값 저장
  - JSON 파일 영속화
  - `MEMORY_UPDATE` 이벤트 통합

### 다음 단계 (W12 내 완료 목표)
- [ ] `telegram_relay.py`에 P2PMessenger 인스턴스 주입
- [ ] 각 봇이 태스크 완료 시 `notify_task_done()` 호출
- [ ] SharedMemory를 `context_db`의 인메모리 캐시 레이어로 활용
- [ ] P2P 메시지 Telegram 그룹 에코 옵션 (디버그용)

### 완료 기준
> dev_bot이 작업 완료 후 analyst_bot에게 PM 없이 직접 결과를 전달하고, analyst_bot이 해당 결과를 기반으로 후속 분석을 실행한다

---

## Phase 2: 팀 문화 (2026 W13~14)

> **테마**: 봇들이 반성하고 성장하는 조직 문화

### 주간 회의 자동화
- [ ] `core/weekly_standup.py` — 주간 회의 오케스트레이터
  - 매주 월요일 09:00 자동 실행 (크론)
  - 각 봇: 지난 주 작업 요약 + 이번 주 계획 발표
  - PM봇: 팀 목표 재확인 + 우선순위 조정
  - 결과: `docs/standups/YYYY-WNN.md` 자동 생성

### 작업 회고 시스템
- [ ] `core/retrospective.py` — 런 완료 후 자동 회고
  - 각 run 종료 시 트리거
  - 잘된 점 / 아쉬운 점 / 다음번 개선점 기록
  - `SharedMemory`에 누적, `docs/retros/` 영속화

### 팀 메모리
- [ ] `core/team_memory.py` — 크로스 런 학습 누적
  - 이전 프로젝트 패턴 기억
  - 같은 실수 반복 방지
  - 성공 패턴 재활용

### 완료 기준
> 월요일 아침 자동 회의 로그가 생성되고, 각 run 완료 후 회고 파일이 자동으로 저장된다

---

## Phase 3: 자율 진화 (2026 W15~18)

> **테마**: 봇들이 스스로 더 나아지는 시스템

### 자기 개선 제안
- [ ] `core/improvement_tracker.py`
  - 봇들이 작업 중 발견한 개선 아이디어를 `SharedMemory`에 기록
  - 주기적으로 Rocky에게 개선 제안 Telegram 보고
  - 제안 → 승인 → 자동 실험 파이프라인

### A/B 실험 엔진
- [ ] `core/ab_tester.py`
  - 프롬프트 변형 A/B 테스트 자동 실행
  - 성과 지표 비교 (완료 시간, 품질 점수)
  - 승자 프롬프트 자동 채택

### 성과 지표 추적
- [ ] `core/metrics_reporter.py`
  - 태스크 완료율, 평균 처리 시간, 오류율 추적
  - 일일/주간 자동 보고
  - Telegram 대시보드 메시지

### 완료 기준
> 봇이 "이 태스크 유형에서 프롬프트 A가 B보다 30% 빠릅니다"라고 스스로 보고하고 채택을 제안한다

---

## Phase 4: 완전 자율 (2026 W19+)

> **테마**: Rocky가 개입 없이도 조직이 스스로 운영됨

### PM 없는 태스크 자율 분배
- [ ] `core/autonomous_distributor.py`
  - 태스크 성격을 봇들이 스스로 분석
  - 경험 기반 최적 담당자 자동 선정
  - PM은 최종 승인/거부만

### 봇 갭 감지 + 신규 봇 제안
- [ ] `core/gap_detector.py`
  - 반복 실패 패턴에서 "전문 봇 부재" 감지
  - Rocky에게 새 봇 생성 제안
  - 봇 청사진 자동 초안 생성

### 자율 로드맵 업데이트
- [ ] 봇들이 이 ROADMAP.md에 직접 완료 체크 + 새 아이템 제안
- [ ] 매월 1일 자동 진행 리뷰 + 다음 달 계획 생성

### 완료 기준
> Rocky가 2주 동안 지시 없이도 봇들이 스스로 태스크를 분배하고 완료하며, 월간 리포트를 자동 생성한다

---

## 기술 부채 (계속 관리)

| 항목 | 우선순위 | 담당 | 비고 |
|---|---|---|---|
| 샌드박스 실행 환경 | High | dev_bot | Claude Code 실행 보안 |
| 봇 토큰 rotation | Medium | pm_bot | 정기 갱신 자동화 |
| Context DB 백업 | Medium | pm_bot | 일일 자동 백업 |
| 메시지 재전송 로직 | High | dev_bot | Telegram API 실패 시 |
| P2P 메시지 내구성 | Medium | - | 재시작 후 미전달 메시지 처리 |

---

## 크론 스케줄 (Phase 2 이후)

| 주기 | 시간 | 작업 |
|---|---|---|
| 매주 월요일 | 09:00 KST | 주간 회의 트리거 |
| 매일 | 23:30 KST | 전날 작업 회고 자동 실행 |
| 매일 | 08:00 KST | 일일 메트릭 보고 |
| 매월 1일 | 10:00 KST | 월간 성과 리뷰 + 로드맵 업데이트 |

---

*최종 업데이트: 2026-03-16 — Phase 1 P2P 기반 구현 완료*
