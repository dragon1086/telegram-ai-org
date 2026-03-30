# RETRO-20 리서치실 최종 보고서
# 변수 교차 사전 가시화 — 레퍼런스·경쟁사 분석 및 ACTION 완료

> **연결 태스크**: RETRO-20 (L1 Active → resolved)
> **작성일**: 2026-03-29
> **메타데이터**: [research_context.yaml](./research_context.yaml)
> **연계 문서**: RETRO-14 ACTION 완료 문서, docs/RESEARCH_STANDARDS.md v1.1.0

---

## 배경

2026-W13 전 조직 회고에서 6개 부서 전원이 동일한 실패 패턴을 보고했다:

> **"기준은 세웠으나 변수 교차 맥락을 담지 못했다"**

리서치실의 구체 사례:
- `research_context.yaml` 필드 정의 완료 (RETRO-08)
- 그러나 조사 시점 + 모델 버전이 동시에 달라진 구간에서 결과 차이의 원인 이분 불가
- 어느 변수(조사 시점 vs 모델 버전)가 결과를 바꿨는지 사후 추적 불가능

팀 전체 ACTION으로 **"변수 교차 사전 가시화"** 가 수렴됨 → 리서치실 역할: 시장·레퍼런스·경쟁사 조사 결과를 출처 기반으로 구조화

---

## 조사 결과

### 1. 변수 의존성 가시화 도구/방법론

| # | 도구명 | 설명 | 적용 가능성 | 출처 |
|---|--------|------|------------|------|
| 1 | **Madge** | JS/TS 모듈 의존성 그래프. `--circular` 플래그로 사이클 탐지, DOT/SVG 시각화. | YAML 설정 파일 간 교차 참조 패턴 참고 | [github.com/pahen/madge](https://github.com/pahen/madge) (2024~) |
| 2 | **DVC DAG** | `dvc.yaml`에 stage/deps/outputs 선언 → DAG 자동 추론. `--mermaid`/`--dot` export. | research_context.yaml 간 의존성 선언 패턴으로 직접 적용 가능 | [dvc.org/doc/command-reference/dag](https://dvc.org/doc/command-reference/dag) (현행) |
| 3 | **DepsRAG** | 에이전트 기반 의존성 관리 AI. 지식 그래프(KG)로 의존성 구조화, 자연어 질의 → 그래프 쿼리 변환. | 멀티에이전트 환경 의존성 동적 조회 패턴 참고 | [arxiv.org/html/2405.20455v5](https://arxiv.org/html/2405.20455v5) (2024, arXiv) |
| 4 | **Multi-Agent DAG Orchestration** | 5단계 의존성 그래프 기반 오케스트레이션. 데이터 모델→TDD→UI→E2E 위상정렬 순서로 에이전트 스폰. | 리서치 산출물 생성 순서를 DAG로 표현하는 패턴 참고 | [gist.github.com/manu354/...](https://gist.github.com/manu354/79252161e2bd48d1cfefbd3aee7df1aa) (2024) |

**핵심 인사이트**: 업계 표준은 **YAML 선언 → DAG 자동 추론 → 시각화(DOT/Mermaid)** 파이프라인이다. `research_context.yaml`에 `dependencies` 필드를 추가하면 동일 패턴 적용 가능.

---

### 2. 순환참조 방지 패턴

| # | 패턴명 | 설명 | 우리 시스템 적용 | 출처 |
|---|--------|------|----------------|------|
| 1 | **DAG 구조적 강제** | 모든 의존성을 DAG로 모델링 → 구조적으로 순환참조 불가능. acyclic 속성이 무한루프를 구조적으로 차단. | design-baseline.yaml CIRC-001~004 패턴과 일치 (이미 적용 중) | [santanub.medium.com/directed-acyclic-graphs-...](https://santanub.medium.com/directed-acyclic-graphs-the-backbone-of-modern-multi-agent-ai-d9a0fe842780) (2025) |
| 2 | **Zuul 명시적 허용/차단** | CI/CD 파이프라인에서 cycle을 기본 차단, 필요 시 per-tenant 명시 활성화. 설정 기반 이분법. | orchestration.yaml에 `circular_dependency: deny` 필드 추가 권고 | [zuul-ci.org/docs/zuul/11.0.0/...](https://zuul-ci.org/docs/zuul/11.0.0/developer/specs/circular-dependencies.html) (Zuul 11.0) |
| 3 | **런타임 위상정렬 검증** | YAML 선언 → DAG 로드 → 위상정렬 실패 시 cycle로 판정, 실행 차단. DVC/Airflow 채용 패턴. | preflight_check.sh에 DAG 검증 단계 추가 가능 | [towardsdatascience.com/network-graphs-...](https://towardsdatascience.com/network-graphs-for-dependency-resolution-5327cffe650f/) |
| 4 | **Dynamic Cycle Rejection** | 실행 중 DAG 동적 재편성 시 cycle 생성 시도를 즉시 거부하는 validator 내장. | tools/orchestration_cli.py validate-config에 통합 가능 | [gocodeo.com/post/dependency-graphs-...](https://www.gocodeo.com/post/dependency-graphs-orchestration-and-control-flows-in-ai-agent-frameworks) (2025) |

---

### 3. 경쟁사·유사 시스템 분석

#### 대상: 멀티에이전트 조율 시스템 5개

| 시스템 | 변수/설정 관리 | Pre-flight 자동화 | 멀티에이전트 조율 패턴 | 출처·날짜 |
|--------|--------------|------------------|----------------------|---------|
| **AutoGen / MS Agent Framework** | 메시지 기반 독립 상태. Actor model 패턴. v1.0(2026 Q1 GA)에서 session-based 상태 + 타입 안전성 + 미들웨어 추가. | 공식 pre-flight 없음. Observability/telemetry로 실행 전 상태 검증. | 이벤트 드리븐 비동기. Graph-based workflow로 명시적 오케스트레이션. | [learn.microsoft.com/en-us/agent-framework/overview/](https://learn.microsoft.com/en-us/agent-framework/overview/) (2025~2026) |
| **CrewAI** | per-agent 메모리(단기 버퍼 + 장기 벡터). `memory=True`로 공유 메모리. YAML/JSON으로 agent·task 선언. | 명시적 없음. 2025년 Flows(event-driven state machine)가 가장 근접. | Crews + Flows: Sequential / Hierarchical / Custom. 2025 Flows로 상태머신 오케스트레이션 추가. | [docs.crewai.com/en/concepts/agents](https://docs.crewai.com/en/concepts/agents) / [markaicode.com/crewai-flows-...](https://markaicode.com/crewai-flows-event-driven-agent-orchestration/) (2025~2026) |
| **LangGraph** | 중앙화된 공유 TypedDict State. Reducer 함수로 충돌 없는 상태 업데이트. SqliteSaver/PostgresSaver checkpointing. | 공식 없음. Input validation 패턴 권장. LangGraph 1.0(2025-10) durable state + human-in-the-loop. | Graph 노드 간 conditional edge, parallel node, interrupt 지원. 2025-10 GA. | [langchain.com/langgraph](https://www.langchain.com/langgraph) / [sparkco.ai/blog/mastering-langgraph-...](https://sparkco.ai/blog/mastering-langgraph-state-management-in-2025) (2025) |
| **MetaGPT** | `~/.metagpt/config2.yaml` 단일 파일로 LLM 엔진·API 통합 관리. SOP를 prompt sequence에 인코딩. | AFlow (ICLR 2025 oral)로 워크플로 자동 생성 — 계획 단계 플로우 유효성 검증. | Assembly line: PM→Architect→PM→Engineer→QA 5역할 파이프라인. | [github.com/FoundationAgents/MetaGPT](https://github.com/FoundationAgents/MetaGPT) / [ibm.com/think/topics/metagpt](https://www.ibm.com/think/topics/metagpt) (2025) |
| **AgentVerse** | 고정 config 대신 evaluation 피드백으로 에이전트 풀 구성 동적 변경. 설정의 "변수" = 에이전트 조합 자체. | Expert Recruitment 단계(태스크 상태 기반 에이전트 자동 선발)가 실질적 pre-run 검증. | 4단계 사이클: Expert Recruitment → Collaborative Decision → Action → Evaluation → (반복). | [github.com/OpenBMB/AgentVerse](https://github.com/OpenBMB/AgentVerse) / [arxiv.org/abs/2308.10848](https://arxiv.org/abs/2308.10848) (ICLR 2024) |

#### 경쟁사 분석 차별화 포인트

| 항목 | 경쟁사 현황 | telegram-ai-org 현황 | 평가 |
|------|-----------|---------------------|------|
| **Pre-flight 자동화** | 5개 시스템 모두 명시적 pre-flight 없음 | `scripts/preflight_check.sh` + `conftest.py` E2E 헤더 자동 삽입 | ✅ **차별화 포인트** |
| **변수 교차 맥락** | LangGraph TypedDict로 상태 추적. 교차 구간 명시 설계는 미확인 | `research_context.yaml` `cross_variable_periods` 블록 (RETRO-20 신설) | ✅ **선도적 구현** |
| **설정 관리 방식** | MetaGPT 단일 YAML / AutoGen 메시지 상태 / CrewAI YAML+메모리 | `orchestration.yaml` + `infra-baseline.yaml` + `design-baseline.yaml` 3계층 분리 | ✅ **명시적 계층 분리로 차별화** |
| **순환참조 방지** | DAG 구조 강제(공통). 명시적 CIRC-001~004 규칙 보유 시스템은 미확인 | `design-baseline.yaml` CIRC-001~004 명시 | ✅ **명시적 규칙 문서화 우위** |

---

## 시사점

1. **Pre-flight 자동화는 업계 공백 영역**: 5개 주요 경쟁사 모두 공식 pre-flight 개념이 없다. 우리 시스템의 `preflight_check.sh` + E2E 헤더 패턴은 차별화 경쟁력이다.

2. **변수 교차 맥락 명시는 선도적 구현**: LangGraph는 TypedDict 상태 관리로 추적하나, 교차 구간을 명시적으로 기재하는 `cross_variable_periods` 블록은 경쟁사에서 확인되지 않았다.

3. **DAG + YAML 선언은 업계 표준**: DVC, Airflow, LangGraph 모두 YAML 선언 → DAG 추론 패턴을 사용한다. `orchestration.yaml`의 의존성을 DAG로 시각화하면 즉시 업계 표준 패턴에 부합한다.

4. **순환참조 방지 4규칙(CIRC-001~004)은 명시화 우위**: 경쟁사들은 구조적 DAG 강제에 의존하지만, 우리는 `design-baseline.yaml`에 명시적 규칙 4개를 문서화했다. 이 패턴을 오픈소스화하면 레퍼런스 구현이 될 수 있다.

---

## 권고사항

| 우선순위 | 권고 | 근거 | 담당 |
|---------|------|------|------|
| **P1** | `research_context.yaml`에 `dependencies` 필드 추가 — DVC DAG 패턴 적용 | 조사 산출물 간 의존성을 DAG로 선언, 변수 교차 구간 자동 식별 | 리서치실 |
| **P2** | `orchestration.yaml`에 `circular_dependency: deny` 필드 추가 | Zuul 명시적 허용/차단 패턴 채용 — 설정 기반 이분법 | 운영실/개발실 |
| **P3** | Pre-flight 자동화를 오픈소스 README에 차별화 포인트로 명시 | 경쟁사 5개 모두 미구현 — 마케팅 차별점 | 성장실/기획실 |
| **P4** | `tools/orchestration_cli.py validate-config`에 DAG 사이클 검증 추가 | 런타임 위상정렬 검증 패턴 (DVC/Airflow 공통 패턴) | 개발실 |

---

## 출처 목록

| # | 출처명 | URL | 날짜 |
|---|--------|-----|------|
| 1 | Madge - GitHub | https://github.com/pahen/madge | 2024~ (활성) |
| 2 | DVC DAG Command Reference | https://dvc.org/doc/command-reference/dag | 현행 |
| 3 | VS Code Dependency Graph Extension | https://marketplace.visualstudio.com/items?itemName=sz-p.dependencygraph | 현행 |
| 4 | DepsRAG - arXiv | https://arxiv.org/html/2405.20455v5 | 2024 |
| 5 | Multi-Agent DAG Orchestration Gist | https://gist.github.com/manu354/79252161e2bd48d1cfefbd3aee7df1aa | 2024 |
| 6 | DAGs: Backbone of Modern Multi-Agent AI | https://santanub.medium.com/directed-acyclic-graphs-the-backbone-of-modern-multi-agent-ai-d9a0fe842780 | 2025 |
| 7 | Zuul CI Circular Dependencies Spec | https://zuul-ci.org/docs/zuul/11.0.0/developer/specs/circular-dependencies.html | Zuul 11.0 |
| 8 | Network Graphs for Dependency Resolution | https://towardsdatascience.com/network-graphs-for-dependency-resolution-5327cffe650f/ | TDS |
| 9 | Dependency Graphs in AI Agent Frameworks | https://www.gocodeo.com/post/dependency-graphs-orchestration-and-control-flows-in-ai-agent-frameworks | 2025 |
| 10 | DAG-Plan - arXiv | https://arxiv.org/html/2406.09953 | 2024 |
| 11 | Microsoft Agent Framework Overview | https://learn.microsoft.com/en-us/agent-framework/overview/ | 2025~2026 |
| 12 | CrewAI Concepts - Agents | https://docs.crewai.com/en/concepts/agents | 2025~2026 |
| 13 | CrewAI Flows - Event-Driven Orchestration | https://markaicode.com/crewai-flows-event-driven-agent-orchestration/ | 2025~2026 |
| 14 | LangChain LangGraph Official | https://www.langchain.com/langgraph | 2025 |
| 15 | Mastering LangGraph State Management 2025 | https://sparkco.ai/blog/mastering-langgraph-state-management-in-2025 | 2025 |
| 16 | MetaGPT - GitHub | https://github.com/FoundationAgents/MetaGPT | 2025 |
| 17 | What is MetaGPT - IBM | https://www.ibm.com/think/topics/metagpt | 2025 |
| 18 | AgentVerse - GitHub | https://github.com/OpenBMB/AgentVerse | ICLR 2024 |
| 19 | AgentVerse - arXiv | https://arxiv.org/abs/2308.10848 | ICLR 2024 |

---

*Generated: 2026-03-29T(KST) | Model: claude-sonnet-4-5 | infra_baseline_version: v1.2.0*
*Linked: RETRO-20 (완료), RETRO-14 (완료) | See: research_context.yaml*
