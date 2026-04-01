/**
 * MetricsPanel.js — 지표 수치 패널
 *
 * 표시 항목:
 *  - 티켓 카운트 (pending/in_progress/done/blocked) — 애니메이션 카운터
 *  - 처리량 (throughput_1h)
 *  - 임계값 게이지: 현재값 vs block_threshold 시각화
 *  - severity 뱃지 (info/warning/critical)
 */

import { computeSeverity, getSeverityStyle } from '../utils/thresholdMapper.js';

/** 카운터 표시 설정 */
const COUNTER_CONFIG = [
  { key: 'in_progress', label: '진행중', color: '#FF6B00' },
  { key: 'pending',     label: '대기',   color: '#0057FF' },
  { key: 'done',        label: '완료',   color: '#00C851' },
  { key: 'blocked',     label: '차단',   color: '#FF3B3F' },
];

export class MetricsPanel {
  /**
   * @param {HTMLElement} container
   */
  constructor(container) {
    this.container = container;
    /** @type {import('../api/types').TicketCounts | null} */
    this._counts     = null;
    /** @type {Record<string, import('../api/types').ThresholdConfig>} */
    this._thresholds = {};
    /** @type {Record<string, number>} threshold별 현재값 (외부에서 주입) */
    this._currentValues = {};
    this._render();
  }

  /**
   * 카운트 + 임계값 업데이트
   * @param {import('../api/types').TicketCounts} counts
   * @param {Record<string, import('../api/types').ThresholdConfig>} thresholds
   * @param {Record<string, number>} [currentValues={}]
   */
  update(counts, thresholds, currentValues = {}) {
    const prevCounts = this._counts ? { ...this._counts } : null;
    this._counts      = counts;
    this._thresholds  = thresholds;
    this._currentValues = currentValues;

    this._renderCounters(counts, prevCounts);
    this._renderThresholdGauges(thresholds, currentValues);
    this._renderThroughput(counts);
  }

  /**
   * 카운터 렌더링 + 변경 시 flash 애니메이션
   * @param {import('../api/types').TicketCounts} counts
   * @param {import('../api/types').TicketCounts | null} prevCounts
   */
  _renderCounters(counts, prevCounts) {
    COUNTER_CONFIG.forEach(({ key, label, color }) => {
      const el = this.container.querySelector(`[data-counter="${key}"]`);
      if (!el) return;

      const valueEl = el.querySelector('.metric-counter');
      if (!valueEl) return;

      const newVal  = counts[key] ?? 0;
      const prevVal = prevCounts ? (prevCounts[key] ?? 0) : null;

      if (prevVal !== null && prevVal !== newVal) {
        this._animateCounter(valueEl, prevVal, newVal);
      } else {
        valueEl.textContent = String(newVal);
      }
    });
  }

  /**
   * 임계값 게이지 렌더링
   * @param {Record<string, import('../api/types').ThresholdConfig>} thresholds
   * @param {Record<string, number>} currentValues
   */
  _renderThresholdGauges(thresholds, currentValues) {
    const container = this.container.querySelector('.threshold-gauges');
    if (!container) return;

    container.innerHTML = '';
    Object.entries(thresholds).forEach(([name, config]) => {
      const currentValue = currentValues[name] ?? 0;
      const el = this._renderThresholdGauge(name, config, currentValue);
      container.appendChild(el);
    });
  }

  /**
   * 임계값 게이지 단일 항목 DOM 생성
   * @param {string} name
   * @param {import('../api/types').ThresholdConfig} config
   * @param {number} currentValue
   * @returns {HTMLElement}
   */
  _renderThresholdGauge(name, config, currentValue) {
    const severity = computeSeverity(currentValue, config);
    const style    = getSeverityStyle(severity);
    const pct      = Math.min(100, (currentValue / config.block_threshold) * 100);
    const warnPct  = Math.min(100, (config.warn_threshold / config.block_threshold) * 100);

    const el = document.createElement('div');
    el.className = `threshold-gauge severity-${severity}`;
    el.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.4rem;">
        <span style="font-size:.8rem;font-weight:700;">${style.icon} ${name}</span>
        <span class="badge" style="background:${style.bg};color:${style.text};border:1px solid ${style.border};padding:.15rem .4rem;border-radius:4px;font-size:.7rem;">${severity.toUpperCase()}</span>
      </div>
      <div style="position:relative;height:8px;background:#eee;border:2px solid var(--comic-dark);border-radius:4px;overflow:hidden;">
        <div class="threshold-bar-fill" style="width:${pct.toFixed(1)}%;background:${style.text};height:100%;border-radius:2px;transition:width .5s ease;"></div>
        <div style="position:absolute;top:0;left:${warnPct.toFixed(1)}%;width:2px;height:100%;background:var(--comic-orange);opacity:.8;"></div>
      </div>
      <div style="display:flex;justify-content:space-between;font-size:.7rem;color:#666;margin-top:.2rem;">
        <span>${currentValue} ${config.unit}</span>
        <span>차단: ${config.block_threshold} ${config.unit}</span>
      </div>
    `;
    return el;
  }

  /**
   * 처리량 표시
   * @param {import('../api/types').TicketCounts} counts
   */
  _renderThroughput(counts) {
    const el = this.container.querySelector('.throughput-value');
    if (el && counts.ts) {
      // counts 자체에 throughput 필드가 없으므로 done 카운트 기반 표시
      el.textContent = counts.done ?? '-';
    }
  }

  /**
   * requestAnimationFrame 기반 숫자 카운터 애니메이션
   * @param {HTMLElement} el
   * @param {number} from
   * @param {number} to
   */
  _animateCounter(el, from, to) {
    const duration = 400;
    const start    = performance.now();

    const step = (now) => {
      const elapsed = now - start;
      const progress = Math.min(elapsed / duration, 1);
      const eased    = 1 - Math.pow(1 - progress, 3); // ease-out cubic
      const value    = Math.round(from + (to - from) * eased);
      el.textContent = String(value);

      if (progress < 1) {
        requestAnimationFrame(step);
      } else {
        el.textContent = String(to);
        el.classList.remove('counter-updated');
        void el.offsetWidth;
        el.classList.add('counter-updated');
        setTimeout(() => el.classList.remove('counter-updated'), 500);
      }
    };

    requestAnimationFrame(step);
  }

  /** 초기 DOM 구조 렌더링 */
  _render() {
    const countersHtml = COUNTER_CONFIG.map(({ key, label, color }) => `
      <div data-counter="${key}" style="text-align:center;padding:.8rem;">
        <div class="metric-counter" style="font-family:var(--font-comic-display);font-size:2.5rem;color:${color};line-height:1;">0</div>
        <div style="font-size:.8rem;font-weight:700;color:#666;margin-top:.3rem;">${label}</div>
      </div>
    `).join('');

    this.container.innerHTML = `
      <div class="metrics-panel">
        <div class="comic-card-header" style="margin-bottom:1rem;">
          <h2 style="font-family:var(--font-comic-display);font-size:1.3rem;">📊 지표 현황</h2>
        </div>
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:.5rem;margin-bottom:1.5rem;">
          ${countersHtml}
        </div>
        <div style="margin-bottom:1rem;">
          <div style="font-size:.75rem;color:#666;font-weight:700;">완료 태스크 총계: <span class="throughput-value">-</span></div>
        </div>
        <div class="threshold-gauges"></div>
      </div>
    `;
  }
}
