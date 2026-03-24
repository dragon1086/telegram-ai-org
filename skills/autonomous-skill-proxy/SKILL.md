---
name: autonomous-skill-proxy
description: "Use when a coding agent running autonomously (--dangerously-skip-permissions) encounters an interactive skill that requires user input and would block execution. Triggers: '자율모드', 'autonomous mode', 'skip interactive', 'non-interactive skill', when AUTONOMOUS_MODE=true is set"
allowed-tools: Read
---

# Autonomous Skill Proxy (자율 스킬 프록시)

## 목적
`--dangerously-skip-permissions`로 실행되는 자율 에이전트가 인터랙티브 스킬(brainstorming, deep-interview 등)을 호출할 때, 사용자 입력 없이 자동으로 응답하는 패턴을 정의한다.

## 핵심 원칙
1. **컨텍스트 자동 수집**: AskUserQuestion 대신 현재 태스크 컨텍스트, 관련 파일, 이전 토론 내용에서 답변을 추론한다.
2. **LLM 위임**: 응답이 불분명할 때는 PM 봇 또는 orchestrator LLM이 대신 응답한다.
3. **단호한 진행**: 추가 정보가 없어도 "합리적 기본값"으로 진행한다. 완벽보다 진행이 우선.

## 자율 응답 규칙 (AUTONOMOUS_MODE)

환경변수 `AUTONOMOUS_MODE=true` 또는 실행 플래그 `--autonomous`가 있을 때:

### brainstorming 스킬
- **"Explore project context"**: CLAUDE.md, AGENTS.md, README.md 자동 읽기
- **"Ask clarifying questions"**: 질문 대신 현재 태스크 설명에서 목적/제약/성공기준 추론
- **"Propose 2-3 approaches"**: 컨텍스트 기반 자동 제안 (사용자 승인 없이 진행)
- **"User approves design?"**: AUTONOMOUS_MODE에서는 자동 승인 후 진행

### deep-interview 스킬
- 인터뷰 질문들을 태스크 컨텍스트로 자동 답변
- 빈 필드는 "TBD (자율모드에서 생략)" 표시

### ralplan/omc-plan (--interactive 없는 경우)
- 이미 비인터랙티브 — 정상 진행

## 구현 방법

### 방법 1: Non-interactive 래퍼 스킬 (권장)
인터랙티브 스킬 대신 자율 실행 가능한 대체 스킬을 사용한다:
- `brainstorming` → `pm-discussion` (비인터랙티브)
- `deep-interview` → 태스크 브리프 직접 작성

### 방법 2: PM 봇 프록시 응답
코딩에이전트가 인터랙티브 프롬프트에 막혔을 때:
1. PM 봇에게 질문을 포워딩
2. PM 봇이 LLM으로 자동 응답 생성
3. 응답을 코딩에이전트에 주입

### 방법 3: 환경변수 기반 자동 응답
```bash
# 자율 모드로 실행
AUTONOMOUS_MODE=true claude --dangerously-skip-permissions "task..."
```
에이전트는 AUTONOMOUS_MODE를 감지하면:
- AskUserQuestion 호출 전에 컨텍스트에서 답변 생성
- 불확실하면 "자율모드: [합리적 기본값 사용]" 로그 후 진행

## organizations.yaml 설정
각 조직 봇의 `team` 섹션에 추가:
```yaml
team:
  autonomous_skill_mode: true   # 인터랙티브 스킬 자동 응답 활성화
  skill_proxy: pm_bot           # 응답 생성에 사용할 프록시 봇
  preferred_skills:
    - brainstorming-auto        # 인터랙티브 대신 자율 버전 사용
```

## 안티패턴
- ❌ 인터랙티브 스킬을 그대로 호출하고 막히는 것
- ❌ 사용자 입력을 기다리며 무한정 멈추는 것
- ✅ 컨텍스트 기반 자동 응답 후 진행
- ✅ 불확실하면 합리적 기본값으로 진행하고 로그 남기기
