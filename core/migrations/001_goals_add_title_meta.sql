-- Migration 001: pm_goals 테이블에 title, meta_json, org_id(alias: created_by) 컬럼 추가
-- 기존 created_by 컬럼이 org_id 역할을 이미 수행하므로 인덱스만 추가.
-- title  : 목표 제목 (short label)
-- meta_json : 메타데이터 JSON (sprint, due_date, tags 등)
-- 실행 방법: sqlite3 ai_org.db < core/migrations/001_goals_add_title_meta.sql

-- title 컬럼 추가 (없으면)
-- SQLite는 IF NOT EXISTS를 ALTER TABLE에서 지원하지 않으므로
-- Python 마이그레이션 헬퍼(context_db.py _migrate_goals_schema)가 처리한다.

-- 아래는 참조용 DDL (실제 실행은 ContextDB._migrate_goals_schema에서 수행)
-- ALTER TABLE pm_goals ADD COLUMN title TEXT DEFAULT '';
-- ALTER TABLE pm_goals ADD COLUMN meta_json TEXT DEFAULT '{}';
-- CREATE INDEX IF NOT EXISTS idx_pm_goals_org ON pm_goals(created_by);
-- CREATE INDEX IF NOT EXISTS idx_pm_goals_active ON pm_goals(created_by, status);

SELECT 'Migration 001 reference DDL — applied via ContextDB._migrate_goals_schema()';
