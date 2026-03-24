-- Migration 001: pm_goals 테이블에 org_id, title, meta_json 컬럼 추가
-- GoalTracker.start_goal(org_id, title, description, meta) API 지원을 위한 스키마 확장.
-- SQLite는 IF NOT EXISTS가 없으므로 Python 레이어에서 OperationalError("duplicate column") 무시 처리.

ALTER TABLE pm_goals ADD COLUMN org_id TEXT DEFAULT 'pm';
ALTER TABLE pm_goals ADD COLUMN title TEXT DEFAULT '';
ALTER TABLE pm_goals ADD COLUMN meta_json TEXT DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_pm_goals_org ON pm_goals(org_id);
