-- Migration 002: OKR 계층 지원 컬럼 추가
-- Idempotent: context_db._migrate_okr_schema()에서 try/except로 처리

ALTER TABLE pm_goals ADD COLUMN goal_type TEXT DEFAULT 'task';
ALTER TABLE pm_goals ADD COLUMN parent_goal_id TEXT;
ALTER TABLE pm_goals ADD COLUMN deadline TEXT;
ALTER TABLE pm_goals ADD COLUMN check_interval TEXT DEFAULT 'daily';
ALTER TABLE pm_goals ADD COLUMN kpi_metric TEXT;
ALTER TABLE pm_goals ADD COLUMN kpi_target REAL;
ALTER TABLE pm_goals ADD COLUMN kpi_current REAL;
ALTER TABLE pm_goals ADD COLUMN kpi_unit TEXT;
ALTER TABLE pm_goals ADD COLUMN progress REAL DEFAULT 0;
ALTER TABLE pm_goals ADD COLUMN weight REAL;
ALTER TABLE pm_goals ADD COLUMN rolled_over_from TEXT;
ALTER TABLE pm_goals ADD COLUMN rollover_count INTEGER DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_goals_parent ON pm_goals(parent_goal_id);
CREATE INDEX IF NOT EXISTS idx_goals_type ON pm_goals(goal_type);
CREATE INDEX IF NOT EXISTS idx_goals_deadline ON pm_goals(deadline);
CREATE INDEX IF NOT EXISTS idx_goals_type_status ON pm_goals(goal_type, status);
