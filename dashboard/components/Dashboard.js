/**
 * Dashboard.js — 캐릭터 컨셉 메인 대시보드 조립 컴포넌트
 *
 * 레이아웃: 3패널 그리드
 *   좌측: CharacterPanel (캐릭터 상태 + 애니메이션)
 *   중앙: MetricsPanel (지표 수치 + 임계값)
 *   우측: EventLogPanel (이벤트 로그)
 *
 * 사용 예:
 *   const dashboard = new Dashboard(document.getElementById('app'));
 *   dashboard.init(apiClient, realtimeHook);
 */

import { CharacterPanel }       from './CharacterPanel.js';
import { MetricsPanel }         from './MetricsPanel.js';
import { EventLogPanel }        from './EventLogPanel.js';
import { CriteriaChangeMarker } from './CriteriaChangeMarker.js';
import { CharacterStateManager } from '../hooks/useCharacterStateMachine.js';

/** ORG_CHARACTERS 설정 */
const ORG_CHARACTERS = [
  { orgId: 'aiorg_engineering_bot', name: '개발실',  emoji: '🦾', color: '#0057FF' },
  { orgId: 'aiorg_design_bot',      name: '디자인실', emoji: '🎨', color: '#9B00FF' },
  { orgId: 'aiorg_ops_bot',         name: '운영실',  emoji: '⚙️', color: '#00C851' },
  { orgId: 'aiorg_product_bot',     name: '기획실',  emoji: '📋', color: '#FF6B00' },
  { orgId: 'aiorg_growth_bot',      name: '성장실',  emoji: '📈', color: '#FF3B3F' },
  { orgId: 'aiorg_research_bot',    name: '리서치실', emoji: '🔬', color: '#00B8D4' },
  { orgId: 'aiorg_pm_bot',          name: 'PM',      emoji: '🎯', color: '#FFD600' },
];

export class Dashboard {
  /**
   * @param {HTMLElement} container
   */
  constructor(container) {
    this.container = container;
    /** @type {Map<string, CharacterPanel>} */
    this._characterPanels = new Map();
    /** @type {MetricsPanel | null} */
    this._metricsPanel    = null;
    /** @type {EventLogPanel | null} */
    this._eventLogPanel   = null;
    /** @type {CriteriaChangeMarker | null} */
    this._criteriaMarker  = null;
    /** @type {CharacterStateManager | null} */
    this._stateManager    = null;
    /** @type {any | null} */
    this._apiClient       = null;
    /** @type {any | null} */
    this._realtimeHook    = null;
    /** @type {Record<string, import('../api/types').ThresholdConfig>} */
    this._thresholds      = {};

    this._render();
  }

  /**
   * 대시보드 초기화
   * @param {import('../api/client').ApiClient | import('../api/client').MockApiClient} apiClient
   * @param {import('../hooks/useRealtimeStatus').RealtimeStatusHook} realtimeStatusHook
   */
  async init(apiClient, realtimeStatusHook) {
    this._apiClient    = apiClient;
    this._realtimeHook = realtimeStatusHook;

    // 상태 머신 초기화
    const orgIds = ORG_CHARACTERS.map((c) => c.orgId);
    this._stateManager = new CharacterStateManager(orgIds);
    this._stateManager.subscribeAll((transition) => {
      const panel = this._characterPanels.get(transition.orgId);
      if (panel) {
        const char = ORG_CHARACTERS.find((c) => c.orgId === transition.orgId) || {};
        panel.update({
          ...char,
          orgId:            transition.orgId,
          hp:               this._severityToHP(transition.severity),
          level:            1,
          emotion:          transition.emotion,
          animationTrigger: 'none',
          severity:         transition.severity,
          lastUpdated:      transition.ts,
        });
      }
    });

    // 초기 스냅샷 로드
    try {
      const snapshot = await apiClient.getDashboardSnapshot();
      this._thresholds = snapshot.thresholds || {};

      // 캐릭터 초기 상태 적용
      (snapshot.characters || []).forEach((char) => {
        const panel = this._characterPanels.get(char.orgId);
        if (panel) panel.update(char);
        this._stateManager.updateFromSeverity(char.orgId, char.severity);
      });

      // 메트릭 초기 적용
      if (this._metricsPanel && snapshot.counts) {
        this._metricsPanel.update(snapshot.counts, this._thresholds);
      }
    } catch (err) {
      console.error('[Dashboard] 초기 스냅샷 로드 실패:', err);
    }

    // 실시간 훅 이벤트 구독
    realtimeStatusHook.on('ticket_update',    (data) => this._handleRealtimeEvent({ type: 'ticket_update', ...data }));
    realtimeStatusHook.on('task_complete',    (data) => this._handleRealtimeEvent({ type: 'task_complete', ...data }));
    realtimeStatusHook.on('criteria_change',  (data) => this._handleCriteriaChange(data));
    realtimeStatusHook.on('character_update', (data) => this._handleRealtimeEvent({ type: 'character_update', ...data }));

    realtimeStatusHook.start();
  }

  /**
   * 실시간 이벤트 처리
   * @param {{ type: string, [key: string]: any }} event
   */
  _handleRealtimeEvent(event) {
    // 이벤트 로그 추가
    if (this._eventLogPanel) this._eventLogPanel.addEvent(event);

    switch (event.type) {
      case 'ticket_update':
        if (this._metricsPanel) {
          this._metricsPanel.update(event, this._thresholds);
        }
        break;

      case 'task_complete': {
        const orgId = event.org_id || event.assignee;
        if (orgId && this._stateManager) {
          this._stateManager.getStateMachine(orgId)?.onTaskComplete();
        }
        break;
      }

      case 'character_update': {
        const orgId = event.org_id || event.orgId;
        if (!orgId) break;
        const panel = this._characterPanels.get(orgId);
        if (panel) {
          const charMeta = ORG_CHARACTERS.find((c) => c.orgId === orgId) || {};
          panel.update({ ...charMeta, ...event });
        }
        if (event.severity && this._stateManager) {
          this._stateManager.updateFromSeverity(orgId, event.severity);
        }
        break;
      }
    }
  }

  /**
   * 기준 변경 이벤트 처리
   * @param {import('../api/types').CriteriaChangeEvent} event
   */
  _handleCriteriaChange(event) {
    // 이벤트 로그 특별 렌더링
    if (this._eventLogPanel) this._eventLogPanel.addCriteriaChange(event);

    // 기준 변경 마커 표시
    if (this._criteriaMarker) this._criteriaMarker.show(event);

    // 상태 머신에 기준 변경 통보
    if (this._stateManager) {
      ORG_CHARACTERS.forEach(({ orgId }) => {
        this._stateManager.getStateMachine(orgId)?.onCriteriaChange(event);
      });
    }

    // 임계값 캐시 업데이트
    if (event.threshold_name && this._thresholds[event.threshold_name]) {
      this._thresholds[event.threshold_name].block_threshold = event.new_value;
      this._thresholds[event.threshold_name].criteria_version = event.new_version;
    }
  }

  /**
   * 티켓 카운트 기반 캐릭터 상태 계산
   *
   * 규칙:
   *   - blocked > 0             → severity 'critical', emotion 'alert'
   *   - in_progress > 10        → severity 'critical', emotion 'alert'
   *   - in_progress > 5         → severity 'warning',  emotion 'alert'
   *   - completed 증가 감지 시   → emotion 'happy' (일회성)
   *   - 그 외                   → severity 'info',     emotion 'idle'
   *
   * @param {{ in_progress?: number, blocked?: number, completed?: number }} counts
   * @param {{ prevCompleted?: number }} [opts]
   * @returns {{ severity: 'info'|'warning'|'critical', emotion: 'idle'|'alert'|'happy' }}
   */
  _computeCharacterState(counts, opts = {}) {
    const inProgress = counts.in_progress ?? 0;
    const blocked    = counts.blocked    ?? 0;
    const completed  = counts.completed  ?? 0;

    // 완료 작업 증가 감지 → happy (우선 체크, severity는 계속 반영)
    const justCompleted = opts.prevCompleted !== undefined && completed > opts.prevCompleted;

    let severity = 'info';
    let emotion  = 'idle';

    if (blocked > 0 || inProgress > 10) {
      severity = 'critical';
      emotion  = 'alert';
    } else if (inProgress > 5) {
      severity = 'warning';
      emotion  = 'alert';
    }

    // happy 이모션이 alert보다 우선할 때: 완료 증가 + info/warning 상태
    if (justCompleted && severity !== 'critical') {
      emotion = 'happy';
    }

    return { severity, emotion };
  }

  /**
   * severity → HP 역산 (info=high, critical=low)
   * @param {string} severity
   * @returns {number}
   */
  _severityToHP(severity) {
    if (severity === 'info')     return 85;
    if (severity === 'warning')  return 55;
    if (severity === 'critical') return 25;
    return 85;
  }

  /** 리소스 해제 */
  destroy() {
    if (this._realtimeHook) this._realtimeHook.stop();
    this._characterPanels.clear();
    this._metricsPanel   = null;
    this._eventLogPanel  = null;
    this._criteriaMarker = null;
    this._stateManager   = null;
  }

  /** 초기 DOM 구조 렌더링 */
  _render() {
    this.container.innerHTML = `
      <div class="dashboard-character-grid">
        <div id="dashboard-characters-col">
          <div id="criteria-marker-zone" style="margin-bottom:1rem;"></div>
          <div id="character-panels-grid" style="display:grid;grid-template-columns:1fr 1fr;gap:1rem;"></div>
        </div>
        <div id="dashboard-metrics-col"></div>
        <div id="dashboard-events-col"></div>
      </div>
    `;

    // 캐릭터 패널 생성
    const grid = this.container.querySelector('#character-panels-grid');
    ORG_CHARACTERS.forEach((char) => {
      const wrapper = document.createElement('div');
      wrapper.id = `char-panel-${char.orgId}`;
      grid.appendChild(wrapper);
      const panel = new CharacterPanel(wrapper, { orgId: char.orgId });
      // 기본 상태로 초기화
      panel.update({ ...char, hp: 85, level: 1, emotion: 'idle', animationTrigger: 'none', severity: 'info', lastUpdated: Date.now() });
      this._characterPanels.set(char.orgId, panel);
    });

    // 메트릭 패널
    const metricsCol = this.container.querySelector('#dashboard-metrics-col');
    this._metricsPanel = new MetricsPanel(metricsCol);

    // 이벤트 로그 패널
    const eventsCol = this.container.querySelector('#dashboard-events-col');
    this._eventLogPanel = new EventLogPanel(eventsCol);

    // 기준 변경 마커
    const markerZone = this.container.querySelector('#criteria-marker-zone');
    this._criteriaMarker = new CriteriaChangeMarker(markerZone);
  }
}
