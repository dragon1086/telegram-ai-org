# 2026-03-21 트렌드 관측 & 전략 포지셔닝

## 1. 트렌드 정리 — 지금 무슨 일이 일어나고 있나

### 1-A. 원격 제어 코딩 에이전트의 확산

| 움직임 | 사례 |
|--------|------|
| 클라우드 채널 원격 제어 | Claude Code 공식 채널 API, Codex CLI remote, Gemini CLI |
| 메시지 플랫폼 연동 | Telegram/Discord/Slack → 에이전트 원격 트리거 |
| 다중 엔진 오케스트레이션 | everything-claude-code (.claude, .codex, .cursor, .opencode 동시 지원) |

**핵심 관찰**: "원격 + 다엔진"은 이제 당연한 기본값으로 수렴 중. 개별 에이전트 수준의 혁신보다 **조율 레이어**가 차별점이 됨.

### 1-B. 하네스(Harness) 트렌드

- **everything-claude-code** (92.6k stars): 28개 전문 서브에이전트 + 스킬 라이브러리 + 멀티엔진 지원. 개인 개발자의 코딩 워크플로 최적화가 목적. `continuous-learning-v2` (instinct 기반, 신뢰도 점수) 포함.
- 방향성: CLAUDE.md + skills/ + agents/ 트리오가 사실상 표준 구조로 굳어지는 중.

### 1-C. Auto-Research / Auto-Improve 트렌드

**Karpathy 패턴** (autoresearch, 47.2k stars):
```
가설 제시 → 실험 실행 → 점수 측정 → 개선이면 keep / 퇴보면 revert → 반복
```
- ML 학습 실험이 원조. git commit = 실험 기록.

**파생 적용 사례**:
- **autoresearch-skill** (402 stars): SKILL.md 자동 개선에 적용. eval-guide.md로 평가 기준 정의.
- **autoimprove-cc** (44 stars): Claude Code native. `/autoimprove skills/my-skill --max-loops 50`. eval.json 스키마 + skill-optimizer 에이전트.
- **auto-researchtrading** (384 stars): 거래 전략(strategy.py) 자동 개선. backtest 점수가 측정 기준.

**핵심 인사이트**: Karpathy 패턴은 **정량 측정 가능한 어떤 것에도 적용 가능**하다. 스킬, 봇 라우팅, 봇 성격 전부 대상이 될 수 있다.

---

## 2. 우리 프로젝트의 현재 강점

### 경쟁자가 없는 영역

| 강점 | 상세 |
|------|------|
| **진짜 조직 구조** | PM → 부서 라우팅 → 전문 봇. 단순 에이전트 목록이 아닌 계층 조직 |
| **봇 정체성과 진화** | `bot_character_evolution.py`, `agent_persona_memory.py` — 봇마다 성격·기억·성장 |
| **사회적 동학** | `shoutout_system.py`, `collaboration_tracker.py` — 봇들 간 협업/칭찬 |
| **Telegram-native 오피스** | 원격 제어가 목적이 아닌 UI. 채팅방이 곧 오피스 |
| **스킬 생태계** | 20개+ 도메인 스킬 (pm-task-dispatch, retro, harness-audit, skill-evolve 등) |
| **OMC 하네스 통합** | ralph, ultrawork, ultraqa, subagent 라우팅 이미 장착 |
| **cokac-bot + openclaw-bot 협업** | 두 코드 에이전트가 메시지 채널로 실시간 협업 |

### 외부에서 보기 어려운 진짜 차별점

- everything-claude-code는 **개인 개발자 최적화**가 목적. 조직 운영 개념이 없다.
- 원격 제어 에이전트들은 단일 에이전트에 Telegram 채널만 붙인 수준이 대부분.
- 우리는 **조직 내 봇들이 서로를 알고, 성장하고, 칭찬하는** 사회적 레이어가 있다.

---

## 3. 우리가 채워야 할 갭 (우선순위 순)

### Gap 1: Auto-Improve 루프 없음 (HIGH)

- `skill-evolve` 스킬이 있지만 **수동 실행**. 밤새 자동으로 돌지 않는다.
- 각 스킬에 **eval.json이 없다** → 정량적 개선 판단 불가.
- autoimprove-cc 패턴을 그대로 이식 가능. 우리 `skill-evolve`를 eval 기반으로 업그레이드하면 된다.

### Gap 2: PM 라우팅 자동 실험 없음 (HIGH)

- Karpathy 패턴의 핵심 = "측정 기준이 있으면 어디든 적용". PM 라우팅 정확도가 측정 기준.
- 현재: 라우팅 규칙은 수동 작성, 결과 로그만 쌓임.
- 할 것: `routing rule 수정 → 테스트 케이스 실행 → accuracy 점수 → keep/revert` 루프.

### Gap 3: 봇 성능 eval 프레임워크 없음 (MEDIUM)

- `performance-eval` 스킬이 있지만 **자동화 아님**. 수동으로 불러야 실행.
- 각 봇에 정량 KPI (응답 품질, 태스크 완료율, 협업 점수) 정의가 안 되어 있다.

### Gap 4: 멀티엔진 공식 통합 (MEDIUM)

- Codex CLI, Gemini CLI를 봇 엔진으로 공식 지원 필요.
- 현재는 OMC 레벨에서 `/ask codex`로 쓰지만, 특정 봇이 Codex-native로 돌도록 `bots/*.yaml`에 통합 안 됨.
- everything-claude-code처럼 `.codex/`, `.opencode/` 지원 구조 추가 가능.

---

## 4. 구체적 액션 플랜

### Phase 1: Auto-Skill-Improve (즉시 착수 가능)

```
목표: 우리 20+ 스킬이 밤새 자동으로 개선되는 루프

1. eval/schema.json 정의 (autoimprove-cc 참고)
2. 핵심 스킬 5개에 eval/eval.json 추가
   - pm-task-dispatch, weekly-review, engineering-review, bot-triage, quality-gate
3. skill-evolve 스킬을 eval 기반으로 업그레이드
4. cron 또는 ralph 루프로 야간 자동 실행
   - /skill-evolve → eval → score → keep/revert → 다음 스킬
```

### Phase 2: PM 라우팅 Auto-Research (2~3주)

```
목표: PM 라우팅 정확도를 자동 실험으로 개선

1. 라우팅 테스트 케이스 셋 구축 (태스크 샘플 50개 + 정답 봇)
2. 라우팅 accuracy 스코어러 작성
3. /autoresearch-routing 커맨드:
   - nl_classifier.py 파라미터 조정 → 테스트 실행 → 점수 비교 → keep/revert
4. git commit = 실험 기록 (auto-researchtrading 패턴 그대로)
```

### Phase 3: 봇 KPI 자동 평가 (1개월)

```
목표: 봇마다 주간 자동 성과 측정 + 개선 제안

1. 봇별 KPI 정의 (YAML에 metrics 섹션 추가)
2. performance-eval을 weekly-review에 자동 연결
3. 낮은 점수 봇 → 자동으로 bot-triage + 개선 루프 트리거
```

---

## 5. 포지셔닝 결론

### 우리가 이미 이기고 있는 것
- 조직 구조 + 사회적 동학 레이어: 아무도 여기까지 안 왔다.
- Telegram-native 멀티봇 오피스: 원격 제어 붙인 단일 에이전트들과 차원이 다름.

### 우리가 당장 따라잡아야 할 것
- **Auto-improve 루프**: Karpathy 패턴을 우리 스킬/라우팅에 적용. 이건 지금 바로 할 수 있다.

### 우리만의 킬러 버전
- Karpathy 패턴 + 조직 구조를 결합한 **"자기진화형 AI 조직"**:
  - 스킬이 스스로 개선되고
  - 라우팅이 스스로 최적화되고
  - 봇 캐릭터가 성과 기반으로 진화하고
  - 팀워크 패턴이 데이터로 학습된다
- 이게 완성되면 everything-claude-code는 개인 도구, 우리는 **자율 조직 플랫폼**.

---

## 참고 소스

| 이름 | Stars | 핵심 기여 |
|------|-------|-----------|
| everything-claude-code | 92.6k | 멀티엔진 하네스, 28 에이전트, continuous-learning-v2 |
| karpathy/autoresearch | 47.2k | 실험-평가-반복 루프 원조 패턴 |
| autoresearch-skill | 402 | SKILL.md eval 기준 정의 방법 |
| autoimprove-cc | 44 | Claude Code native auto-improve 구현 참고 |
| auto-researchtrading | 384 | 도메인 특화 Karpathy 루프 (backtest → score → git) |
