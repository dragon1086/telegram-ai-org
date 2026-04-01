/**
 * CompletedTasksPanel.js — 완료 작업 목록 패널
 * 최근 N건 스크롤 리스트
 */

const MAX_TASKS = 50;

export class CompletedTasksPanel {
  /**
   * @param {HTMLElement} container
   * @param {Array} initialTasks
   */
  constructor(container, initialTasks = []) {
    this.container = container;
    this.tasks = [...initialTasks];
    this._render();
  }

  /** task_complete 이벤트 수신 시 호출 */
  addTask(task) {
    this.tasks.unshift({
      id: task.id || `task-${Date.now()}`,
      title: task.title || '(제목 없음)',
      org_id: task.org_id || 'unknown',
      completed_at: task.completed_at || new Date().toISOString(),
      result: task.result || '완료',
    });

    // 최대 MAX_TASKS건 유지
    if (this.tasks.length > MAX_TASKS) {
      this.tasks = this.tasks.slice(0, MAX_TASKS);
    }

    this._prependTaskItem(this.tasks[0]);
    this._updateCount();
  }

  _render() {
    this.container.innerHTML = `
      <div class="comic-card" id="completed-tasks-card">
        <div class="comic-card-header">
          <h2 class="comic-card-title">✅ 완료 작업</h2>
          <span class="badge" style="background:#d4ffd4;" id="completed-count">0건</span>
        </div>
        <div class="tasks-list" id="tasks-list"></div>
        ${this.tasks.length === 0 ? '<p style="text-align:center; color:#aaa; padding:2rem; font-style:italic;">아직 완료된 작업이 없습니다.</p>' : ''}
      </div>
    `;

    const list = this.container.querySelector('#tasks-list');
    this.tasks.forEach((t) => list.appendChild(this._createTaskEl(t)));
    this._updateCount();
  }

  _prependTaskItem(task) {
    const list = this.container.querySelector('#tasks-list');
    if (!list) return;

    // "작업 없음" 플레이스홀더 제거
    const placeholder = this.container.querySelector('p[style*="작업 없음"], p[style*="color:#aaa"]');
    if (placeholder) placeholder.remove();

    const el = this._createTaskEl(task);
    list.insertBefore(el, list.firstChild);

    // MAX_TASKS 초과 시 마지막 항목 제거
    while (list.children.length > MAX_TASKS) {
      list.removeChild(list.lastChild);
    }
  }

  _createTaskEl(task) {
    const el = document.createElement('div');
    el.className = 'task-item';
    el.dataset.taskId = task.id;

    const orgEmoji = _orgEmoji(task.org_id);
    const timeStr = _formatRelativeTime(new Date(task.completed_at));

    el.innerHTML = `
      <span class="task-icon">${orgEmoji}</span>
      <div class="task-body">
        <div class="task-title" title="${_escape(task.title)}">${_escape(task.title)}</div>
        <div class="task-meta">
          <span class="badge" style="font-size:0.65rem; padding:0.1rem 0.4rem;">${_escape(task.org_id)}</span>
          &nbsp;${_escape(task.result)}
        </div>
      </div>
      <span class="task-time">${timeStr}</span>
    `;
    return el;
  }

  _updateCount() {
    const badge = this.container.querySelector('#completed-count');
    if (badge) badge.textContent = `${this.tasks.length}건`;
  }
}

function _orgEmoji(orgId) {
  const map = {
    dev: '🔧', design: '🎨', product: '📋',
    ops: '⚙️', growth: '📈', research: '🔬', pm: '🎯',
  };
  return map[orgId] || '📦';
}

function _formatRelativeTime(date) {
  const diff = Math.floor((Date.now() - date.getTime()) / 1000);
  if (diff < 60) return `${diff}초 전`;
  if (diff < 3600) return `${Math.floor(diff / 60)}분 전`;
  return date.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
}

function _escape(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
