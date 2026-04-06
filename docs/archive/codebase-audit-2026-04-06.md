# Codebase Audit — docs/ Directory Restructure
**Date**: 2026-04-06

## Summary

docs/ 루트에 50개 이상의 파일이 혼재하여 탐색성이 떨어지는 문제를 해결했다.

## Actions Taken

### Deleted (duplicates already in archive/)
- docs/G009-design-result-tracking.md
- docs/G009-FU-KR4-visual-guide.md
- docs/setup.sh_e2e_report.md
- docs/TEST_REPORT_PHASE3B.md
- docs/test_scope_phase3b.md

### Moved to docs/archive/
- 성능_비교.md, benchmark_results.md (벤치마크 산출물)
- e2e_setup_validation.md, phase1-test-coverage.md (테스트 아티팩트)
- ops-report-weekly-blocking-diagnosis.md (운영 세션 리포트)
- image_prompts.md, dashboard-tunnel-comparison.md (세션 산출물)
- PRD-README-OVERHAUL-v1.md (완료된 PRD)
- MEMORY_ARCHITECTURE_DESIGN_v1.md (설계 산출물, MEMORY_TIER_ARCHITECTURE.md로 대체)
- RELEASE_NOTES_v1.0.0.md, RELEASE_NOTES_v1.1.0.md (이력 보존)
- RETRO-06, RETRO-11-17-completion, RETRO-11, RETRO-12, RETRO-15, RETRO-17, RETRO-18 (x2), RETRO-20, RETRO-23, RETRO-33, RETRO-exit-code-143 (세션 회고 산출물)

### Moved to docs/guides/
- AUTONOMOUS_LOOP.md, async-blocking-fix-guide.md, CI_CD_SETUP.md
- design-baseline-guide.md, ENV_DEBUG_GUIDE.md, env_isolation_debug_guide.md
- INSTALL_FLOW.md, MEMORY_TIER_ARCHITECTURE.md, pre_flight_checklist.md
- SKILLS_MCP_GUIDE.md, OPS-ARCH-v1.md, OPS-CICD-v1.md, OPS-DEPLOY-v1.md
- OPS-RUNBOOK-v1.md, RESEARCH_STANDARDS.md

### Created
- docs/guides/ (새 디렉토리)
- docs/retro/ (새 디렉토리)
- docs/INDEX.md (디렉토리 구조 인덱스)

### Kept in docs/ root
- OPENSOURCE_PLAN.md, REFACTORING_PLAN.md, agent-coordination-map.md
- opensource_packaging_reference.md, GROWTH_OPENSOURCE_STRATEGY.md

## Link Impact
README.md: `docs/` 일반 참조만 있음 — 특정 파일 링크 없어 수정 불필요.
ARCHITECTURE.md: 파일 미존재.
