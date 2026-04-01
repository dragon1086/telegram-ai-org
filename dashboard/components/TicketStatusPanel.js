/**
 * TicketStatusPanel.js — 티켓 처리 현황 패널
 * 진행중 / 대기 / 완료 카운터 표시
 */

export class TicketStatusPanel {
  /**
   * @param {HTMLElement} container - 렌더링할 DOM 요소
   * @param {Object} initialData - 초기 상태 데이터
   */
  constructor(container, initialData = {}) {
    this.container = container;
    this.data = {
      in_progress: 0,
      pending: 0,
      done: 0,
      ...initialData,
    };
    this._render();
  }

  /** 상태 데이터 업데이트 (ticket_update 이벤트 수신 시 호출) */
  update(data) {
    const prev = { ...this.data };
    this.data = { ...this.data, ...data };

    // 변경된 카운터만 플래시 업데이트
    const keys = ['in_progress', 'pending', 'done'];
    keys.forEach((key) => {
      if (prev[key] !== this.data[key]) {
        this._flashCounter(key);
      }
    });

    this._updateCounters();
  }

  _render() {
    this.container.innerHTML = `
      <div class="comic-card" id="ticket-status-card">
        <div class="comic-card-header">
          <h2 class="comic-card-title">📋 티켓 현황</h2>
          <span class="badge" style="background:#fff176; border-color:#a08000;">LIVE</span>
        </div>
        <div class="ticket-counters">
          <div class="ticket-counter in-progress" id="counter-in-progress">
            <span class="count" id="count-in-progress">0</span>
            <div class="label">진행중</div>
          </div>
          <div class="ticket-counter pending" id="counter-pending">
            <span class="count" id="count-pending">0</span>
            <div class="label">대기</div>
          </div>
          <div class="ticket-counter done" id="counter-done">
            <span class="count" id="count-done">0</span>
            <div class="label">완료</div>
          </div>
        </div>
        <div style="margin-top:1rem; text-align:right;">
          <span style="font-size:0.75rem; color:#999;" id="ticket-last-updated">-</span>
        </div>
      </div>
    `;
    this._updateCounters();
  }

  _updateCounters() {
    const el = (id) => this.container.querySelector(id);
    el('#count-in-progress').textContent = this.data.in_progress;
    el('#count-pending').textContent = this.data.pending;
    el('#count-done').textContent = this.data.done;
    el('#ticket-last-updated').textContent = `마지막 업데이트: ${_formatTime(new Date())}`;
  }

  _flashCounter(key) {
    const mapping = { in_progress: 'in-progress', pending: 'pending', done: 'done' };
    const el = this.container.querySelector(`#counter-${mapping[key]}`);
    if (!el) return;
    el.classList.remove('flash-update');
    void el.offsetWidth; // reflow 트리거
    el.classList.add('flash-update');
    setTimeout(() => el.classList.remove('flash-update'), 700);
  }
}

function _formatTime(date) {
  return date.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}
