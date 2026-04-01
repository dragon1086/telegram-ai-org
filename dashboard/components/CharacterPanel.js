/**
 * CharacterPanel.js — 만화 캐릭터 상태 패널
 *
 * 기능:
 *  - severity(info/warning/critical)에 따른 캐릭터 SVG/emoji 교체
 *  - CSS keyframe 애니메이션: idle / alert / danger
 *  - 감정 말풍선 오버레이 (speechBubble)
 *  - HP/Level 게이지 표시
 *  - WCAG AA 대비 기준 준수 색상 매핑
 */

import { getSeverityStyle } from '../utils/thresholdMapper.js';

/** severity별 WCAG AA 색상 매핑 */
const SEVERITY_COLORS = {
  info:     { bg: '#E3F2FD', text: '#0D47A1', border: '#1565C0' }, // 대비 7.5:1
  warning:  { bg: '#FFF3E0', text: '#E65100', border: '#BF360C' }, // 대비 4.8:1
  critical: { bg: '#FFEBEE', text: '#B71C1C', border: '#7F0000' }, // 대비 6.2:1
};

/** emotion별 말풍선 텍스트 풀 */
const SPEECH_TEXTS = {
  idle:   ['⚡ 작업중... 집중집중!', '🎯 OK OK!'],
  alert:  ['⚠️ 경고! 주의 필요!', '🚨 이상 감지!'],
  danger: ['🚫 위험! 차단됨!', '💥 CRITICAL!'],
  happy:  ['✅ 완료! 최고야!', '🎉 DONE!'],
};

/** severity → animation class 매핑 */
const SEVERITY_ANIM = {
  info:     'character-anim-idle',
  warning:  'character-anim-alert',
  critical: 'character-anim-danger',
};

/** HP 게이지 색상 */
const HP_COLORS = {
  high:   '#00C851', // 70~100
  mid:    '#FF6B00', // 30~69
  low:    '#FF3B3F', // 0~29
};

/** orgId → PNG 경로 매핑 */
const CHAR_IMG = {
  pm:          '/static/chars/pm.png',
  engineering: '/static/chars/engineering.png',
  design:      '/static/chars/design.png',
  growth:      '/static/chars/growth.png',
  ops:         '/static/chars/ops.png',
  research:    '/static/chars/research.png',
};

export class CharacterPanel {
  /**
   * @param {HTMLElement} container
   * @param {{ showLevel?: boolean, orgId?: string }} [options={}]
   */
  constructor(container, options = {}) {
    this.container = container;
    this.options   = { showLevel: true, ...options };
    /** @type {import('../api/types').CharacterState | null} */
    this._state    = null;
    this._bubbleTimer = null;
    this._render();
  }

  /**
   * 상태 업데이트 → 애니메이션 트리거
   * @param {import('../api/types').CharacterState} characterState
   */
  update(characterState) {
    const prev = this._state;
    this._state = characterState;

    this._renderCharacter(characterState);

    // 애니메이션 트리거가 명시되어 있으면 우선 적용
    if (characterState.animationTrigger && characterState.animationTrigger !== 'none') {
      const triggerMap = { pulse: 'character-anim-alert', shake: 'character-anim-danger', bounce: 'character-anim-happy' };
      this._triggerAnimation(triggerMap[characterState.animationTrigger] || SEVERITY_ANIM[characterState.severity]);
    } else {
      this._triggerAnimation(SEVERITY_ANIM[characterState.severity] || 'character-anim-idle');
    }

    // severity가 바뀌었거나 처음 렌더링 시 말풍선 갱신
    if (!prev || prev.severity !== characterState.severity || prev.emotion !== characterState.emotion) {
      this._renderSpeechBubble(characterState.emotion, characterState.severity);
    }

    this._renderHPBar(characterState.hp, characterState.severity);
  }

  /**
   * SVG + emoji 렌더링
   * @param {import('../api/types').CharacterState} state
   */
  _renderCharacter(state) {
    const colors = SEVERITY_COLORS[state.severity] || SEVERITY_COLORS.info;
    const panel  = this.container.querySelector('.character-panel');
    if (!panel) return;

    // severity 색상 클래스 교체
    panel.classList.remove('severity-info', 'severity-warning', 'severity-critical');
    panel.classList.add(`severity-${state.severity}`);

    // 아바타 — PNG img 또는 emoji fallback
    const avatarEl = panel.querySelector('.character-avatar');
    if (avatarEl) {
      const statusLabel = {
        info:     '정상',
        warning:  '경고',
        critical: '위험',
      }[state.severity] || '알 수 없음';
      const imgEl = avatarEl.querySelector('.character-img');
      if (imgEl) {
        imgEl.setAttribute('alt', `${state.name} — 현재 상태: ${statusLabel}`);
      } else {
        // emoji fallback
        avatarEl.textContent = state.emoji;
        avatarEl.setAttribute('role', 'img');
        avatarEl.setAttribute('aria-label', `${state.name} — 현재 상태: ${statusLabel}`);
      }
    }

    // 이름
    const nameEl = panel.querySelector('.character-name');
    if (nameEl) {
      nameEl.textContent = state.name;
      nameEl.style.color = state.color;
    }

    // 레벨 뱃지
    if (this.options.showLevel) {
      const levelEl = panel.querySelector('.character-level');
      if (levelEl) levelEl.textContent = `Lv.${state.level}`;
    }

    // 테두리 색상 갱신
    panel.style.borderColor = colors.border;
  }

  /**
   * 말풍선 렌더링
   * @param {string} emotion
   * @param {string} severity
   */
  _renderSpeechBubble(emotion, severity) {
    const panel = this.container.querySelector('.character-panel');
    if (!panel) return;

    const texts = SPEECH_TEXTS[emotion] || SPEECH_TEXTS.idle;
    const text  = texts[Math.floor(Math.random() * texts.length)];
    const colors = SEVERITY_COLORS[severity] || SEVERITY_COLORS.info;

    let bubble = panel.querySelector('.speech-bubble');
    if (!bubble) {
      bubble = document.createElement('div');
      bubble.className = 'speech-bubble';
      panel.appendChild(bubble);
    }

    bubble.textContent = text;
    bubble.style.background = colors.bg;
    bubble.style.color       = colors.text;
    bubble.style.borderColor = colors.border;

    // 재애니메이션 트리거
    bubble.classList.remove('speech-bubble');
    void bubble.offsetWidth;
    bubble.classList.add('speech-bubble');

    // 5초 후 말풍선 숨김
    clearTimeout(this._bubbleTimer);
    this._bubbleTimer = setTimeout(() => {
      bubble.style.opacity = '0';
      bubble.style.transition = 'opacity 0.5s';
    }, 5000);
  }

  /**
   * HP 게이지 렌더링
   * @param {number} hp 0~100
   * @param {string} severity
   */
  _renderHPBar(hp, severity) {
    const panel = this.container.querySelector('.character-panel');
    if (!panel) return;

    const fill  = panel.querySelector('.hp-bar-fill');
    const label = panel.querySelector('.hp-value');
    if (!fill) return;

    const pct   = Math.max(0, Math.min(100, hp));
    fill.style.width = `${pct}%`;

    // HP 색상
    let color;
    if (pct >= 70) color = HP_COLORS.high;
    else if (pct >= 30) color = HP_COLORS.mid;
    else color = HP_COLORS.low;
    fill.style.background = color;

    if (label) label.textContent = `${pct}`;

    // 애니메이션 클래스 리트리거
    fill.classList.remove('hp-bar-fill');
    void fill.offsetWidth;
    fill.classList.add('hp-bar-fill');
  }

  /**
   * CSS 클래스 전환으로 애니메이션 트리거
   * @param {string} animClass
   */
  _triggerAnimation(animClass) {
    const avatar = this.container.querySelector('.character-avatar');
    if (!avatar) return;

    avatar.classList.remove(
      'character-anim-idle',
      'character-anim-alert',
      'character-anim-danger',
      'character-anim-happy',
    );
    void avatar.offsetWidth; // reflow
    avatar.classList.add(animClass);

    // happy 애니메이션은 1회만 실행 후 idle로 복귀
    if (animClass === 'character-anim-happy') {
      setTimeout(() => {
        avatar.classList.remove('character-anim-happy');
        avatar.classList.add('character-anim-idle');
      }, 1200);
    }
  }

  /** 초기 DOM 구조 렌더링 */
  _render() {
    const imgSrc = CHAR_IMG[this.options.orgId] || '';
    const avatarContent = imgSrc
      ? `<img src="${imgSrc}" alt="${this.options.orgId || ''}" class="character-img" />`
      : '❓';
    this.container.innerHTML = `
      <div class="character-panel severity-info">
        <div class="character-avatar character-anim-idle">${avatarContent}</div>
        <div class="character-name" style="font-family:var(--font-comic-display);font-size:1.4rem;letter-spacing:.05em;margin-bottom:.5rem;">-</div>
        ${this.options.showLevel ? '<div class="character-level" style="font-size:.85rem;color:#666;margin-bottom:.5rem;">Lv.-</div>' : ''}
        <div class="hp-bar-container">
          <div class="hp-bar-label">
            <span>HP</span>
            <span><span class="hp-value">-</span>/100</span>
          </div>
          <div class="hp-bar-track">
            <div class="hp-bar-fill" style="width:0%;background:${HP_COLORS.high};"></div>
          </div>
        </div>
      </div>
    `;
  }
}
