# ROADMAP.md — telegram-ai-org 구현 로드맵

## Phase 1 (Week 1): 뼈대 구축

### 목표
기본 메시지 라우팅 + PM/Worker 봇 통신 검증

### 태스크
- [ ] PM Bot 기본 구현 (메시지 수신 → 파싱 → 라우팅)
- [ ] Worker Bot 베이스 클래스 구현
- [ ] OrgMessage 스키마 완성 + 검증 테스트
- [ ] Shared Context DB 기초 스키마 설정
- [ ] 1개 Worker Bot (dev_bot) 연동 테스트
- [ ] 기본 E2E 테스트: 유저 요청 → PM → dev_bot → 보고

### 완료 기준
- Telegram 그룹에서 유저 메시지 → PM이 dev_bot에 태스크 할당 → dev_bot이 `echo "hello"` 실행 후 보고

---

## Phase 2 (Week 2): 실행 엔진 연동

### 목표
dev_bot에서 실제 Claude Code 실행 + 태스크 상태 추적

### 태스크
- [ ] Claude Code Runner 구현 (subprocess 래퍼)
- [ ] dev_bot → Claude Code 실행 → 결과 파싱 → 보고
- [ ] Task Manager 구현 (상태: pending → running → done/failed)
- [ ] Context DB CRUD 완성
- [ ] PM Bot: 태스크 상태 기반 다음 단계 결정

### 완료 기준
- `dev_bot에서 "파이썬 웹서버 코드 작성해줘"` → Claude Code 실행 → 실제 파일 생성 → PM에 결과 보고

---

## Phase 3 (Week 3): 팀 확장 + 완료 프로토콜

### 목표
3개 봇 팀 운영 + 완료 검증 프로토콜 구현

### 태스크
- [ ] analyst_bot 구현 (amp MCP 또는 web search 연동)
- [ ] docs_bot 구현 (markdown 생성 특화)
- [ ] Completion Protocol 구현
  - PM이 완료 판단 → `[TO: ALL]` 확인 요청
  - 각 봇의 ack 수집
  - 전체 확인 후 CLOSED 처리
- [ ] 병렬 태스크 실행 (dev + analyst 동시)

### 완료 기준
- 복잡한 프로젝트 요청 → 3개 봇이 병렬 작업 → 각자 완료 보고 → PM이 최종 CLOSED

---

## Phase 4 (Week 4+): 고도화

### 목표
프로덕션 레벨 신뢰성 + 확장성

### 태스크
- [ ] 동적 봇 추가/제거 (플러그인 레지스트리)
- [ ] 벡터 컨텍스트 검색 (sqlite-vec 활성화)
- [ ] 에러 복구: 봇 실패 시 PM이 재할당
- [ ] 웹 대시보드 (태스크 상태 시각화)
- [ ] Codex Runner 연동
- [ ] 멀티 그룹 지원 (프로젝트별 Telegram 그룹)
- [ ] 메트릭 수집 (태스크 완료율, 평균 시간 등)

---

## 기술 부채 관리

| 항목 | 우선순위 | 비고 |
|---|---|---|
| 샌드박스 실행 환경 | High | Claude Code 실행 시 보안 |
| 봇 토큰 rotation | Medium | 정기 갱신 자동화 |
| Context DB 백업 | Medium | 일일 자동 백업 |
| 메시지 재전송 로직 | High | Telegram API 실패 시 |
