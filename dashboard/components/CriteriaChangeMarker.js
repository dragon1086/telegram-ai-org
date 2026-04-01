/**
 * CriteriaChangeMarker.js — 기준 변경 마커 컴포넌트
 *
 * 기준 변경 이벤트(criteria_change) 수신 시 대시보드에 마커를 렌더링한다.
 *
 * 표시 내용:
 *   📋 기준 변경: exit_code_143 v0.9.0→v1.0.0 | threshold: 2→3 | 이유: RETRO-27
 *
 * 애니메이션: criteria-marker-flash (3회 flash 후 고정)
 * 자동 제거: 30초 후 페이드아웃
 */

export class CriteriaChangeMarker {
  /**
   * @param {HTMLElement} container
   * @param {{ autoRemoveMs?: number }} [options={}]
   */
  constructor(container, options = {}) {
    this.container    = container;
    this.autoRemoveMs = options.autoRemoveMs ?? 30000;
    /** @type {HTMLElement[]} */
    this._markers     = [];
    this._ensureList();
  }

  /**
   * 기준 변경 마커 렌더링
   * @param {import('../api/types').CriteriaChangeEvent} criteriaChangeEvent
   */
  show(criteriaChangeEvent) {
    const el = this._createMarkerEl(criteriaChangeEvent);
    const list = this.container.querySelector('.criteria-marker-list');
    if (list) {
      list.insertBefore(el, list.firstChild);
      this._markers.unshift(el);
      this._scheduleAutoRemove(el, this.autoRemoveMs);
    }
  }

  /** 최상단 마커 숨김 */
  hide() {
    const el = this._markers[0];
    if (el) this._fadeAndRemove(el);
  }

  /** 전체 마커 제거 */
  clear() {
    this._markers.forEach((el) => el.remove());
    this._markers = [];
  }

  /**
   * 마커 DOM 요소 생성
   * @param {import('../api/types').CriteriaChangeEvent} event
   * @returns {HTMLElement}
   */
  _createMarkerEl(event) {
    const el = document.createElement('div');
    el.className = 'criteria-change-marker criteria-marker';
    el.setAttribute('role', 'alert');
    el.innerHTML = this._formatMarkerText(event);
    return el;
  }

  /**
   * 마커 텍스트 포맷: "📋 기준 변경: {name} v{old}→v{new} | threshold: {old_val}→{new_val} | 이유: {reason}"
   * @param {import('../api/types').CriteriaChangeEvent} event
   * @returns {string}
   */
  _formatMarkerText(event) {
    const reasonPart = event.change_reason
      ? ` &nbsp;|&nbsp; 이유: <span style="color:var(--comic-blue);">${event.change_reason}</span>`
      : '';
    return `
      <span style="font-size:1.1rem;">📋</span>
      <span>
        <strong>기준 변경:</strong>
        <code style="background:rgba(0,0,0,.08);padding:.1rem .3rem;border-radius:3px;">${event.threshold_name}</code>
        &nbsp;v${event.old_version}→v${event.new_version}
        &nbsp;|&nbsp; threshold: <strong>${event.old_value}→${event.new_value}</strong>
        ${reasonPart}
      </span>
      <span style="margin-left:auto;font-size:.72rem;color:#666;">${this._formatTime(event.changed_at)}</span>
    `;
  }

  /**
   * 자동 제거 타이머 설정
   * @param {HTMLElement} el
   * @param {number} ms
   */
  _scheduleAutoRemove(el, ms) {
    setTimeout(() => {
      this._fadeAndRemove(el);
    }, ms);
  }

  /**
   * 페이드아웃 후 DOM 제거
   * @param {HTMLElement} el
   */
  _fadeAndRemove(el) {
    el.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
    el.style.opacity    = '0';
    el.style.transform  = 'translateY(-8px)';
    setTimeout(() => {
      el.remove();
      this._markers = this._markers.filter((m) => m !== el);
    }, 650);
  }

  /**
   * 시각 포맷
   * @param {number} ts
   * @returns {string}
   */
  _formatTime(ts) {
    const d = new Date(ts);
    if (isNaN(d.getTime())) return '--:--:--';
    return d.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
  }

  /** 마커 목록 컨테이너 초기화 */
  _ensureList() {
    if (!this.container.querySelector('.criteria-marker-list')) {
      const list = document.createElement('div');
      list.className = 'criteria-marker-list';
      list.style.cssText = 'display:flex;flex-direction:column;gap:.5rem;';
      this.container.appendChild(list);
    }
  }

  /** 현재 마커 개수 */
  get markerCount() {
    return this._markers.length;
  }
}
