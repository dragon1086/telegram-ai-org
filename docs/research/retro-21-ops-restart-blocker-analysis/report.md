# RETRO-21: 운영실 재기동 워크플로우 블로커 분석

> **리서치실 산출물** | 작성일: 2026-03-30 | 담당: aiorg_research_bot
> 태스크: T-aiorg_pm_bot-881 | 기준 커밋: 98540f3

---

## Executive Summary (PM 보고용 1-page)

**결론 (1줄)**: 98540f3 머지 이후 운영실 재기동은 **이미 2026-03-30 12:31~12:32 KST에 완료**되었으며, "진행 불가"의 직접 원인은 `restart_bots.sh` 실행 소요시간이 Bash 툴 타임아웃(120s)을 초과한 exit 143과, ORDER-GUARD 의존성 차단으로 재기동 태스크 자체가 큐에서 지연된 것이었다.

| 항목 | 내용 |
|------|------|
| **재기동 완료 시각** | 2026-03-30 12:31:29 KST (watchdog 플래그 감지 → 12:32:27 완료) |
| **현재 상태** | 전체 봇 7개 UP, watchdog PID=87121 정상 동작 |
| **실행 브랜치** | `.worktrees/bot-runtime` → HEAD `98540f3` (정상) |
| **잔여 플래그 파일** | `~/.ai-org/restart_requested` 없음 (watchdog 소비 완료) |
| **블로커 수** | 확인된 블로커 3건 — High 1개, Medium 1개, Low 1개 |

---

## 1. 조사 범위 및 방법

| 조사 항목 | 도구 | 결과 |
|-----------|------|------|
| 커밋 98540f3 diff | `git show 98540f3 --stat` | 63개 파일, +7,570/-297 라인 |
| 재기동 워크플로우 파일 | Read: `restart_bots.sh`, `bot_watchdog.py`, `bot_control.sh`, `request_restart.sh` | 완료 |
| 에러 로그 | Grep: `~/.ai-org/bot-watchdog.log`, `aiorg_ops_bot.log` | 완료 |
| 헬스체크 로그 | `~/.ai-org/bot_healthcheck.log` 최근 5건 파싱 | 완료 |
| 환경변수·CI | `.github/workflows/ci.yml` diff, `infra-baseline.yaml` | 완료 |

---

## 2. 타임라인 재구성

```
[2026-03-29 20:30 KST] 98540f3 커밋·푸시 완료 (총괄 PM)
[2026-03-29 20:30 KST] request_restart.sh 플래그 등록 (reason: 진보적 변경사항 선별 커밋 반영)
[2026-03-29 20:15~   ] 운영실 T-875 (재기동 상태 확인 태스크) ORDER-GUARD 차단 26초 후 실행
[2026-03-29 20:15~   ] 운영실 T-872 ORDER-GUARD 차단: T-870/T-871 running 상태 유지로 대기
[2026-03-29 20:18 KST] T-875 완료 — "봇은 fix/auto-2026-03-29-telegram_relay 브랜치 실행 중" 확인
[2026-03-29 이후]      운영실 실제 재기동 명령 → restart_bots.sh 실행 → exit 143 timeout
[2026-03-30 12:31:29]  watchdog PID=2673 플래그 감지 → restart_bots.sh 실행 시작
[2026-03-30 12:32:07]  전체 봇 7개 재시작 완료 (PID 87072~87117)
[2026-03-30 12:32:27]  watchdog PID=87121 정상 시작, 현재까지 안정 운영 중
```

---

## 3. 블로커 후보 목록 (우선순위 표)

| # | 우선순위 | 카테고리 | 블로커 | 근거 | 재현 조건 | 영향 범위 |
|---|----------|----------|--------|------|-----------|-----------|
| B-01 | **High** | (d) 코드 변경 호환성 | `restart_bots.sh` 실행시간 > Bash 툴 타임아웃(120s) → exit 143 | `~/.ai-org/bot-watchdog.log`: 플래그는 등록됐으나 ops bot 명령 exit 143 종료. `restart_bots.sh`는 stop→고아정리→세션리셋→start_all.sh 순차 실행으로 총 60~120+s 소요 | 운영실 봇이 `bash restart_bots.sh`를 직접 Bash 툴로 실행할 때마다 | 운영실 재기동 명령 무응답. 플래그 등록 후 watchdog에 위임됐으나, 운영실은 완료 여부를 실시간 확인 불가 |
| B-02 | **Medium** | (a) 의존 서비스 순서 | ORDER-GUARD가 상위 의존 태스크(T-874, T-870, T-871) running 상태 유지로 재기동 태스크 큐 차단 | `aiorg_ops_bot.log`: `T-aiorg_pm_bot-875` ORDER-GUARD 차단 20:15:08~20:15:34 (26초+), T-872는 T-870/T-871 완료 대기로 추가 지연 | 상위 태스크 실행 시간이 길거나 stuck 상태일 때 | 운영실 재기동 태스크가 실제 실행되기까지 수십 초~분 단위 지연 발생 |
| B-03 | **Low** | (d) 코드 변경 호환성 | `TeamProfile.__init__() got an unexpected keyword argument 'model'` — orchestration config 로드 실패 | `~/.ai-org/bot-watchdog.log`: `2026-03-29 07:53:18 ERROR orchestration config 로드 실패: TeamProfile.__init__() got an unexpected keyword argument 'model'` (2회 발생) | orchestration.yaml에 `model` 필드가 있으나 `TeamProfile` dataclass에는 `fallback_model`만 정의된 시점 | watchdog의 봇 목록 조회 실패 → 자동 재시작 불가 (98540f3 이전 발생, 현재 해소됨) |

---

## 4. 블로커별 상세 분석

### B-01: restart_bots.sh 타임아웃 (High)

**근거 (diff 위치)**
`scripts/restart_bots.sh`의 실행 순서:
1. `bot_control.sh stop all` — Python으로 모든 봇 프로세스 SIGTERM, 확인 대기
2. agent_monitor/watchdog PID 파일 기반 kill
3. 고아 프로세스 awk 스캔 + kill
4. tmux 세션 정리
5. Python으로 세션 JSON 리셋 (glob 전체 순회)
6. `start_all.sh` — 7개 봇 순차 nohup 기동 + watchdog 시작

**재현 조건**: Claude Code Bash 툴 타임아웃(기본 120s) 이내에 위 6단계가 완료되지 않으면 exit 143(SIGTERM) 발생.

**영향 범위**: 운영실 봇이 재기동을 직접 실행하면 항상 실패. `request_restart.sh` → watchdog 위임 경로만 실질적으로 동작함.

**현재 해소 여부**: watchdog가 플래그를 소비하여 재기동 완료. 다만 근본 원인(직접 실행 시 타임아웃)은 해소되지 않음 — 운영 규칙 준수로 우회 중.

---

### B-02: ORDER-GUARD 의존성 차단 (Medium)

**근거 (로그 라인)**
```
2026-03-29 20:15:08 WARNING [ORDER-GUARD] 태스크 T-aiorg_pm_bot-875 (aiorg_ops_bot) 차단:
  의존 태스크 T-aiorg_pm_bot-874 상태=running (미완료). 레이스 컨디션 차단 정상 동작.
(이후 20:15:34까지 2초마다 동일 경고 반복)
```

**분석**: T-875 (재기동 확인)와 T-872가 상위 태스크 완료를 기다리는 구조. 상위 태스크가 지연되면 운영 태스크 자체가 지연된다. 재기동과 같이 긴급성이 높은 태스크도 ORDER-GUARD를 통과해야 하는 구조적 한계.

**영향 범위**: 급박한 재기동 상황에서 태스크 처리가 수십~수백 초 지연 가능.

---

### B-03: TeamProfile 파라미터 미스매치 (Low, 해소됨)

**근거 (로그 라인)**
```
2026-03-29 07:53:18 ERROR bot_watchdog | orchestration config 로드 실패:
  TeamProfile.__init__() got an unexpected keyword argument 'model'
2026-03-29 07:53:48 ERROR (동일 에러 반복)
```

**분석**: `core/orchestration_config.py` 44번 줄: `fallback_model: str = ""` — `model` 필드가 없다. orchestration.yaml에 `model: xxx` 항목이 추가됐으나 dataclass가 업데이트되지 않은 시점에 발생. 98540f3 이후에는 로그에서 해당 에러 없음.

**해소 여부**: ✅ 98540f3 이후 동일 에러 미발생 (config 또는 dataclass가 정렬됨).

---

## 5. 현재 시스템 상태 (2026-03-30 조사 시점)

| 구성 요소 | 상태 | PID | 비고 |
|-----------|------|-----|------|
| aiorg_pm_bot | ✅ UP | 87097 | 98540f3 브랜치 |
| aiorg_engineering_bot | ✅ UP | 87078 | 98540f3 브랜치 |
| aiorg_design_bot | ✅ UP | 87072 | 98540f3 브랜치 |
| aiorg_growth_bot | ✅ UP | 87085 | 98540f3 브랜치 |
| aiorg_product_bot | ✅ UP | 87111 | 98540f3 브랜치 |
| aiorg_research_bot | ✅ UP | 87117 | 98540f3 브랜치 |
| aiorg_ops_bot | ✅ UP | 87091 | 98540f3 브랜치 |
| bot_watchdog | ✅ UP | 87121 | 30초 간격 헬스체크 |
| restart_requested 플래그 | ✅ 없음 | — | watchdog 소비 완료 |

---

## 부록: 재기동 체크리스트 초안

> **⚠️ 리서치실 제안 전용** — 실제 수정·적용은 운영실·개발실 담당

### 즉시 확인 (Before 재기동 명령)

- [ ] **B-01 우회 확인**: `bash scripts/request_restart.sh --reason "..."` 경로 사용 중인지 확인 (직접 `restart_bots.sh` 실행 금지)
- [ ] **watchdog 실행 여부**: `ps aux | grep bot_watchdog` — PID 확인 필수. watchdog가 없으면 플래그 소비 불가
- [ ] **restart_requested 플래그 미중복**: `ls ~/.ai-org/restart_requested` — 이미 있으면 watchdog가 처리 중 (재등록 불필요)
- [ ] **상위 태스크 상태**: ORDER-GUARD 차단 여부 — 상위 의존 태스크 running 상태 길어지면 재기동 태스크 지연됨

### 재기동 후 검증

- [ ] **봇 프로세스 PID 교체 확인**: `ps aux | grep main.py` — 이전 PID가 새 PID로 교체됐는지 확인
- [ ] **브랜치 확인**: `~/.ai-org/bot-watchdog.log` — `HEAD is now at [커밋 해시]` 로그 확인
- [ ] **watchdog 신규 PID 확인**: restart 후 새 watchdog PID 등록 여부
- [ ] **헬스체크 로그 확인**: `~/.ai-org/bot_healthcheck.log` 최신 엔트리에서 전체 봇 UP 상태 확인
- [ ] **heartbeat 파일 갱신**: `ls -la ~/.ai-org/*.heartbeat` — 60초 이내 mtime 갱신 확인

### 블로커 해소 순서 (우선순위 순)

1. **B-01 (High)**: 운영실은 항상 `request_restart.sh` → watchdog 위임 경로만 사용. `restart_bots.sh` 직접 실행은 운영 규칙 위반 + 타임아웃 확실히 발생
2. **B-02 (Medium)**: ORDER-GUARD 차단 시 최대 대기 시간 상한선 설정 검토 (개발실 협의 필요) — 긴급 재기동 태스크는 우선순위 레인 분리 고려
3. **B-03 (Low, 해소됨)**: `orchestration.yaml`에 신규 필드 추가 시 `TeamProfile` dataclass 동시 업데이트 규칙 추가

---

## 참고 파일

| 파일 | 용도 |
|------|------|
| `scripts/request_restart.sh` | 안전 재기동 플래그 등록 스크립트 |
| `scripts/bot_watchdog.py` | 플래그 소비 + 실제 재기동 실행 (RESTART_FLAG 처리 라인 271~313) |
| `scripts/restart_bots.sh` | 실제 재기동 스크립트 (직접 실행 시 exit 143 위험) |
| `~/.ai-org/bot-watchdog.log` | watchdog 재기동 이력 로그 |
| `~/.ai-org/bot_healthcheck.log` | 봇 UP/DOWN 상태 이력 (30분 간격) |
| `~/.ai-org/aiorg_ops_bot.log` | ORDER-GUARD 차단 이력 포함 |

---

*보고서 생성: 리서치실 PM (aiorg_research_bot) | 2026-03-30*
*Phase 1~3 완료 | 조사 범위: 커밋 diff, 프로세스 로그, watchdog 이력, 헬스체크 이력*
