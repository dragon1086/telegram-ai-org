# 자율 진화 자동화 설계 — Cron & Scheduled Tasks

> telegram-ai-org가 스스로 성장하는 AI 조직이 되기 위한 크론 자동화 설계서

---

## 크론 스케줄 전체 요약

```
# ┌──── 분 (0-59)
# │ ┌──── 시 (0-23, KST)
# │ │ ┌──── 일 (1-31)
# │ │ │ ┌──── 월 (1-12)
# │ │ │ │ ┌──── 요일 (0=일, 1=월, ..., 7=일)
# │ │ │ │ │
# 0 9 * * 1   주간 회의 (매주 월요일 09:00)
# 30 23 * * * 일일 회고 (매일 23:30)
# 0 8 * * *   일일 메트릭 (매일 08:00)
# 0 10 1 * *  월간 리뷰 (매월 1일 10:00)
```

---

## 1. 주간 회의 (Weekly Standup)

**트리거**: 매주 월요일 09:00 KST
**스크립트**: `scripts/weekly_standup.py`

### 흐름
```
1. PM봇: 지난 주 완료 태스크 목록 집계 (ContextDB)
2. 각 봇: SharedMemory에서 자신의 주간 요약 읽기
3. PM봇: Telegram 그룹에 회의록 초안 게시
4. 각 봇: 이번 주 목표 1~3개 기록 → SharedMemory에 저장
5. 결과: docs/standups/YYYY-WNN.md 생성
6. Rocky에게 Telegram 알림
```

### 예시 출력 (`docs/standups/2026-W13.md`)
```markdown
# 주간 회의 — 2026 W13 (2026-03-23)

## dev_bot
- 지난 주: FastAPI 서버 구현, 단위 테스트 12개 추가
- 이번 주: OAuth 연동, CI 파이프라인 설정

## analyst_bot
- 지난 주: 시장 조사 보고서 2건
- 이번 주: 경쟁사 분석 심화

## PM 목표
- Sprint 목표: 사용자 인증 플로우 완성
```

### 크론 등록
```bash
# crontab -e
0 0 * * 1 cd /Users/rocky/telegram-ai-org && \
  source venv/bin/activate && \
  python scripts/weekly_standup.py >> logs/standup.log 2>&1
```
> 참고: KST(UTC+9) 기준 월요일 09:00 = UTC 일요일 00:00

---

## 2. 일일 작업 회고 (Daily Retrospective)

**트리거**: 매일 23:30 KST
**스크립트**: `scripts/daily_retro.py`

### 흐름
```
1. 오늘 완료된 run 목록 조회 (ContextDB)
2. 각 run에 대해:
   a. 성공 여부, 소요 시간 집계
   b. 오류/재시도 발생 여부 확인
   c. 잘된 점 / 개선점 자동 분석 (LLM 활용)
3. SharedMemory["retro"][오늘날짜] 저장
4. team_memory.py에 학습 내용 누적
5. docs/retros/YYYY-MM-DD.md 생성
6. 이슈 발견 시 Rocky에게 즉시 Telegram 알림
```

### 예시 출력 (`docs/retros/2026-03-23.md`)
```markdown
# 작업 회고 — 2026-03-23

## 오늘 완료된 태스크: 7건
- T-042: API 설계 (dev_bot, 12분) ✅
- T-043: 문서 작성 (docs_bot, 8분) ✅
- T-044: 보안 검토 (security_bot, 15분) ⚠️ 1회 재시도

## 잘된 점
- P2P 협업으로 T-042→T-043 연계가 PM 없이 자동 처리됨

## 개선 필요
- T-044에서 Telegram API 타임아웃 발생 → 재전송 로직 강화 필요

## 내일 주의사항
- Telegram 재전송 로직 검토 (기술 부채 항목)
```

### 크론 등록
```bash
30 14 * * * cd /Users/rocky/telegram-ai-org && \
  source venv/bin/activate && \
  python scripts/daily_retro.py >> logs/retro.log 2>&1
```
> KST 23:30 = UTC 14:30

---

## 3. 일일 메트릭 보고 (Daily Metrics)

**트리거**: 매일 08:00 KST
**스크립트**: `scripts/daily_metrics.py`

### 수집 지표
| 지표 | 설명 |
|---|---|
| `task_completion_rate` | 완료 태스크 / 전체 태스크 (%) |
| `avg_task_duration_sec` | 태스크 평균 소요 시간 |
| `p2p_message_count` | P2P 메시지 수 (PM 경유 vs 직접) |
| `retry_count` | 재시도 발생 횟수 |
| `error_rate` | 오류율 (%) |
| `bot_utilization` | 봇별 활성 시간 비율 |

### 출력
```
📊 일일 메트릭 — 2026-03-23

✅ 완료율: 94.4% (17/18)
⏱ 평균 시간: 11.2분
💬 P2P 메시지: 34건 (PM 직접: 8, 봇간 직접: 26)
🔄 재시도: 2건
❌ 오류율: 5.6%
```

### 크론 등록
```bash
0 23 * * * cd /Users/rocky/telegram-ai-org && \  # KST 08:00 = UTC 23:00
  source venv/bin/activate && \
  python scripts/daily_metrics.py >> logs/metrics.log 2>&1
```

---

## 4. 월간 성과 리뷰 + 로드맵 업데이트 (Monthly Review)

**트리거**: 매월 1일 10:00 KST
**스크립트**: `scripts/monthly_review.py`

### 흐름
```
1. 지난 달 모든 회고 파일 집계
2. 핵심 지표 월간 트렌드 분석
3. ROADMAP.md 진행 상태 자동 업데이트 (완료 항목 체크)
4. 다음 달 자동 계획 초안 생성
5. Rocky에게 Telegram 보고 + 승인 요청
6. docs/monthly/YYYY-MM.md 생성
```

### 크론 등록
```bash
0 1 1 * * cd /Users/rocky/telegram-ai-org && \  # KST 10:00 = UTC 01:00
  source venv/bin/activate && \
  python scripts/monthly_review.py >> logs/monthly.log 2>&1
```

---

## 5. 런타임 트리거 (크론 아님 — 이벤트 기반)

이하 항목은 크론이 아닌 이벤트 기반으로 자동 실행:

| 이벤트 | 트리거 조건 | 액션 |
|---|---|---|
| `TASK_STATE_CHANGED` → `done` | 태스크 완료 시 | `notify_task_done()` → 관련 봇 알림 |
| `GOAL_STAGNATED` | 목표 정체 감지 | Rocky에게 즉시 알림 |
| `DISCUSSION_TIMED_OUT` | 토론 시간 초과 | PM 강제 결정 요청 |
| 매일 자정 | 오늘 SharedMemory 스냅샷 | `shared_memory.json` 백업 |

---

## 구현 우선순위

| 단계 | 스크립트 | 의존성 | 예상 구현 시간 |
|---|---|---|---|
| Phase 1 (완료) | `p2p_messenger.py`, `shared_memory.py` | — | 완료 |
| Phase 2-A | `scripts/daily_retro.py` | `shared_memory.py` | 1~2일 |
| Phase 2-B | `scripts/weekly_standup.py` | `daily_retro.py` | 1~2일 |
| Phase 2-C | `core/team_memory.py` | `shared_memory.py` | 2~3일 |
| Phase 3-A | `scripts/daily_metrics.py` | `context_db.py` | 1일 |
| Phase 3-B | `core/improvement_tracker.py` | `team_memory.py` | 3~5일 |
| Phase 4 | `scripts/monthly_review.py` | 모두 | 1주일 |

---

## 로그 구조

```
logs/
├── standup.log      # 주간 회의 실행 로그
├── retro.log        # 일일 회고 실행 로그
├── metrics.log      # 일일 메트릭 로그
└── monthly.log      # 월간 리뷰 로그

docs/
├── standups/
│   └── YYYY-WNN.md  # 주간 회의록
├── retros/
│   └── YYYY-MM-DD.md # 일일 회고
└── monthly/
    └── YYYY-MM.md   # 월간 리뷰
```

---

*작성: 2026-03-16 — telegram-ai-org 자율 진화 설계*
