/**
 * client.js — AIMesh Dashboard Client
 *
 * DashboardClient는 RealtimeClient(또는 MockEventEmitter)와
 * 각 패널(TicketStatusPanel, CompletedTasksPanel, RemoteAccessPanel)을
 * 연결하는 오케스트레이터다.
 *
 * 사용 예::
 *
 *   import { DashboardClient } from './services/client.js';
 *
 *   const dashClient = new DashboardClient({ mock: false });
 *   dashClient.mount({
 *     ticketEl:  document.getElementById('ticket-status-panel'),
 *     tasksEl:   document.getElementById('completed-tasks-panel'),
 *     remoteEl:  document.getElementById('remote-access-panel'),
 *     badgeEl:   document.getElementById('conn-status-badge'),
 *     badgeText: document.getElementById('conn-status-text'),
 *   });
 *   dashClient.start();
 */

import { RealtimeClient }                        from './realtimeClient.js';
import { MockEventEmitter, isMockMode }          from './mockEventEmitter.js';

// ---------------------------------------------------------------------------
// 연결 상태 → 한국어 레이블 매핑
// ---------------------------------------------------------------------------

const CONN_LABELS = {
  connected:    '실시간 연결됨',
  disconnected: '연결 끊김',
  connecting:   '연결중...',
  reconnecting: '재연결중...',
  stopped:      '중단됨',
  failed:       '연결 실패',
};

// ---------------------------------------------------------------------------
// DashboardClient
// ---------------------------------------------------------------------------

export class DashboardClient {
  /**
   * @param {object} options
   * @param {boolean} [options.mock]        - true 이면 MockEventEmitter 사용 (기본: isMockMode())
   * @param {string}  [options.sseUrl]      - SSE 엔드포인트 URL
   * @param {string}  [options.snapshotUrl] - 초기 스냅샷 API URL
   */
  constructor(options = {}) {
    this._mock        = options.mock !== undefined ? options.mock : isMockMode();
    this._sseUrl      = options.sseUrl      || '/api/v1/events/stream';
    this._snapshotUrl = options.snapshotUrl || '/api/v1/dashboard/snapshot';

    this._client  = null;  // RealtimeClient | MockEventEmitter
    this._panels  = {};    // { ticket, tasks, remote }
    this._els     = {};    // { badgeEl, badgeText }
    this._started = false;
  }

  // ── 공개 API ──────────────────────────────────────────────────────────────

  /**
   * 패널 인스턴스와 DOM 요소를 등록한다.
   *
   * @param {object} opts
   * @param {HTMLElement}           opts.ticketEl  - #ticket-status-panel 컨테이너
   * @param {HTMLElement}           opts.tasksEl   - #completed-tasks-panel 컨테이너
   * @param {HTMLElement}           opts.remoteEl  - #remote-access-panel 컨테이너
   * @param {HTMLElement}           [opts.badgeEl] - #conn-status-badge 배지 요소
   * @param {HTMLElement}           [opts.badgeText] - #conn-status-text 텍스트 요소
   */
  mount(opts = {}) {
    // 패널이 이미 인스턴스로 전달되면 그대로 쓰고,
    // HTMLElement가 전달되면 컴포넌트를 직접 생성한다.
    this._panels.ticket = opts.ticketPanel  || null;
    this._panels.tasks  = opts.tasksPanel   || null;
    this._panels.remote = opts.remotePanel  || null;

    // 패널 인스턴스가 없으면 DOM 요소만 저장 (나중에 외부에서 주입 가능)
    this._els.ticketEl  = opts.ticketEl  || null;
    this._els.tasksEl   = opts.tasksEl   || null;
    this._els.remoteEl  = opts.remoteEl  || null;
    this._els.badgeEl   = opts.badgeEl   || null;
    this._els.badgeText = opts.badgeText || null;

    return this;
  }

  /**
   * 패널 인스턴스를 직접 주입한다 (mount 이후 호출 가능).
   *
   * @param {object} panels
   */
  setPanels({ ticketPanel, tasksPanel, remotePanel } = {}) {
    if (ticketPanel) this._panels.ticket = ticketPanel;
    if (tasksPanel)  this._panels.tasks  = tasksPanel;
    if (remotePanel) this._panels.remote = remotePanel;
    return this;
  }

  /**
   * 클라이언트를 시작한다:
   *   1. RealtimeClient(또는 Mock) 생성
   *   2. 서버 연결 시 초기 스냅샷 fetch
   *   3. 이벤트 핸들러 연결
   *   4. 연결 시작
   */
  start() {
    if (this._started) return this;
    this._started = true;

    // 클라이언트 생성
    this._client = this._mock
      ? new MockEventEmitter()
      : new RealtimeClient({ mode: 'sse', sseUrl: this._sseUrl });

    // 초기 스냅샷 로드 (실서버 모드만)
    if (!this._mock) {
      this._loadSnapshot();
    }

    // 이벤트 핸들러 연결
    this._client
      .on('_status',             (s) => this._onStatus(s))
      .on('ticket_update',       (d) => this._onTicketUpdate(d))
      .on('task_complete',       (d) => this._onTaskComplete(d))
      .on('remote_access_change',(d) => this._onRemoteAccessChange(d));

    this._client.connect();
    return this;
  }

  /** 연결을 종료한다. */
  stop() {
    if (this._client) this._client.disconnect();
    this._started = false;
    return this;
  }

  /** 현재 연결 상태 문자열 반환. */
  get state() {
    return this._client ? this._client.state : 'stopped';
  }

  // ── 내부 핸들러 ────────────────────────────────────────────────────────────

  _onStatus(s) {
    this._updateConnectionBadge(s.state);
  }

  _onTicketUpdate(d) {
    if (this._panels.ticket) {
      this._panels.ticket.update(d);
    }
  }

  _onTaskComplete(d) {
    if (this._panels.tasks) {
      this._panels.tasks.addTask(d);
    }
    this._showWowEffect();
  }

  _onRemoteAccessChange(d) {
    if (this._panels.remote) {
      this._panels.remote.update(d);
    }
  }

  // ── 초기 스냅샷 ──────────────────────────────────────────────────────────

  _loadSnapshot() {
    fetch(this._snapshotUrl)
      .then((r) => (r.ok ? r.json() : null))
      .then((snap) => {
        if (!snap) return;

        // 상태별 카운트 초기화
        if (snap.counts && this._panels.ticket) {
          this._panels.ticket.update(snap.counts);
        }

        // 집계 정보 (throughput 1h)
        if (snap.aggregations && this._panels.ticket) {
          const agg1h = snap.aggregations['1h'];
          if (agg1h) {
            this._panels.ticket.update({
              _throughput_1h: agg1h.throughput,
              _completed_1h:  agg1h.completed,
            });
          }
        }

        // 최근 완료 작업 목록
        if (snap.recent_completed && snap.recent_completed.length > 0 && this._panels.tasks) {
          snap.recent_completed.slice(-10).forEach((t) => this._panels.tasks.addTask(t));
        }
      })
      .catch(() => {
        console.warn('[DashboardClient] 스냅샷 로드 실패 — 서버 미기동 가능');
      });
  }

  // ── 연결 배지 업데이트 ────────────────────────────────────────────────────

  _updateConnectionBadge(state) {
    const { badgeEl, badgeText } = this._els;
    if (badgeEl) {
      badgeEl.className = `connection-badge ${state}`;
    }
    if (badgeText) {
      badgeText.textContent = CONN_LABELS[state] || state;
    }
  }

  // ── WOW! 효과 ─────────────────────────────────────────────────────────────

  _showWowEffect() {
    const WOW_TEXTS = ['WOW!', 'POW!', 'ZAP!', 'BAM!', '완료!', 'YES!'];
    const el = document.createElement('div');
    el.className   = 'wow-effect';
    el.textContent = WOW_TEXTS[Math.floor(Math.random() * WOW_TEXTS.length)];
    el.style.left  = Math.random() * (window.innerWidth  - 150) + 'px';
    el.style.top   = Math.random() * (window.innerHeight - 100) + 'px';
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 900);
  }
}
