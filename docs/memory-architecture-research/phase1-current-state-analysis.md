---
title: Phase 1 — 현황 한계 분석 보고서
type: research
project: telegram-ai-org
date: 2026-03-22
author: aiorg_research_bot (PM)
tags: [memory, architecture, analysis, phase1]
---

# Phase 1: 현황 한계 분석 보고서

## 1. 현재 메모리 저장 구조 개요

telegram-ai-org 프로젝트는 **두 겹의 마크다운 기반 메모리**를 운영 중이다.

### 1-A. Claude Code 프로젝트 메모리 (MEMORY.md 인덱스)
- 위치: `~/.claude/projects/-Users-rocky-telegram-ai-org/memory/`
- 구성: MEMORY.md (인덱스) + 개별 .md 파일 (3개)
  - `project_pending_tasks.md` — 미완료 작업 목록
  - `project_skills_strategy.md` — 스킬 전략
  - `feedback_production_data.md` — 운영 피드백/규칙
- 참조 방식: MEMORY.md에 `[파일명](파일명) — 한 줄 설명` 형태의 단순 링크

### 1-B. MemoryManager 3계층 시스템 (런타임 메모리)
- 위치: `~/.ai-org/memory/{scope}.md`
- 구성: CORE / SUMMARY / LOG 3섹션이 단일 .md 파일 내 구분
  - CORE: importance 9-10, 항상 프롬프트 주입, 수동 관리
  - SUMMARY: importance 5-8, LLM 자동 요약
  - LOG: 최근 30개 유지, 자동 채점
- 검색: BM25 키워드 검색 (rank_bm25) + keyword fallback
- 연결: conversation_messages DB (SQLite) 와 분리된 조회

### 1-C. 기타 저장소
- `ai_org.db` / `context.db` — SQLite (스키마 불명, 대화 이력 추정)
- `data/tasks.db` — 태스크 상태

---

## 2. 한계점 목록 및 실사례 매핑

### 한계 #1: 크로스-파일 관계 표현 불가
**설명**: 파일 간 의미론적 연결이 없다. "project_pending_tasks.md의 ACT-5"가 "project_skills_strategy.md의 quality-gate 스킬"과 연관됨을 시스템이 알 수 없다.

**실사례**:
- MEMORY.md의 파일 간 링크는 단순 hyperlink뿐 — "이 작업은 저 피드백에서 파생됨"을 표현하는 필드 없음
- `project_pending_tasks.md`의 "ACT-5 SharedMemory 캐시"와 `shared_memory.py` 코드 사이의 구현 연결 추적 불가
- 태스크 완료 여부(tasks.db)와 메모리 항목(memory.md) 사이 자동 동기화 없음

### 한계 #2: 메타데이터 부재로 인한 필터링 불가
**설명**: 각 메모리 파일에 타입, 우선순위, 작성자, 연관 봇 등의 구조화 메타데이터가 없다. (project_pending_tasks.md에 YAML frontmatter가 부분적으로 존재하나 쿼리에 활용되지 않음)

**실사례**:
- "엔지니어링 봇 관련 메모리만" 또는 "2026-03-19 이후 생성된 결정사항만" 필터링 불가
- `feedback_production_data.md`의 규칙이 어느 봇에게 적용되는지 메타데이터로 표현되지 않음
- CORE/SUMMARY/LOG의 importance 점수는 있으나, 도메인 분류(기술/운영/전략), 관련 봇 등의 다차원 필터링 불가

### 한계 #3: 시간축/버전 관리 미흡
**설명**: "언제 배운 사실인가"와 "그 사실이 지금도 유효한가"를 추적할 수 없다.

**실사례**:
- `project_pending_tasks.md` 상단에 "(2026-03-19 기준)"이라는 단순 날짜 주석만 있음
- Claude Code는 메모리 파일 읽을 때 자동으로 "(This memory is 3 days old)" 경고를 붙임 — 시스템이 staleness를 인식하나 메모리 자체가 유효기간을 갖지 못함
- ACT-5 완료 기록이 있지만, 추후 해당 기능이 변경되거나 롤백되어도 메모리가 업데이트될 메커니즘 없음
- LOG 최대 30개 제한 — 오래된 중요 사실이 밀려남

### 한계 #4: 의미적 유사도 검색 불가
**설명**: BM25는 키워드 빈도 기반이다. "SharedMemory 캐시 구현"으로 검색하면 "인메모리 저장 레이어 ACT-5"를 찾지 못할 수 있다.

**실사례**:
- MemoryManager.search_memories()가 BM25 → keyword fallback 구조 — 동의어, 약어, 관련 개념 검색 불가
- "봇 재기동"을 물어보면 "request_restart.sh" 관련 메모리가 아닌 "봇" 키워드가 많은 문서가 상위에 옴
- CLAUDE.md/MEMORY.md는 LLM이 컨텍스트에 통째로 로드해야 내용을 파악 — 토큰 낭비

### 한계 #5: 구조적 단절 — 런타임 메모리 vs Claude Code 메모리
**설명**: MemoryManager(.ai-org/memory/)와 CLAUDE Code 프로젝트 메모리(MEMORY.md)가 완전히 분리된 사일로다.

**실사례**:
- PM 봇이 runtime에 배운 사실(MemoryManager)이 다음 Claude Code 세션에 반영되지 않음
- 두 시스템 간 "봇 재기동 금지" 규칙이 feedback_production_data.md에만 있고, MemoryManager CORE에는 없음
- 메모리 조회 시 두 시스템을 각각 확인해야 하는 운영 부담

### 한계 #6: 데이터-지식 연결 불가
**설명**: tasks.db, context.db 등 SQLite DB의 이력 데이터와 메모리 파일이 연결되지 않는다.

**실사례**:
- 태스크 T-260 완료가 tasks.db에 기록되지만, 그 태스크에서 배운 "SharedMemory 캐시 패턴"은 메모리.md에 별도 수동 기록 필요
- 태스크 성공률(tasks.db) 데이터와 "해당 봇의 강점/약점 지식"(메모리) 자동 연결 없음

### 한계 #7: 확장성 한계
**설명**: 현재 3개 메모리 파일, 30개 LOG가 한계지만, 운영이 성장하면 더 많은 봇·더 많은 프로젝트 맥락이 필요하다.

**실사례**:
- skills/README.md에 13개 스킬이 나열되지만, 각 스킬과 연관된 성공/실패 사례가 메모리에 구조적으로 쌓이지 않음
- 6개 봇(pm/research/engineering/design/growth/ops) 간 공유 지식 vs 봇별 전용 지식 분리 구조 없음

---

## 3. 요구사항 정의서 — 해결해야 할 핵심 문제 7개

| # | 요구사항 | 우선순위 | 현재 한계 연결 |
|---|---------|---------|--------------|
| R1 | **관계 표현**: 메모리 항목 간 "파생됨", "구현됨", "충돌함" 등 의미론적 관계 저장 | P0 | 한계 #1 |
| R2 | **다차원 메타데이터 필터링**: 봇/도메인/날짜/우선순위/상태 기반 쿼리 | P0 | 한계 #2 |
| R3 | **시간 유효성 관리**: 메모리 항목별 유효기간, 버전, 업데이트 이력 추적 | P1 | 한계 #3 |
| R4 | **의미적 유사도 검색**: 동의어·관련 개념 포함 시맨틱 검색 | P1 | 한계 #4 |
| R5 | **단일 메모리 레이어**: 런타임 메모리 ↔ Claude Code 메모리 통합 | P1 | 한계 #5 |
| R6 | **데이터-지식 자동 연결**: 태스크/대화 이력에서 지식 자동 추출·저장 | P2 | 한계 #6 |
| R7 | **경량 운영**: 로컬 환경에서 외부 API 없이 운영 가능, 저용량 | P2 | 한계 #7 |
