-- Migration 003: 진척 스냅샷 테이블

CREATE TABLE IF NOT EXISTS progress_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id TEXT NOT NULL,
    progress REAL NOT NULL,
    snapshot_type TEXT NOT NULL,
    snapshot_date TEXT NOT NULL,
    kpi_current REAL,
    notes TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(goal_id, snapshot_type, snapshot_date)
);
