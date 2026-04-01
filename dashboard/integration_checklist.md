# 대시보드 통합 동작 확인 체크리스트

**작성일**: 2026-03-31
**Phase**: 2 — WebSocket/SSE 실시간 업데이트 연동 및 통합 검증

---

## Phase 1 — 기반 구조 검증

- [ ] `dashboard/index.html` 브라우저에서 정상 렌더링 (오류 없음)
- [ ] 만화 테마 CSS 적용 확인 (말풍선 카드, 두꺼운 테두리, Bangers 폰트)
- [ ] TicketStatusPanel: 진행중/대기/완료 카운터 표시
- [ ] CompletedTasksPanel: 빈 목록 상태 플레이스홀더 표시
- [ ] RemoteAccessPanel: 초기 'disconnected' 상태 표시
- [ ] 반응형 레이아웃 — 모바일(768px 이하) 확인

## Phase 2 — 실시간 연동 검증 (Mock 모드)

### 2-1. 목 모드 활성화
- [ ] `http://localhost/dashboard/index.html?mock=1` 접속 시 노란 배너 표시
- [ ] 로컬호스트 자동 mock 모드 활성화 확인
- [ ] 헤더 "실시간 연결됨" 배지 표시 (약 0.5초 후)

### 2-2. ticket_update 이벤트
- [ ] 2~5초 간격으로 카운터 숫자 변경 확인
- [ ] 변경된 카운터 노란 플래시 애니메이션 동작 확인
- [ ] 카운터 음수 미발생 확인

### 2-3. task_complete 이벤트
- [ ] 4~8초 간격으로 완료 작업 목록 상단에 새 항목 추가
- [ ] slideInRight 애니메이션 동작 확인
- [ ] WOW!/POW!/ZAP! 팝업 이펙트 표시 확인
- [ ] 조직 이모지(🔧🎨📋⚙️📈🔬🎯) 정상 표시
- [ ] 50건 초과 시 가장 오래된 항목 자동 제거

### 2-4. remote_access_change 이벤트
- [ ] 10~20초 간격으로 연결 상태 변경 (connected/connecting/disconnected)
- [ ] 상태별 아이콘/색상 변경 확인 (🟢/🟡/🔴)
- [ ] CONNECTING 상태 blink 애니메이션 동작
- [ ] URL 업데이트 확인 (connected: ngrok URL, disconnected: '터널 비활성')
- [ ] 응답 지연(latency_ms) 표시 확인

### 2-5. 연결 끊김 / 재연결 (실서버 모드)
- [ ] SSE 연결 끊김 시 헤더 배지 "연결 끊김" 표시
- [ ] Exponential backoff 재연결 시도 콘솔 로그 확인
  - 1차: ~1초 후, 2차: ~2초, 3차: ~4초, ... 최대 30초
- [ ] 재연결 성공 시 "실시간 연결됨" 복귀

### 2-6. 실시간 시계
- [ ] 매 1초 갱신 확인
- [ ] 한국어 시간 포맷 (HH:MM:SS)

## Phase 3 — 백엔드 SSE 엔드포인트 (선택)

- [ ] `GET /api/v1/events/stream` Content-Type: text/event-stream 응답
- [ ] `ticket_update` 이벤트 JSON 전송 테스트
- [ ] `task_complete` 이벤트 JSON 전송 테스트
- [ ] `remote_access_change` 이벤트 JSON 전송 테스트
- [ ] 연결 유지 (30초+ 지속) 확인

---

## 테스트 실행 방법

```bash
# 방법 1: Python 간이 서버 (개발용)
cd /Users/rocky/telegram-ai-org
python3 -m http.server 3000 --directory dashboard

# 방법 2: FastAPI 서버 통합 (실서버)
ENABLE_REST_API=true uvicorn core.api.app:create_app --factory --port 8000

# 목 모드 접속
open http://localhost:3000/?mock=1
```
