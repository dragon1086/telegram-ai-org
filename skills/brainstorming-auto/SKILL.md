---
name: brainstorming-auto
description: "Use instead of brainstorming when running in autonomous mode with no human available to answer clarifying questions. Produces design docs without user approval gates. Triggers: 'auto design', '자동 설계', 'autonomous brainstorm', 'brainstorm without user', when brainstorming is needed in a headless/automated context"
allowed-tools: Read, Write, Glob, Grep
---

# Brainstorming Auto (자율 브레인스토밍)

brainstorming 스킬의 비인터랙티브 버전. 자율 에이전트가 사용자 입력 없이 설계 문서를 생성한다.

## 절차 (모두 자동, 사용자 입력 없음)

1. **컨텍스트 수집** (자동)
   - CLAUDE.md, AGENTS.md, README.md, 관련 코어 파일 읽기
   - 현재 태스크 설명에서 목적/제약/성공기준 추출

2. **설계 방안 자동 제안** (3개)
   - 컨텍스트 기반으로 3가지 접근법 생성
   - 각 방안의 장단점 자동 분석
   - 권장 방안 선택 (근거 포함)

3. **설계 문서 자동 작성**
   - `docs/plans/YYYY-MM-DD-<topic>-design.md` 저장
   - 사용자 승인 없이 진행

4. **구현 계획 자동 생성**
   - 태스크를 prd.json 스토리로 분해
   - 바로 실행 가능한 상태로 전환

## 사용법
```
/brainstorming-auto "설계할 기능 설명"
```
또는 자율 에이전트가 brainstorming이 필요한 상황에서 이 스킬을 대신 사용.
