# telegram-ai-org v1.1.0

> **v1.0.0 이후 신규 기능 + 버그 수정 누적 릴리스**

## 🚀 New Features

### Rate Limiting + Metrics + Audit Log REST API (Phase 3-A)
- Rate Limiting 미들웨어 추가 — 조직별 요청 throttle 지원
- Metrics 수집 엔드포인트 신설
- Audit Log REST API 확장

### harness + hermes-agent 핵심 패턴 이식 (Phase 2)
- harness 실행 패턴 및 hermes-agent 메시지 라우팅 이식
- 983개 테스트 전체 통과 검증

### 세션 자동 로테이션
- 컨텍스트 누적 방지를 위한 세션 자동 로테이션 구현
- 장시간 실행 시 메모리 누수 방지

### PM 2-pass 위임 구조 + Gemini 2.5-flash GA 폴백
- PM 위임 시 2-pass 구조로 품질 향상
- Gemini 2.5-flash GA 폴백 로직 추가

### Pre-flight 검증 자동화 (RETRO-01)
- E2E 실행 전 인프라 체크리스트 자동 검증
- timeout/filter/env 검증 포함

### 페르소나명 표시 개선
- 팀 구성 출력에서 추상 역할명 → 실제 페르소나명 자동 해소
- `load_personas()` glob→rglob 변경으로 하위 디렉토리 에이전트 인식

### 기타 신규
- AI_ORG_DATA_DIR 환경변수 도입 — 산출물/데이터 저장 경로 표준화
- JIT 맥락 수집 필터링 및 범위 최적화
- COLLAB 브로드캐스트 복원 + weekly_meeting target_mentions 추가

---

## 🐛 Bug Fixes

- `RetroMemory.get_week_entries()` UTC/로컬 타임존 불일치 수정 (테스트 실패 원인 해소)
- `_weekly_meeting_automation` no-op 동작과 테스트 동기화 (중복 발송 방지 설계 반영)
- `daily_retro` 중복 실행 제거 + `create_pm_task` 시그니처 버그 수정
- 하트비트 DB 동기화, JIT 맥락 새로고침 및 메모리 요약 로직 개선
- `_remote_org_speak` chat_id 버그 + StalenessChecker 이벤트 루프 타이밍 수정
- `_reply_with_pm_chat`에서 COLLAB 태그 미처리 버그 수정
- `_read_stream()`/`_read_stdout()`에 asyncio.LimitOverrunError 예외 처리 추가
- SynthesisPoller 무한 재합성 루프 — Goal(G-*) 상태 미갱신 수정
- CONFLICTING 판정 시 pm_goals 상태 needs_review 업데이트
- GoalTracker E2E 테스트 NameError 3건 수정
- cascade-cancel dependent tasks on failure + /engine 명령어

---

## 🧪 Test Coverage

| 이전 (v1.0.0) | 이후 (v1.1.0) |
|---------------|---------------|
| 2,527 passed  | **2,443 passed** (e2e 제외 기준) |
| 0 failed      | **0 failed** |

---

## Upgrade

```bash
git pull origin main
pip install -e .
```

---

*Released: 2026-03-29*
