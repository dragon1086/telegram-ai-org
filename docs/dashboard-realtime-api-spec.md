# 실시간 대시보드 API 스펙 (Phase 1 & 2)

**버전**: 2.0.0
**작성일**: 2026-04-01
**기술 선택**: SSE (Server-Sent Events)

---

## 기술 선택 근거

### SSE vs WebSocket 비교

| 기준 | SSE | WebSocket |
|------|-----|-----------|
| 방향성 | 단방향 (서버→클라이언트) | 양방향 |
| 프로토콜 | HTTP/1.1 기반 | 별도 프로토콜 업그레이드 |
| 자동 재연결 | 브라우저 기본 지원 | 수동 구현 필요 |
| 구현 복잡도 | 낮음 | 높음 |
| nginx 호환성 | X-Accel-Buffering 비활성화로 해결 | 별도 설정 불필요 |
| Last-Event-ID | 표준 지원 | 수동 구현 필요 |

**결론**: 티켓 상태 스트리밍은 단방향 서버 푸시이므로 SSE가 최적. WebSocket의 양방향 기능은 현재 요구사항에 불필요한 오버헤드.

---

## 엔드포인트 스펙

### 기존 통합 스트림 (Phase 1, 하위 호환 유지)

```
GET /api/v1/events/stream
```

모든 이벤트 타입 혼합 발행. 기존 클라이언트 하위 호환용.

### Phase 2 채널별 전용 스트림

#### (a) 티켓 처리 현황 스트림

```
GET /api/v1/stream/tickets
```

- **이벤트 타입**: `ticket_update`
- **인증**: 불필요
- **초기 이벤트**: 연결 즉시 현재 카운트 스냅샷 발송
- **Last-Event-ID**: 지원 (재연결 시 클라이언트 전달)

**페이로드 스키마:**
```json
{
  "type": "ticket_update",
  "pending": 5,
  "in_progress": 3,
  "done": 42,
  "blocked": 1,
  "aggregations": {
    "1h":  { "period_hours": 1, "completed": 5, "throughput": 5.0, "avg_duration_seconds": 120.5, "window_start": 1711900000.0, "window_end": 1711903600.0 },
    "6h":  { "period_hours": 6, "completed": 18, "throughput": 3.0, "avg_duration_seconds": 95.2, "window_start": 1711882000.0, "window_end": 1711903600.0 },
    "24h": { "period_hours": 24, "completed": 65, "throughput": 2.7, "avg_duration_seconds": 110.0, "window_start": 1711817200.0, "window_end": 1711903600.0 }
  },
  "ts": 1711903645.123
}
```

#### (b) 완료 작업 스트림

```
GET /api/v1/stream/completed-tasks
```

- **이벤트 타입**: `task_complete`
- **인증**: 불필요
- **초기 이벤트**: 연결 즉시 최근 완료 작업 최대 20건 초기 발송

**페이로드 스키마:**
```json
{
  "type": "task_complete",
  "ticket_id": "T-aiorg_pm_bot-1059",
  "state": "done",
  "assignee": "aiorg_engineering_bot",
  "created_at": 1711900000.0,
  "started_at": 1711900100.0,
  "completed_at": 1711903600.0,
  "title": "Phase 2 대시보드 구현",
  "org_id": "aiorg_engineering_bot",
  "color": "#00C851",
  "emoji": "✅",
  "ts": 1711903645.123,
  "note": "initial_batch"
}
```

> `note: "initial_batch"` 필드는 초기 발송 배치 항목에만 포함됩니다.

#### (c) 원격 접근 현황 스트림

```
GET /api/v1/stream/remote-access
```

- **이벤트 타입**: `remote_access_change`
- **인증**: 불필요
- **초기 이벤트**: 연결 즉시 현재 접속 현황 발송
- **트리거**: 클라이언트 연결/해제 시 자동 발행

**페이로드 스키마:**
```json
{
  "type": "remote_access_change",
  "client_count": 5,
  "channel_stats": {
    "tickets": 2,
    "completed-tasks": 1,
    "remote-access": 1,
    "all": 1
  },
  "ts": 1711903645.123,
  "note": "initial_snapshot"
}
```

> `note: "initial_snapshot"` 필드는 초기 연결 이벤트에만 포함됩니다.

---

## 공통 이벤트 스키마

### ping (연결 유지)

30초 간격 또는 연결 초기 발송.

```json
{
  "type": "ping",
  "ts": 1711903645.123,
  "message": "connected",
  "channel": "tickets",
  "last_id": "1711903600000"
}
```

> `message`, `channel`, `last_id` 필드는 초기 연결 ping에만 포함됩니다.

---

## SSE 포맷

```
id: {event_id}
event: {event_type}
data: {json_payload}

```

**예시:**
```
id: 1711903645123
event: ticket_update
data: {"pending": 5, "in_progress": 3, "done": 42, "blocked": 1, "ts": 1711903645.123}

```

---

## 재연결 지원 (Last-Event-ID)

클라이언트는 연결 끊김 후 재연결 시 `Last-Event-ID` 헤더를 전달합니다.

```http
GET /api/v1/stream/tickets
Last-Event-ID: 1711903600000
```

서버는 이 헤더를 수신하면:
1. 로그에 재연결 기록
2. 초기 ping 이벤트에 `last_id` 필드 포함

> 현재 구현은 Last-Event-ID 기반 이벤트 리플레이를 지원하지 않습니다. 재연결 시 현재 스냅샷만 발송됩니다.

---

## 인증

```
ENABLE_API_AUTH=false  → 모든 스트림 엔드포인트 인증 불필요
ENABLE_API_AUTH=true   → 스트림 엔드포인트는 여전히 인증 불필요 (대시보드 공개 접근 정책)
```

스트림 엔드포인트는 대시보드 실시간 시각화를 위해 인증 없이 공개 접근을 허용합니다.
X-API-Key 인증이 필요한 CRUD 엔드포인트(`/api/v1/tasks`)와 분리됩니다.

---

## 연결 관리 구조

```
ConnectionManager (core/dashboard/connection_manager.py)
│
├── channels["tickets"]         → [Queue, Queue, ...]   # ticket_update 구독자
├── channels["completed-tasks"] → [Queue, Queue, ...]   # task_complete 구독자
├── channels["remote-access"]   → [Queue, Queue, ...]   # remote_access_change 구독자
└── channels["all"]             → [Queue, Queue, ...]   # 전체 이벤트 구독자 (하위 호환)

DashboardPusher (core/dashboard/pusher.py)
│ (폴링 5초 간격)
├── publish("tickets", "ticket_update", {...})
├── publish("completed-tasks", "task_complete", {...})
└── publish("remote-access", "remote_access_change", {...})
```

---

## 아키텍처 다이어그램

```
[DataSourceAdapter] --poll--> [DashboardPusher]
                                     │
                    ┌────────────────┼──────────────────────┐
                    ▼                ▼                       ▼
            publish("tickets") publish("completed-tasks") publish("remote-access")
                    │                │                       │
            [ConnectionManager]────────────────────────────────
                    │
        ┌───────────┼────────────────┐
        ▼           ▼                ▼
  /stream/tickets  /stream/         /stream/
                completed-tasks   remote-access
        │           │                │
    SSE clients  SSE clients     SSE clients
```

---

## 변경 이력

| 버전 | 날짜 | 변경 내용 |
|------|------|----------|
| 1.0.0 | 2026-04-01 | Phase 1 — 단일 통합 SSE 스트림 (`/api/v1/events/stream`) |
| 2.0.0 | 2026-04-01 | Phase 2 — 채널별 전용 스트림 3종 + ConnectionManager 추가 |
