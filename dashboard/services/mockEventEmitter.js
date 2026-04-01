/**
 * mockEventEmitter.js — 개발용 목 이벤트 에미터
 *
 * 실제 서버 없이 realtimeClient와 동일한 인터페이스로 동작.
 * DEV_MODE=true 또는 URL 파라미터 ?mock=1 시 자동 활성화.
 *
 * 이벤트:
 *   - ticket_update       : 2~5초마다 랜덤 카운터 변경
 *   - task_complete       : 4~8초마다 새 완료 태스크 생성
 *   - remote_access_change: 10~20초마다 연결 상태 변경
 */

const ORG_IDS = ['dev', 'design', 'product', 'ops', 'growth', 'research', 'pm'];

const SAMPLE_TASKS = [
  '마케팅 자동화 파이프라인 구현',
  'REST API 인증 모듈 완성',
  'Telegram 봇 E2E 테스트 통과',
  'CI/CD GitHub Actions 배포',
  '대시보드 UI 컴포넌트 개발',
  'DB 마이그레이션 스크립트 작성',
  '코드 리뷰 및 PR 머지',
  '사용자 온보딩 플로우 개선',
  '버그 수정: 타임아웃 이슈',
  '성능 최적화 — 쿼리 인덱싱',
  'ngrok 터널 헬스체크 자동화',
  'Gemini CLI 연동 완료',
  '보안 취약점 패치',
  'Docker 이미지 경량화',
];

function _rand(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

function _choice(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

export class MockEventEmitter {
  constructor() {
    this._handlers  = {};
    this._timers    = [];
    this._ticketState = { in_progress: 3, pending: 7, done: 12 };
    this._running   = false;
  }

  // ── realtimeClient 동일 인터페이스 ───────────────────────

  on(eventType, handler) {
    if (!this._handlers[eventType]) this._handlers[eventType] = [];
    this._handlers[eventType].push(handler);
    return this;
  }

  off(eventType, handler) {
    if (!this._handlers[eventType]) return this;
    this._handlers[eventType] = this._handlers[eventType].filter((h) => h !== handler);
    return this;
  }

  connect() {
    this._running = true;
    console.log('[MockEventEmitter] 개발 모드 활성화 — 목 이벤트 시작');

    // 즉시 초기 상태 전송
    setTimeout(() => {
      this._emit('_status', { state: 'connected', retries: 0 });
      this._emit('ticket_update', { ...this._ticketState });
      this._emit('remote_access_change', {
        status: 'connected',
        url: 'https://mock-abc123.ngrok.io',
        tunnel_provider: 'ngrok (mock)',
        latency_ms: 42,
        last_connected: new Date().toISOString(),
      });
    }, 500);

    this._scheduleTicketUpdates();
    this._scheduleTaskCompletes();
    this._scheduleRemoteAccessChanges();
    return this;
  }

  disconnect() {
    this._running = false;
    this._timers.forEach(clearTimeout);
    this._timers = [];
    console.log('[MockEventEmitter] 목 이벤트 중단');
  }

  get state() {
    return this._running ? 'connected' : 'stopped';
  }

  // ── 내부 스케줄러 ─────────────────────────────────────────

  _scheduleTicketUpdates() {
    const next = () => {
      if (!this._running) return;
      this._updateTickets();
      const delay = _rand(2000, 5000);
      this._timers.push(setTimeout(next, delay));
    };
    this._timers.push(setTimeout(next, _rand(2000, 4000)));
  }

  _scheduleTaskCompletes() {
    const next = () => {
      if (!this._running) return;
      this._emitTaskComplete();
      const delay = _rand(4000, 8000);
      this._timers.push(setTimeout(next, delay));
    };
    this._timers.push(setTimeout(next, _rand(1000, 3000)));
  }

  _scheduleRemoteAccessChanges() {
    const states = ['connected', 'connecting', 'connected', 'connected', 'disconnected', 'connecting', 'connected'];
    let idx = 0;
    const next = () => {
      if (!this._running) return;
      const status = states[idx % states.length];
      idx++;
      this._emit('remote_access_change', {
        status,
        url: status === 'connected' ? `https://mock-${Math.random().toString(36).slice(2, 8)}.ngrok.io` : null,
        tunnel_provider: 'ngrok (mock)',
        latency_ms: status === 'connected' ? _rand(15, 120) : null,
        last_connected: status === 'connected' ? new Date().toISOString() : null,
      });
      this._timers.push(setTimeout(next, _rand(10000, 20000)));
    };
    this._timers.push(setTimeout(next, _rand(10000, 15000)));
  }

  _updateTickets() {
    // 랜덤으로 in_progress/pending/done 중 하나 변경
    const keys = ['in_progress', 'pending', 'done'];
    const key  = _choice(keys);
    const delta = _rand(-2, 3);
    this._ticketState[key] = Math.max(0, this._ticketState[key] + delta);

    this._emit('ticket_update', { ...this._ticketState });
  }

  _emitTaskComplete() {
    const orgId = _choice(ORG_IDS);
    this._emit('task_complete', {
      id: `T-mock-${Date.now()}`,
      title: _choice(SAMPLE_TASKS),
      org_id: orgId,
      completed_at: new Date().toISOString(),
      result: '완료',
    });
  }

  _emit(eventType, data) {
    const handlers = this._handlers[eventType] || [];
    handlers.forEach((h) => {
      try { h(data); } catch (err) { console.error('[MockEventEmitter] 핸들러 오류:', err); }
    });
  }
}

/** URL 파라미터 또는 환경 기반 목 모드 감지 */
export function isMockMode() {
  if (typeof window === 'undefined') return false;
  const params = new URLSearchParams(window.location.search);
  if (params.get('mock') === '1') return true;
  if (window.DEV_MODE === true)    return true;
  if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
    // 로컬호스트에서는 기본 목 모드 활성화 (명시적 ?mock=0 으로 비활성화 가능)
    return params.get('mock') !== '0';
  }
  return false;
}
