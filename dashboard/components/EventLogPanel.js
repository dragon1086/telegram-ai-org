/**
 * EventLogPanel.js — 이벤트 로그 패널
 *
 * 기능:
 *  - 최근 이벤트 50건 (FIFO)
 *  - 이벤트 타입별 아이콘/색상 매핑
 *  - 기준 변경 이벤트 특별 강조 렌더링
 *  - 가상 스크롤 (DOM 최대 50개 유지)
 */

const MAX_EVENTS = 50;

/** 이벤트 타입별 아이콘/색상 */
const EVENT_TYPE_CONFIG = {
  ticket_update:        { icon: '🎫', color: '#0057FF', label: '티켓 업데이트' },
  task_complete:        { icon: '✅', color: '#00C851', label: '태스크 완료'   },
  remote_access_change: { icon: '🔒', color: '#9B00FF', label: '원격 접근 변경' },
  criteria_change:      { icon: '📋', color: '#FF6B00', label: '기준 변경'     },
  character_update:     { icon: '🦾', color: '#FF3B3F', label: '캐릭터 업데이트' },
  ping:                 { icon: '🏓', color: '#aaa',    label: 'Ping'          },
  message:              { icon: '💬', color: '#666',    label: '메시지'         },
};

const DEFAULT_TYPE_CONFIG = { icon: 'ℹ️', color: '#666', label: '이벤트' };

export class EventLogPanel {
  /**
   * @param {HTMLElement} container
   */
  constructor(container) {
    this.container = container;
    /** @type {Array<{type: string, data: any, ts: number}>} */
    this._events   = [];
    this._render();
  }

  /**
   * 이벤트 추가 (FIFO, 최대 MAX_EVENTS)
   * @param {{ type: string, [key: string]: any }} event
   */
  addEvent(event) {
    const entry = { type: event.type || 'message', data: event, ts: event.ts || Date.now() };
    this._events.unshift(entry);
    if (this._events.length > MAX_EVENTS) this._events.pop();

    this._prependEventItem(entry);
    this._pruneDOM();
  }

  /**
   * 기준 변경 이벤트 특별 렌더링
   * @param {import('../api/types').CriteriaChangeEvent} event
   */
  addCriteriaChange(event) {
    const entry = { type: 'criteria_change', data: event, ts: event.changed_at || Date.now() };
    this._events.unshift(entry);
    if (this._events.length > MAX_EVENTS) this._events.pop();

    this._prependCriteriaChangeItem(entry);
    this._pruneDOM();
  }

  /**
   * 이벤트 아이템 DOM 생성
   * @param {{ type: string, data: any, ts: number }} entry
   * @returns {HTMLElement}
   */
  _renderEventItem(entry) {
    const cfg   = EVENT_TYPE_CONFIG[entry.type] || DEFAULT_TYPE_CONFIG;
    const el    = document.createElement('div');
    el.className = 'event-item';
    el.style.borderLeftColor = cfg.color;

    const timeStr = this._formatTime(entry.ts);
    let detail = '';

    if (entry.type === 'ticket_update' && entry.data) {
      const d = entry.data;
      detail = `진행중:${d.in_progress ?? '?'} 대기:${d.pending ?? '?'} 완료:${d.done ?? '?'}`;
    } else if (entry.type === 'task_complete' && entry.data) {
      detail = entry.data.title || entry.data.ticket_id || '';
    } else if (entry.data && typeof entry.data === 'object') {
      const keys = Object.keys(entry.data).filter((k) => k !== 'type').slice(0, 2);
      detail = keys.map((k) => `${k}:${JSON.stringify(entry.data[k])}`).join(' ');
    }

    el.innerHTML = `
      <span style="color:${cfg.color};margin-right:.3rem;">${cfg.icon}</span>
      <span style="font-weight:700;font-size:.75rem;">${cfg.label}</span>
      ${detail ? `<span style="color:#666;font-size:.72rem;margin-left:.4rem;">${detail}</span>` : ''}
      <span style="float:right;font-size:.68rem;color:#999;">${timeStr}</span>
    `;
    return el;
  }

  /**
   * 기준 변경 이벤트 강조 DOM 생성
   * @param {{ type: string, data: import('../api/types').CriteriaChangeEvent, ts: number }} entry
   * @returns {HTMLElement}
   */
  _renderCriteriaChangeItem(entry) {
    const { data } = entry;
    const el = document.createElement('div');
    el.className = 'event-item criteria-change criteria-marker';
    el.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <span style="font-weight:700;">📋 기준 변경: <strong>${data.threshold_name}</strong></span>
        <span style="font-size:.68rem;color:#999;">${this._formatTime(entry.ts)}</span>
      </div>
      <div style="font-size:.75rem;margin-top:.3rem;">
        v${data.old_version} → v${data.new_version} &nbsp;|&nbsp;
        threshold: <strong>${data.old_value} → ${data.new_value}</strong>
        ${data.change_reason ? `&nbsp;|&nbsp; 이유: ${data.change_reason}` : ''}
      </div>
    `;
    return el;
  }

  /**
   * 시각 포맷 (HH:MM:SS)
   * @param {number} ts Unix ms timestamp
   * @returns {string}
   */
  _formatTime(ts) {
    const d = new Date(ts);
    if (isNaN(d.getTime())) return '--:--:--';
    return d.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
  }

  /** 이벤트 아이템 목록 상단에 추가 */
  _prependEventItem(entry) {
    const list = this.container.querySelector('.event-log-list');
    if (!list) return;
    const el = this._renderEventItem(entry);
    list.insertBefore(el, list.firstChild);
  }

  /** 기준 변경 아이템 목록 상단에 추가 */
  _prependCriteriaChangeItem(entry) {
    const list = this.container.querySelector('.event-log-list');
    if (!list) return;
    const el = this._renderCriteriaChangeItem(entry);
    list.insertBefore(el, list.firstChild);
  }

  /** DOM 최대 MAX_EVENTS 개 유지 */
  _pruneDOM() {
    const list = this.container.querySelector('.event-log-list');
    if (!list) return;
    while (list.children.length > MAX_EVENTS) {
      list.removeChild(list.lastChild);
    }
  }

  /** 초기 DOM 구조 */
  _render() {
    this.container.innerHTML = `
      <div class="event-log-panel">
        <div class="comic-card-header" style="margin-bottom:1rem;display:flex;justify-content:space-between;align-items:center;">
          <h2 style="font-family:var(--font-comic-display);font-size:1.3rem;">📡 이벤트 로그</h2>
          <span style="font-size:.72rem;color:#999;">최근 ${MAX_EVENTS}건</span>
        </div>
        <div class="event-log-list"></div>
      </div>
    `;
  }
}
