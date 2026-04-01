/**
 * types.ts — 대시보드 API 타입 정의
 */

/** 캐릭터 상태 */
export interface CharacterState {
  orgId: string;
  name: string;
  emoji: string;
  color: string;
  hp: number;           // 0~100
  level: number;
  emotion: 'idle' | 'alert' | 'danger' | 'happy';
  animationTrigger: 'none' | 'pulse' | 'shake' | 'bounce';
  severity: 'info' | 'warning' | 'critical';
  lastUpdated: number;
}

/** 티켓 카운트 */
export interface TicketCounts {
  pending: number;
  in_progress: number;
  done: number;
  blocked: number;
  ts: number;
}

/** 임계값 설정 */
export interface ThresholdConfig {
  name: string;
  block_threshold: number;
  warn_threshold: number;
  unit: string;
  criteria_version: string;
  severity?: 'info' | 'warning' | 'critical';
}

/** 기준 변경 이벤트 */
export interface CriteriaChangeEvent {
  type: 'criteria_change';
  threshold_name: string;
  old_version: string;
  new_version: string;
  old_value: number;
  new_value: number;
  changed_at: number;
  change_reason?: string;
}

/** 대시보드 스냅샷 */
export interface DashboardSnapshot {
  counts: TicketCounts;
  aggregations: Record<string, { throughput: number; completed: number }>;
  recent_completed: any[];
  characters: CharacterState[];
  thresholds: Record<string, ThresholdConfig>;
  criteria_version: string;
  ts: number;
}

/** API 클라이언트 인터페이스 */
export interface IApiClient {
  getCharacterStatus(orgId: string): Promise<CharacterState>;
  getThresholds(): Promise<Record<string, ThresholdConfig>>;
  getDashboardSnapshot(): Promise<DashboardSnapshot>;
  getTasks(status?: string): Promise<any[]>;
  updateCharacterState(orgId: string, state: Partial<CharacterState>): Promise<CharacterState>;
}

/** 네트워크 에러 */
export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

/** severity 레벨 */
export type Severity = 'info' | 'warning' | 'critical';

/** severity WCAG 색상 정보 */
export interface SeverityStyle {
  bg: string;
  text: string;
  border: string;
  icon: string;
  label: string;
}

/** 상태 머신 전이 */
export interface StateMachineTransition {
  orgId: string;
  from: string;
  to: string;
  animation: string;
  emotion: string;
  severity: Severity;
  ts: number;
}

/** 실시간 훅 옵션 */
export interface RealtimeStatusHookOptions {
  mode?: 'sse' | 'polling';
  pollInterval?: number;
  sseUrl?: string;
  apiClient?: IApiClient;
}

/** 연결 상태 */
export type ConnectionState = 'connected' | 'disconnected' | 'connecting' | 'polling';
