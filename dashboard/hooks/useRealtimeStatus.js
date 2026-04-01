/**
 * useRealtimeStatus.js — 실시간 상태 훅 (React 없이 vanilla JS 옵저버 패턴)
 *
 * SSE 또는 폴링(3초)으로 백엔드에 연결하고, 수신 데이터를 구독자에게 전달한다.
 *
 * 사용 예:
 *   const hook = new RealtimeStatusHook({ mode: 'sse' });
 *   hook.on('ticket_update', (data) => console.log(data));
 *   hook.on('criteria_change', (data) => console.log('기준 변경!', data));
 *   hook.start();
 */

import { RealtimeClient } from '../services/realtimeClient.js';

/** SSE 이벤트 타입 (기존 RealtimeClient에 등록된 타입 + 확장) */
const SSE_EVENT_TYPES = [
  'ticket_update',
  'task_complete',
  'remote_access_change',
  'criteria_change',
  'character_update',
  'ping',
  'message',
];

export class RealtimeStatusHook {
  /**
   * @param {{ mode?: 'sse'|'polling', pollInterval?: number, sseUrl?: string, apiClient?: any }} [options={}]
   */
  constructor(options = {}) {
    this._mode         = options.mode ?? 'sse';
    this._pollInterval = options.pollInterval ?? 3000;
    this._sseUrl       = options.sseUrl ?? '/api/v1/events/stream';
    this._apiClient    = options.apiClient ?? null;

    /** @type {Record<string, Function[]>} */
    this._handlers     = {};
    /** @type {RealtimeClient | null} */
    this._sseClient    = null;
    /** @type {number | null} */
    this._pollTimer    = null;
    /** @type {'connected'|'disconnected'|'connecting'|'polling'} */
    this._connState    = 'disconnected';
    /** @type {any | null} previous snapshot for diff comparison */
    this._prevSnapshot = null;
    /** @type {Record<string, number>} threshold block_threshold 캐시 (기준 변경 감지용) */
    this._thresholdCache = {};
  }

  /**
   * 이벤트 핸들러 등록
   * @param {string} eventType
   * @param {Function} handler
   * @returns {this}
   */
  on(eventType, handler) {
    if (!this._handlers[eventType]) this._handlers[eventType] = [];
    this._handlers[eventType].push(handler);
    return this;
  }

  /**
   * 이벤트 핸들러 해제
   * @param {string} eventType
   * @param {Function} handler
   * @returns {this}
   */
  off(eventType, handler) {
    if (!this._handlers[eventType]) return this;
    this._handlers[eventType] = this._handlers[eventType].filter((h) => h !== handler);
    return this;
  }

  /** 연결 시작 */
  start() {
    if (this._mode === 'sse') {
      this._startSSE();
    } else {
      this._startPolling();
    }
  }

  /** 연결 중단 */
  stop() {
    if (this._sseClient) {
      this._sseClient.disconnect();
      this._sseClient = null;
    }
    if (this._pollTimer != null) {
      clearInterval(this._pollTimer);
      this._pollTimer = null;
    }
    this._connState = 'disconnected';
  }

  /**
   * 현재 연결 상태
   * @returns {'connected'|'disconnected'|'connecting'|'polling'}
   */
  get connectionState() {
    return this._connState;
  }

  // ── 내부 구현 ───────────────────────────────────────────────

  /** SSE 연결 시작 (RealtimeClient 활용) */
  _startSSE() {
    this._connState = 'connecting';

    this._sseClient = new RealtimeClient({
      mode:   'sse',
      sseUrl: this._sseUrl,
    });

    // 상태 이벤트
    this._sseClient.on('_status', (status) => {
      if (status.state === 'connected')    this._connState = 'connected';
      if (status.state === 'disconnected') this._connState = 'disconnected';
      if (status.state === 'reconnecting') this._connState = 'connecting';
      this._emit('_connection', { state: this._connState });
    });

    // 각 이벤트 타입 구독
    SSE_EVENT_TYPES.forEach((type) => {
      this._sseClient.on(type, (data) => {
        this._processEvent(type, data);
      });
    });

    this._sseClient.connect();
  }

  /** 폴링 시작 (3초 인터벌 fetch + diff 비교) */
  _startPolling() {
    if (!this._apiClient) {
      console.warn('[RealtimeStatusHook] 폴링 모드에는 apiClient 옵션이 필요합니다.');
      return;
    }

    this._connState = 'polling';
    this._emit('_connection', { state: 'polling' });

    const poll = async () => {
      try {
        const snapshot = await this._apiClient.getDashboardSnapshot();
        this._detectCriteriaChange(snapshot);

        // ticket_update diff
        if (this._prevSnapshot) {
          const prev = this._prevSnapshot;
          const curr = snapshot;
          const prevCounts = prev.counts || {};
          const currCounts = curr.counts || {};

          const changed = ['pending', 'in_progress', 'done', 'blocked'].some(
            (k) => prevCounts[k] !== currCounts[k],
          );
          if (changed) this._processEvent('ticket_update', currCounts);

          // recent_completed diff — 새 완료 태스크 감지
          const prevDone = new Set((prev.recent_completed || []).map((t) => t.ticket_id));
          (curr.recent_completed || []).forEach((task) => {
            if (!prevDone.has(task.ticket_id)) {
              this._processEvent('task_complete', task);
            }
          });
        } else {
          // 첫 번째 폴링 — 현재 상태 발행
          if (snapshot.counts) this._processEvent('ticket_update', snapshot.counts);
        }

        this._prevSnapshot = snapshot;
      } catch (err) {
        console.warn('[RealtimeStatusHook] 폴링 오류:', err);
        this._emit('_connection', { state: 'disconnected', error: err.message });
      }
    };

    // 즉시 한 번 실행
    poll();
    this._pollTimer = setInterval(poll, this._pollInterval);
  }

  /**
   * 이벤트 처리 + criteria_change 감지
   * @param {string} type
   * @param {any} data
   */
  _processEvent(type, data) {
    // SSE를 통해 직접 기준 변경 이벤트가 들어오는 경우
    if (type === 'criteria_change' || (data && data.type === 'criteria_change')) {
      this._emit('criteria_change', data);
      return;
    }

    this._emit(type, data);
  }

  /**
   * 스냅샷 비교를 통해 block_threshold 변경 감지 → 'criteria_change' 이벤트 발행
   * @param {{ thresholds?: Record<string, import('../api/types').ThresholdConfig>, criteria_version?: string }} newData
   */
  _detectCriteriaChange(newData) {
    if (!newData || !newData.thresholds) return;

    Object.entries(newData.thresholds).forEach(([name, config]) => {
      const prevBlock = this._thresholdCache[name];
      const newBlock  = config.block_threshold;

      if (prevBlock != null && prevBlock !== newBlock) {
        const event = {
          type:           'criteria_change',
          threshold_name: name,
          old_version:    this._prevSnapshot?.criteria_version || '?',
          new_version:    newData.criteria_version || '?',
          old_value:      prevBlock,
          new_value:      newBlock,
          changed_at:     Date.now(),
        };
        this._emit('criteria_change', event);
      }

      this._thresholdCache[name] = newBlock;
    });
  }

  /**
   * 이벤트 발행
   * @param {string} type
   * @param {any} data
   */
  _emit(type, data) {
    const handlers = this._handlers[type] || [];
    handlers.forEach((h) => {
      try { h(data); }
      catch (err) { console.error(`[RealtimeStatusHook] 핸들러 오류 (${type}):`, err); }
    });
  }
}
