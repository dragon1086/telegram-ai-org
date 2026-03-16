# implementation

## Request
telegram-ai-org리파지토리의 설계(알고리즘이나 프로그램적인 요소(파이프라인, 인프라 등)와 LLM의 요소(프롬프트, skill, mcp 등)을 깔끔하게 만들어서 알려줘. gemini의 나노바나나2로 이미지를 만들어서 첨부해도 좋고 다이어그램이나 설계 시각화 도구를 이용해서 만들어 첨부해도 좋아

## Note
설계 공유 완료, implementation phase로 이동

## Implementation result
- at: 2026-03-16T05:00:36.329677+00:00

[TEAM:solo]

두 다이어그램 생성 완료. 핵심 설계를 정리합니다.

---

## telegram-ai-org 아키텍처 요약

### 📊 다이어그램 1: 메시지 플로우 파이프라인

**프로그래밍 레이어**

```
Telegram → main.py (TelegramRelay) → on_message()
    ├─ direct_reply     → 즉시 응답
    ├─ local_execution  → tmux Claude Code 세션
    └─ delegate         → 부서 봇 위임
              ↓
    pm_orchestrator.py
    plan_request() → RequestPlan → dispatch()
              ↓
    session_manager.py
    tmux send-keys → Claude Code CLI → response capture
              ↓
    .ai-org/runs/state.json + orchestration.yaml
```

---

### 🤖 다이어그램 2: LLM 레이어

| 요소 | 구성 |
|------|------|
| **Classification LLM** | Gemini → OpenAI → Anthropic → DeepSeek (폴백 체인) |
| **System Prompt** | Bot YAML + `~/.claude/agents/` 동적 로드 + `agent_hints.yaml` + `CLAUDE.md` |
| **Team Strategy** | `detect_strategy()` → omc(MCP) / native(실험) / solo |
| **Agent Catalog** | planner, architect, executor, debugger, analyst, designer, writer, verifier |
| **Phase Pipeline** | intake → planning → design → implementation → verification → feedback |
| **부서 봇** | PM / Research / Engineering / Product / Design / Growth / Ops |

---

### 핵심 설계 특징

1. **이중 레이어 분리**: 프로그래밍 파이프라인(Python async + tmux)과 LLM 레이어(agent/skill/MCP)가 명확히 분리
2. **파일시스템 기반 상태**: DB 없이 `.ai-org/runs/` 디렉토리로 런 상태 관리
3. **동적 팀 구성**: YAML 설정으로 각 봇의 preferred_agents/skills 선언, 런타임에 전략 자동 감지
4. **폴백 체인**: LLM confidence scoring도 Gemini 우선 → 순차 폴백

저장 경로:
- `docs/arch-pipeline.png` — 파이프라인
- `docs/arch-llm.png` — LLM 레이어
