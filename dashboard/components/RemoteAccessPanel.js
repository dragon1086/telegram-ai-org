/**
 * RemoteAccessPanel.js — 원격 접근 지원 패널
 * 연결 상태 표시 (connected / disconnected / connecting)
 */

export class RemoteAccessPanel {
  /**
   * @param {HTMLElement} container
   * @param {Object} initialData
   */
  constructor(container, initialData = {}) {
    this.container = container;
    this.data = {
      status: 'disconnected',
      url: null,
      tunnel_provider: 'ngrok',
      latency_ms: null,
      last_connected: null,
      ...initialData,
    };
    this._render();
  }

  /** remote_access_change 이벤트 수신 시 호출 */
  update(data) {
    this.data = { ...this.data, ...data };
    this._updateStatus();
  }

  _render() {
    this.container.innerHTML = `
      <div class="comic-card" id="remote-access-card">
        <div class="comic-card-header">
          <h2 class="comic-card-title">🌐 원격 접근</h2>
          <span class="badge" id="remote-provider-badge" style="background:#e0e7ff;">ngrok</span>
        </div>

        <div class="remote-status-main" id="remote-status-main">
          <div class="remote-status-icon" id="remote-icon">📡</div>
          <div>
            <div class="remote-status-label" id="remote-status-label">연결 확인중...</div>
            <div class="remote-url" id="remote-url">-</div>
          </div>
        </div>

        <div class="remote-details">
          <div class="remote-detail-item">
            <div class="detail-label">터널 제공자</div>
            <div class="detail-value" id="detail-provider">-</div>
          </div>
          <div class="remote-detail-item">
            <div class="detail-label">응답 지연</div>
            <div class="detail-value" id="detail-latency">-</div>
          </div>
          <div class="remote-detail-item">
            <div class="detail-label">마지막 연결</div>
            <div class="detail-value" id="detail-last-connected">-</div>
          </div>
          <div class="remote-detail-item">
            <div class="detail-label">상태</div>
            <div class="detail-value" id="detail-status">-</div>
          </div>
        </div>
      </div>
    `;
    this._updateStatus();
  }

  _updateStatus() {
    const { status, url, tunnel_provider, latency_ms, last_connected } = this.data;

    const iconEl    = this.container.querySelector('#remote-icon');
    const labelEl   = this.container.querySelector('#remote-status-label');
    const urlEl     = this.container.querySelector('#remote-url');
    const mainEl    = this.container.querySelector('#remote-status-main');

    const config = {
      connected:    { icon: '🟢', label: 'CONNECTED',    iconClass: 'connected',    labelClass: 'connected' },
      disconnected: { icon: '🔴', label: 'DISCONNECTED', iconClass: 'disconnected', labelClass: 'disconnected' },
      connecting:   { icon: '🟡', label: 'CONNECTING…',  iconClass: 'connecting',   labelClass: 'connecting' },
    };

    const cfg = config[status] || config['disconnected'];

    iconEl.textContent = cfg.icon;
    iconEl.className = `remote-status-icon ${cfg.iconClass}`;
    labelEl.textContent = cfg.label;
    labelEl.className = `remote-status-label ${cfg.labelClass}`;

    if (status === 'connecting') {
      labelEl.classList.add('blink');
    } else {
      labelEl.classList.remove('blink');
    }

    urlEl.textContent = url
      ? url
      : status === 'disconnected' ? '터널 비활성' : '주소 할당 중...';

    // 플래시 애니메이션
    mainEl.classList.remove('flash-update');
    void mainEl.offsetWidth;
    mainEl.classList.add('flash-update');

    // 세부 정보 업데이트
    this.container.querySelector('#detail-provider').textContent = tunnel_provider || '-';
    this.container.querySelector('#detail-latency').textContent  = latency_ms != null ? `${latency_ms}ms` : '-';
    this.container.querySelector('#detail-last-connected').textContent =
      last_connected ? new Date(last_connected).toLocaleTimeString('ko-KR') : '-';
    this.container.querySelector('#detail-status').textContent = status.toUpperCase();
    this.container.querySelector('#remote-provider-badge').textContent = tunnel_provider || 'unknown';
  }
}
