/**
 * thresholdMapper.js — block_threshold 값 → UI severity 레벨 매핑 유틸리티
 *
 * criteria_tracking.yaml 설계:
 *   severity_mapping:
 *     1: "info"     → value < warn_threshold
 *     2: "warning"  → warn_threshold <= value < block_threshold
 *     3: "critical" → value >= block_threshold
 */

/** severity 레벨 상수 */
export const SEVERITY_LEVELS = Object.freeze({ INFO: 'info', WARNING: 'warning', CRITICAL: 'critical' });

/** severity 순위 (높을수록 심각) */
export const SEVERITY_RANK = Object.freeze({ info: 1, warning: 2, critical: 3 });

/** severity별 WCAG AA 스타일 */
const SEVERITY_STYLES = {
  info: {
    bg:     '#E3F2FD',
    text:   '#0D47A1',
    border: '#1565C0',
    icon:   'ℹ️',
    label:  'INFO',
  },
  warning: {
    bg:     '#FFF3E0',
    text:   '#E65100',
    border: '#BF360C',
    icon:   '⚠️',
    label:  'WARNING',
  },
  critical: {
    bg:     '#FFEBEE',
    text:   '#B71C1C',
    border: '#7F0000',
    icon:   '🚫',
    label:  'CRITICAL',
  },
};

/**
 * 현재값과 임계값 설정으로 severity 결정
 *
 * criteria_tracking.yaml severity_mapping 로직:
 *   level 1 (info)     → value < warn_threshold
 *   level 2 (warning)  → warn_threshold <= value < block_threshold
 *   level 3 (critical) → value >= block_threshold
 *
 * @param {number} currentValue - 현재 측정값
 * @param {{ warn_threshold: number, block_threshold: number }} thresholdConfig
 * @returns {'info' | 'warning' | 'critical'}
 */
export function computeSeverity(currentValue, thresholdConfig) {
  if (currentValue == null || thresholdConfig == null) return SEVERITY_LEVELS.INFO;

  const { warn_threshold, block_threshold } = thresholdConfig;

  if (currentValue >= block_threshold) return SEVERITY_LEVELS.CRITICAL;
  if (currentValue >= warn_threshold)  return SEVERITY_LEVELS.WARNING;
  return SEVERITY_LEVELS.INFO;
}

/**
 * 수치 값을 threshold 설정에 따라 severity 레벨 문자열로 변환한다.
 *
 * 오버로드 형태로 두 가지 호출 방식을 모두 지원:
 *   (a) getSeverityStyle(value, { warning, critical }) → severity 문자열
 *   (b) getSeverityStyle(severity)                     → WCAG 색상 정보 객체
 *
 * @param {number | 'info' | 'warning' | 'critical'} valueOrSeverity
 * @param {{ warning?: number, critical?: number }} [thresholds]
 * @returns {'info'|'warning'|'critical' | { bg: string, text: string, border: string, icon: string, label: string }}
 *
 * @example
 *   getSeverityStyle(3);                            // 'info'
 *   getSeverityStyle(6, { warning: 5, critical: 10 }); // 'warning'
 *   getSeverityStyle('warning');                    // { bg, text, border, icon, label }
 */
export function getSeverityStyle(valueOrSeverity, thresholds) {
  // 수치 입력: threshold 비교 → severity 문자열 반환
  if (typeof valueOrSeverity === 'number') {
    const warnAt     = (thresholds && thresholds.warning  != null) ? thresholds.warning  : 5;
    const criticalAt = (thresholds && thresholds.critical != null) ? thresholds.critical : 10;
    if (valueOrSeverity >= criticalAt) return SEVERITY_LEVELS.CRITICAL;
    if (valueOrSeverity >= warnAt)     return SEVERITY_LEVELS.WARNING;
    return SEVERITY_LEVELS.INFO;
  }
  // severity 문자열 입력: WCAG 색상 정보 반환
  return SEVERITY_STYLES[valueOrSeverity] || SEVERITY_STYLES.info;
}

/**
 * 임계값 설정 배열에서 가장 높은 severity 반환 (대시보드 전체 상태)
 * @param {Array<{ severity?: string, currentValue?: number, warn_threshold?: number, block_threshold?: number }>} thresholdValues
 * @returns {'info' | 'warning' | 'critical'}
 */
export function getOverallSeverity(thresholdValues) {
  if (!thresholdValues || thresholdValues.length === 0) return SEVERITY_LEVELS.INFO;

  let maxRank = 1;
  let maxSeverity = SEVERITY_LEVELS.INFO;

  thresholdValues.forEach((item) => {
    let sev;
    if (item.severity) {
      sev = item.severity;
    } else if (item.currentValue != null && item.warn_threshold != null && item.block_threshold != null) {
      sev = computeSeverity(item.currentValue, item);
    } else {
      return;
    }

    const rank = SEVERITY_RANK[sev] || 1;
    if (rank > maxRank) {
      maxRank     = rank;
      maxSeverity = sev;
    }
  });

  return maxSeverity;
}

/**
 * HP 계산: block_threshold 기준으로 역산
 *   critical (value >= block)  → 0~30 HP
 *   warning  (warn <= v < block)→ 31~70 HP
 *   info     (v < warn)        → 71~100 HP
 *
 * @param {'info' | 'warning' | 'critical'} severity
 * @param {number} currentValue
 * @param {{ warn_threshold: number, block_threshold: number }} thresholdConfig
 * @returns {number} 0~100
 */
export function computeHPFromSeverity(severity, currentValue, thresholdConfig) {
  if (!thresholdConfig) {
    if (severity === 'critical') return 20;
    if (severity === 'warning')  return 55;
    return 85;
  }

  const { warn_threshold, block_threshold } = thresholdConfig;

  if (severity === 'critical') {
    // block_threshold 이상 → HP 0~30
    const excess = currentValue - block_threshold;
    const range  = block_threshold; // 같은 범위를 역으로 사용
    const hp     = Math.max(0, 30 - Math.min(30, (excess / Math.max(range, 1)) * 30));
    return Math.round(hp);
  }

  if (severity === 'warning') {
    // warn_threshold ~ block_threshold → HP 31~70
    const span   = block_threshold - warn_threshold;
    const pos    = currentValue - warn_threshold;
    const ratio  = span > 0 ? pos / span : 0;
    const hp     = 70 - Math.round(ratio * 39); // 70 → 31
    return Math.max(31, Math.min(70, hp));
  }

  // info: value < warn_threshold → HP 71~100
  const ratio = warn_threshold > 0 ? currentValue / warn_threshold : 0;
  const hp    = 100 - Math.round(ratio * 29); // 100 → 71
  return Math.max(71, Math.min(100, hp));
}
