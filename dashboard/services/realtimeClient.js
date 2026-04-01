/**
 * realtimeClient.js — WebSocket/SSE 실시간 클라이언트
 *
 * 이벤트 타입:
 *   - ticket_update       : 티켓 카운터 변경
 *   - task_complete       : 작업 완료
 *   - remote_access_change: 원격 접근 상태 변경
 *
 * 기능:
 *   - 자동 재연결 (exponential backoff, 최대 30초)
 *   - 이벤트 핸들러 등록/해제
 *   - SSE(기본) / WebSocket 모드 전환
 */

const DEFAULT_OPTIONS = {
  mode: 'sse',           // 'sse' | 'websocket'
  sseUrl: '/api/v1/events/stream',
  wsUrl: null,           // ws:// or wss:// URL (mode='websocket' 시 필수)
  reconnect: true,
  initialDelay: 1000,    // 첫 재연결 대기 (ms)
  maxDelay: 30000,       // 최대 재연결 대기 (ms)
  backoffFactor: 2.0,    // 지수 backoff 계수
  maxRetries: Infinity,  // 최대 재시도 횟수 (Infinity = 무제한)
};

export class RealtimeClient {
  constructor(options = {}) {
    this.options   = { ...DEFAULT_OPTIONS, ...options };
    this._handlers = {};     // eventType → [handler, ...]
    this._source   = null;   // EventSource | WebSocket
    this._retries  = 0;
    this._delay    = this.options.initialDelay;
    this._stopped  = false;
    this._retryTimer = null;
  }

  // ── 공개 API ──────────────────────────────────────────────

  /** 이벤트 핸들러 등록 */
  on(eventType, handler) {
    if (!this._handlers[eventType]) this._handlers[eventType] = [];
    this._handlers[eventType].push(handler);
    return this;
  }

  /** 이벤트 핸들러 해제 */
  off(eventType, handler) {
    if (!this._handlers[eventType]) return this;
    this._handlers[eventType] = this._handlers[eventType].filter((h) => h !== handler);
    return this;
  }

  /** 연결 시작 */
  connect() {
    this._stopped = false;
    this._connectInternal();
    return this;
  }

  /** 연결 종료 (재연결 중단) */
  disconnect() {
    this._stopped = true;
    clearTimeout(this._retryTimer);
    this._closeSource();
  }

  /** 현재 연결 상태 */
  get state() {
    if (this._stopped) return 'stopped';
    if (!this._source)  return 'disconnected';
    if (this.options.mode === 'sse') {
      return this._source.readyState === EventSource.OPEN ? 'connected' : 'connecting';
    }
    const WS_STATES = { 0: 'connecting', 1: 'connected', 2: 'closing', 3: 'disconnected' };
    return WS_STATES[this._source.readyState] || 'unknown';
  }

  // ── 내부 구현 ─────────────────────────────────────────────

  _connectInternal() {
    if (this._stopped) return;
    this._closeSource();
    this._emit('_status', { state: 'connecting', retries: this._retries });

    try {
      if (this.options.mode === 'sse') {
        this._connectSSE();
      } else {
        this._connectWS();
      }
    } catch (err) {
      console.error('[RealtimeClient] 연결 오류:', err);
      this._scheduleReconnect();
    }
  }

  _connectSSE() {
    const source = new EventSource(this.options.sseUrl);
    this._source = source;

    source.onopen = () => {
      console.log('[RealtimeClient] SSE 연결됨');
      this._retries = 0;
      this._delay   = this.options.initialDelay;
      this._emit('_status', { state: 'connected', retries: 0 });
    };

    source.onerror = (e) => {
      console.warn('[RealtimeClient] SSE 오류/닫힘', e);
      this._emit('_status', { state: 'disconnected' });
      this._closeSource();
      this._scheduleReconnect();
    };

    // 이벤트 타입별 리스너 등록
    ['ticket_update', 'task_complete', 'remote_access_change', 'ping'].forEach((type) => {
      source.addEventListener(type, (e) => {
        try {
          const data = JSON.parse(e.data);
          this._emit(type, data);
        } catch {
          this._emit(type, e.data);
        }
      });
    });

    // 기본 메시지 (타입 없는 이벤트)
    source.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.type) this._emit(data.type, data);
        else this._emit('message', data);
      } catch {
        this._emit('message', e.data);
      }
    };
  }

  _connectWS() {
    if (!this.options.wsUrl) throw new Error('wsUrl 옵션이 필요합니다');

    const ws = new WebSocket(this.options.wsUrl);
    this._source = ws;

    ws.onopen = () => {
      console.log('[RealtimeClient] WebSocket 연결됨');
      this._retries = 0;
      this._delay   = this.options.initialDelay;
      this._emit('_status', { state: 'connected', retries: 0 });
    };

    ws.onclose = (e) => {
      console.warn('[RealtimeClient] WebSocket 닫힘', e.code, e.reason);
      this._emit('_status', { state: 'disconnected' });
      this._scheduleReconnect();
    };

    ws.onerror = (e) => {
      console.error('[RealtimeClient] WebSocket 오류', e);
    };

    ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        const type = data.type || 'message';
        this._emit(type, data);
      } catch {
        this._emit('message', e.data);
      }
    };
  }

  _scheduleReconnect() {
    if (this._stopped) return;
    if (!this.options.reconnect) return;
    if (this._retries >= this.options.maxRetries) {
      console.error('[RealtimeClient] 최대 재시도 초과');
      this._emit('_status', { state: 'failed' });
      return;
    }

    this._retries++;
    const jitter  = Math.random() * 1000;
    const wait    = Math.min(this._delay + jitter, this.options.maxDelay);
    this._delay   = Math.min(this._delay * this.options.backoffFactor, this.options.maxDelay);

    console.log(`[RealtimeClient] ${Math.round(wait)}ms 후 재연결 시도 (${this._retries}회차)`);
    this._emit('_status', { state: 'reconnecting', retries: this._retries, nextDelay: Math.round(wait) });

    this._retryTimer = setTimeout(() => this._connectInternal(), wait);
  }

  _closeSource() {
    if (!this._source) return;
    try {
      if (this.options.mode === 'sse') {
        this._source.close();
      } else if (this._source.readyState !== WebSocket.CLOSED) {
        this._source.close(1000, 'client disconnect');
      }
    } catch { /* ignore */ }
    this._source = null;
  }

  _emit(eventType, data) {
    const handlers = this._handlers[eventType] || [];
    handlers.forEach((h) => {
      try { h(data); } catch (err) { console.error('[RealtimeClient] 핸들러 오류:', err); }
    });
  }
}
