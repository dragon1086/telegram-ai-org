# Agent Coordination Map — 태스크 유형별 봇 라우팅 플로우

> 최종 업데이트: 2026-03-24  
> 이 문서는 PM 봇이 태스크를 어떤 조직에 배분할지 결정하는 기준을 정리한다.

## 라우팅 원칙

```
사용자 메시지
    │
    ▼
[PM 봇 수신]
    │
    ├─ 직접 답변 가능? (인사/질문/안내) ──► PM 직접 답변
    │
    ├─ 단일 조직 작업? ──────────────────► 해당 조직 단독 위임
    │
    ├─ 복합 태스크? ─────────────────────► 태스크 분해 → 병렬 위임
    │
    └─ 장기 목표? ───────────────────────► GoalTracker 루프 시작
```

## 조직별 전문 분야

| 조직 | 전문 분야 | 트리거 키워드 |
|------|-----------|---------------|
| `engineering_bot` | 코딩, 버그수정, API 구현, 리팩토링 | 구현, 코드, 버그, 수정, 테스트 |
| `product_bot` | 기획, PRD, 요구사항 분석, 로드맵 | 기획, 요구사항, PRD, 로드맵, 스펙 |
| `design_bot` | UI/UX, 와이어프레임, 디자인 시스템 | 디자인, UI, UX, 와이어프레임 |
| `research_bot` | 시장조사, 경쟁사 분석, 문서 요약 | 조사, 분석, 레퍼런스, 경쟁사 |
| `growth_bot` | 성장 전략, 마케팅, 지표 분석 | 성장, 마케팅, 지표, 퍼널 |
| `ops_bot` | 배포, 인프라, 모니터링, 재기동 | 배포, 인프라, 재기동, 운영 |

## 태스크 유형 → 라우팅 매트릭스

| 태스크 유형 | 기본 담당 | COLLAB 가능 |
|-------------|-----------|-------------|
| 조사 🔍 | research_bot | product_bot |
| 분석 📊 | research_bot / growth_bot | product_bot |
| 기획 📋 | product_bot | PM 직접 |
| 설계 🏗️ | engineering_bot + design_bot | product_bot |
| 검토 👀 | engineering_bot | ops_bot |
| 수정 🔧 | engineering_bot | ops_bot |
| 구현 💻 | engineering_bot | ops_bot |
| 운영 ⚙️ | ops_bot | engineering_bot |

## GoalTracker 루프 (장기 목표)

```
목표 설정 (사용자 메시지 또는 첨부파일)
    │
    ▼
GoalTracker.start_goal()
    │
    ▼
[Loop: idle → evaluate → replan → dispatch → idle]
    │
    ├─ evaluate: LLM이 진행도 평가 (0~100%)
    │
    ├─ not done → replan: 남은 작업 분해
    │
    ├─ dispatch: 각 조직에 서브태스크 배분
    │
    └─ done → 최종 보고 → 루프 종료
```

**활성화**: `ENABLE_GOAL_TRACKER=1` (.env)  
**최대 반복**: `GOAL_TRACKER_MAX_ITERATIONS` (기본 10)  
**폴링 간격**: `GOAL_TRACKER_POLL_INTERVAL_SEC` (기본 60초)

## 첨부파일 라우팅

```
첨부파일 수신
    │
    ├─ 목표 문서 (HTML/MD/PDF) ──► GoalTracker 시작 [권장]
    ├─ 코드 파일 ────────────────► engineering_bot
    ├─ 디자인 파일 ──────────────► design_bot
    └─ 데이터 파일 ──────────────► research_bot / growth_bot
```

> **현재 상태**: 첨부파일은 항상 `_execute_task` 직접 실행 경로를 탐. 
> GoalTracker 연동은 향후 개선 과제 (`_process_attachment_bundle` 수정 필요).

## 관련 문서
- `docs/harness-upgrade-prd.md` — 하네스 업그레이드 전체 로드맵
- `core/goal_tracker.py` — GoalTracker 구현
- `skills/pm-task-dispatch/SKILL.md` — PM 배분 스킬
