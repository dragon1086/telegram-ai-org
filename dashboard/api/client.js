/**
 * api/client.js — 백엔드 API 클라이언트 모듈
 *
 * 환경변수 (window.__ENV__ 또는 URL 파라미터로 주입):
 *   VITE_API_BASE_URL   : API 서버 기본 URL (기본값: '')
 *   VITE_API_KEY        : X-API-Key 헤더값
 *   VITE_USE_MOCK       : '1' 시 Mock 모드 활성화
 *
 * Mock 모드 전환: URL에 ?mock=1 추가 또는 VITE_USE_MOCK=1
 */

/**
 * 환경변수 읽기 (window.__ENV__ → URLSearchParams 순)
 * @param {string} key
 * @param {string} [fallback='']
 * @returns {string}
 */
export function getEnv(key, fallback = '') {
  if (typeof window !== 'undefined' && window.__ENV__ && window.__ENV__[key] != null) {
    return String(window.__ENV__[key]);
  }
  if (typeof window !== 'undefined' && window.location) {
    const params = new URLSearchParams(window.location.search);
    // URL 파라미터 키는 소문자 단축형으로도 지원
    const shortKey = key.replace('VITE_', '').toLowerCase();
    if (params.has(shortKey)) return params.get(shortKey);
    if (params.has(key)) return params.get(key);
  }
  return fallback;
}

/**
 * URL ?mock=1 또는 env VITE_USE_MOCK=1 기반 모드 판단
 * @returns {boolean}
 */
export function isMockMode() {
  if (typeof window !== 'undefined' && window.location) {
    const params = new URLSearchParams(window.location.search);
    if (params.get('mock') === '1' || params.get('mock') === 'true') return true;
    if (params.get('mock') === '0' || params.get('mock') === 'false') return false;
  }
  return getEnv('VITE_USE_MOCK', '0') === '1';
}

/**
 * 네트워크 에러 클래스
 */
export class ApiError extends Error {
  /**
   * @param {number} status HTTP 상태 코드
   * @param {string} message 에러 메시지
   */
  constructor(status, message) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

/**
 * 실제 API 클라이언트
 */
export class ApiClient {
  /**
   * @param {{ baseUrl?: string, apiKey?: string, timeout?: number }} options
   */
  constructor(options = {}) {
    this.baseUrl = options.baseUrl ?? getEnv('VITE_API_BASE_URL', '');
    this.apiKey  = options.apiKey  ?? getEnv('VITE_API_KEY', '');
    this.timeout = options.timeout ?? 5000;
  }

  /**
   * fetch 래퍼 — timeout + 에러 처리 (AbortController)
   * @param {string} path
   * @param {RequestInit} [options={}]
   * @returns {Promise<any>}
   */
  async _fetch(path, options = {}) {
    const controller = new AbortController();
    const timerId = setTimeout(() => controller.abort(), this.timeout);

    const headers = { 'Content-Type': 'application/json', ...options.headers };
    if (this.apiKey) headers['X-API-Key'] = this.apiKey;

    try {
      const res = await fetch(`${this.baseUrl}${path}`, {
        ...options,
        headers,
        signal: controller.signal,
      });
      clearTimeout(timerId);

      if (!res.ok) {
        let msg = `HTTP ${res.status}`;
        try { const body = await res.json(); msg = body.detail || body.message || msg; } catch { /* ignore */ }
        throw new ApiError(res.status, msg);
      }

      const ct = res.headers.get('Content-Type') || '';
      if (ct.includes('application/json')) return res.json();
      return res.text();
    } catch (err) {
      clearTimeout(timerId);
      if (err.name === 'AbortError') throw new ApiError(408, 'Request timeout');
      throw err;
    }
  }

  /**
   * 캐릭터 상태 조회
   * @param {string} orgId
   * @returns {Promise<import('./types').CharacterState>}
   */
  getCharacterStatus(orgId) {
    return this._fetch(`/api/v1/dashboard/character/${encodeURIComponent(orgId)}`);
  }

  /**
   * 임계값 설정 조회 (criteria_tracking.yaml 내용)
   * @returns {Promise<Record<string, import('./types').ThresholdConfig>>}
   */
  getThresholds() {
    return this._fetch('/api/v1/dashboard/thresholds');
  }

  /**
   * 대시보드 스냅샷 조회
   * @returns {Promise<import('./types').DashboardSnapshot>}
   */
  getDashboardSnapshot() {
    return this._fetch('/api/v1/dashboard/snapshot');
  }

  /**
   * 태스크 목록 조회
   * @param {string} [status]
   * @returns {Promise<any[]>}
   */
  getTasks(status) {
    const qs = status ? `?status=${encodeURIComponent(status)}` : '';
    return this._fetch(`/api/v1/tasks${qs}`);
  }

  /**
   * 캐릭터 상태 업데이트
   * @param {string} orgId
   * @param {Partial<import('./types').CharacterState>} state
   * @returns {Promise<import('./types').CharacterState>}
   */
  updateCharacterState(orgId, state) {
    return this._fetch(`/api/v1/dashboard/character/${encodeURIComponent(orgId)}/state`, {
      method: 'POST',
      body: JSON.stringify(state),
    });
  }
}

/**
 * Mock API 클라이언트 — mock_data.json 기반 응답
 */
export class MockApiClient {
  constructor() {
    this._dataPromise = null;
  }

  /** mock_data.json 로드 (캐시) */
  async _loadData() {
    if (!this._dataPromise) {
      this._dataPromise = fetch(new URL('./mock_data.json', import.meta.url))
        .then((r) => {
          if (!r.ok) throw new ApiError(r.status, 'mock_data.json 로드 실패');
          return r.json();
        })
        .then((data) => {
          // ts 필드를 현재 시각으로 패치
          const now = Date.now();
          if (data.snapshot) data.snapshot.ts = now;
          (data.characters || []).forEach((c) => { c.lastUpdated = now; });
          (data.recent_completed || []).forEach((t) => { t.completed_at = now; });
          (data.criteria_change_events || []).forEach((e) => { e.changed_at = now; });
          return data;
        });
    }
    return this._dataPromise;
  }

  async getCharacterStatus(orgId) {
    const data = await this._loadData();
    const char = (data.characters || []).find((c) => c.orgId === orgId);
    if (!char) throw new ApiError(404, `캐릭터를 찾을 수 없습니다: ${orgId}`);
    return char;
  }

  async getThresholds() {
    const data = await this._loadData();
    return data.thresholds || {};
  }

  async getDashboardSnapshot() {
    const data = await this._loadData();
    return {
      ...data.snapshot,
      characters: data.characters || [],
      thresholds: data.thresholds || {},
      recent_completed: data.recent_completed || [],
      aggregations: data.snapshot?.aggregations || {},
    };
  }

  async getTasks(status) {
    const data = await this._loadData();
    const tasks = data.recent_completed || [];
    if (status) return tasks.filter((t) => t.state === status);
    return tasks;
  }

  async updateCharacterState(orgId, state) {
    const current = await this.getCharacterStatus(orgId);
    return { ...current, ...state, lastUpdated: Date.now() };
  }
}

/**
 * isMockMode() 판단 후 적절한 클라이언트 반환
 * @returns {ApiClient | MockApiClient}
 */
export function createApiClient() {
  return isMockMode() ? new MockApiClient() : new ApiClient();
}
