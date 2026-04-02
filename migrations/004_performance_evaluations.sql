-- Migration 004: 성과 평가 테이블

CREATE TABLE IF NOT EXISTS performance_evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dept_id TEXT NOT NULL,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    period_type TEXT NOT NULL,
    overall_score REAL,
    grade TEXT,
    criteria_scores TEXT DEFAULT '{}',
    strengths TEXT DEFAULT '[]',
    weaknesses TEXT DEFAULT '[]',
    prompt_fragment TEXT,
    created_at TEXT NOT NULL
);
