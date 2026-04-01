/**
 * useCharacterStateMachine.js — 캐릭터 상태 머신
 *
 * 상태 전이 규칙:
 *   normal  → warning : severity가 'warning'으로 변경될 때
 *   warning → critical: severity가 'critical'으로 변경될 때
 *   critical→ warning : severity가 'warning'으로 복구될 때
 *   *       → normal  : severity가 'info'로 복구될 때
 *
 * 각 전이 시 animationTrigger를 자동 결정:
 *   normal   → idle 애니메이션
 *   warning  → pulse 애니메이션
 *   critical → shake 애니메이션
 *   완료 이벤트 → bounce 애니메이션 (1.2초 후 이전 상태 복구)
 */

import { computeSeverity } from '../utils/thresholdMapper.js';

export class CharacterStateMachine {
  static STATES = Object.freeze({ NORMAL: 'normal', WARNING: 'warning', CRITICAL: 'critical' });
  static ANIMATIONS = Object.freeze({ NORMAL: 'idle', WARNING: 'alert', CRITICAL: 'danger', HAPPY: 'happy' });

  /**
   * @param {string} orgId
   * @param {'info'|'warning'|'critical'} [initialSeverity='info']
   */
  constructor(orgId, initialSeverity = 'info') {
    this.orgId = orgId;
    /** @type {string} */
    this._state     = CharacterStateMachine.STATES.NORMAL;
    /** @type {string} */
    this._animation = CharacterStateMachine.ANIMATIONS.NORMAL;
    /** @type {string} */
    this._emotion   = 'idle';
    /** @type {Function[]} */
    this._subscribers = [];
    /** @type {number | null} */
    this._happyTimer  = null;
    /** @type {string} state before happy animation */
    this._preHappyState = CharacterStateMachine.STATES.NORMAL;

    // 초기 상태 설정
    this.transition(initialSeverity);
  }

  /**
   * severity → 상태 전이 실행
   * @param {'info'|'warning'|'critical'} newSeverity
   */
  transition(newSeverity) {
    const prevState = this._state;
    const newState  = this._severityToState(newSeverity);

    if (newState === prevState) return; // 변화 없음

    this._state     = newState;
    this._animation = this._stateToAnimation(newState);
    this._emotion   = this._computeEmotion(newState);

    this._notify({
      orgId:     this.orgId,
      from:      prevState,
      to:        newState,
      animation: this._animation,
      emotion:   this._emotion,
      severity:  newSeverity,
      ts:        Date.now(),
    });
  }

  /**
   * 완료 이벤트 → happy 애니메이션 (1.2초 후 이전 상태로 복구)
   */
  onTaskComplete() {
    this._preHappyState = this._state;
    const prevEmotion   = this._emotion;

    this._animation = CharacterStateMachine.ANIMATIONS.HAPPY;
    this._emotion   = 'happy';

    this._notify({
      orgId:     this.orgId,
      from:      this._preHappyState,
      to:        'happy_transit',
      animation: CharacterStateMachine.ANIMATIONS.HAPPY,
      emotion:   'happy',
      severity:  this._stateToSeverity(this._preHappyState),
      ts:        Date.now(),
    });

    clearTimeout(this._happyTimer);
    this._happyTimer = setTimeout(() => {
      this._animation = this._stateToAnimation(this._preHappyState);
      this._emotion   = prevEmotion;

      this._notify({
        orgId:     this.orgId,
        from:      'happy_transit',
        to:        this._preHappyState,
        animation: this._animation,
        emotion:   this._emotion,
        severity:  this._stateToSeverity(this._preHappyState),
        ts:        Date.now(),
      });
    }, 1200);
  }

  /**
   * 기준 변경 이벤트 → 일시 alert 애니메이션 (2초 후 복구)
   * @param {import('../api/types').CriteriaChangeEvent} event
   */
  onCriteriaChange(event) {
    const prevAnim    = this._animation;
    const prevEmotion = this._emotion;

    this._animation = CharacterStateMachine.ANIMATIONS.WARNING;
    this._emotion   = 'alert';

    this._notify({
      orgId:     this.orgId,
      from:      this._state,
      to:        'criteria_alert_transit',
      animation: CharacterStateMachine.ANIMATIONS.WARNING,
      emotion:   'alert',
      severity:  this._stateToSeverity(this._state),
      ts:        Date.now(),
    });

    setTimeout(() => {
      this._animation = prevAnim;
      this._emotion   = prevEmotion;
      this._notify({
        orgId:     this.orgId,
        from:      'criteria_alert_transit',
        to:        this._state,
        animation: this._animation,
        emotion:   this._emotion,
        severity:  this._stateToSeverity(this._state),
        ts:        Date.now(),
      });
    }, 2000);
  }

  /**
   * 상태 변화 구독
   * @param {(transition: import('../api/types').StateMachineTransition) => void} handler
   * @returns {() => void} unsubscribe 함수
   */
  subscribe(handler) {
    this._subscribers.push(handler);
    return () => this.unsubscribe(handler);
  }

  /**
   * 구독 해제
   * @param {Function} handler
   */
  unsubscribe(handler) {
    this._subscribers = this._subscribers.filter((h) => h !== handler);
  }

  /** 현재 상태 */
  get currentState() { return this._state; }

  /** 현재 애니메이션 */
  get currentAnimation() { return this._animation; }

  /** 현재 감정 */
  get currentEmotion() { return this._emotion; }

  // ── 내부 헬퍼 ───────────────────────────────────────────────

  /**
   * state → emotion 매핑
   * @param {string} state
   * @returns {string}
   */
  _computeEmotion(state) {
    const map = {
      [CharacterStateMachine.STATES.NORMAL]:   'idle',
      [CharacterStateMachine.STATES.WARNING]:  'alert',
      [CharacterStateMachine.STATES.CRITICAL]: 'danger',
    };
    return map[state] || 'idle';
  }

  /**
   * severity → state 매핑
   * @param {'info'|'warning'|'critical'} severity
   * @returns {string}
   */
  _severityToState(severity) {
    if (severity === 'critical') return CharacterStateMachine.STATES.CRITICAL;
    if (severity === 'warning')  return CharacterStateMachine.STATES.WARNING;
    return CharacterStateMachine.STATES.NORMAL;
  }

  /**
   * state → animation 매핑
   * @param {string} state
   * @returns {string}
   */
  _stateToAnimation(state) {
    const map = {
      [CharacterStateMachine.STATES.NORMAL]:   CharacterStateMachine.ANIMATIONS.NORMAL,
      [CharacterStateMachine.STATES.WARNING]:  CharacterStateMachine.ANIMATIONS.WARNING,
      [CharacterStateMachine.STATES.CRITICAL]: CharacterStateMachine.ANIMATIONS.CRITICAL,
    };
    return map[state] || CharacterStateMachine.ANIMATIONS.NORMAL;
  }

  /**
   * state → severity 역매핑
   * @param {string} state
   * @returns {string}
   */
  _stateToSeverity(state) {
    if (state === CharacterStateMachine.STATES.CRITICAL) return 'critical';
    if (state === CharacterStateMachine.STATES.WARNING)  return 'warning';
    return 'info';
  }

  /**
   * 구독자 알림
   * @param {import('../api/types').StateMachineTransition} transition
   */
  _notify(transition) {
    this._subscribers.forEach((h) => {
      try { h(transition); } catch (err) { console.error('[CharacterStateMachine] 핸들러 오류:', err); }
    });
  }
}

/**
 * 멀티 캐릭터 상태 관리자
 */
export class CharacterStateManager {
  /**
   * @param {string[]} orgIds
   */
  constructor(orgIds) {
    /** @type {Map<string, CharacterStateMachine>} */
    this._machines = new Map();
    orgIds.forEach((id) => {
      this._machines.set(id, new CharacterStateMachine(id));
    });
    /** @type {Function[]} */
    this._globalSubscribers = [];
  }

  /**
   * 현재값 + ThresholdConfig에서 severity 자동 계산 후 상태 머신 전이
   * @param {string} orgId
   * @param {number} currentValue
   * @param {import('../api/types').ThresholdConfig} thresholdConfig
   */
  updateFromThreshold(orgId, currentValue, thresholdConfig) {
    const severity = computeSeverity(currentValue, thresholdConfig);
    this.updateFromSeverity(orgId, severity);
  }

  /**
   * severity로 직접 상태 머신 전이
   * @param {string} orgId
   * @param {'info'|'warning'|'critical'} severity
   */
  updateFromSeverity(orgId, severity) {
    const machine = this._machines.get(orgId);
    if (!machine) return;
    machine.transition(severity);
  }

  /**
   * orgId에 해당하는 상태 머신 반환
   * @param {string} orgId
   * @returns {CharacterStateMachine | undefined}
   */
  getStateMachine(orgId) {
    return this._machines.get(orgId);
  }

  /**
   * 전체 캐릭터 상태 변화 구독
   * @param {(transition: import('../api/types').StateMachineTransition) => void} handler
   * @returns {() => void} unsubscribe 함수
   */
  subscribeAll(handler) {
    this._globalSubscribers.push(handler);

    // 각 머신에 구독 연결
    const unsubs = [];
    this._machines.forEach((machine) => {
      unsubs.push(machine.subscribe(handler));
    });

    return () => {
      this._globalSubscribers = this._globalSubscribers.filter((h) => h !== handler);
      unsubs.forEach((unsub) => unsub());
    };
  }
}
