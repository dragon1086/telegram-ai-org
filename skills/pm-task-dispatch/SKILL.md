---
name: pm-task-dispatch
description: "Use when the PM bot receives a task and needs to route it to the right department bot. Analyzes task type and assigns to engineering/design/growth/ops/research/product. Triggers: 'pm dispatch', '업무배분', 'assign task', '태스크 배분', 'route task', when a new request needs to be delegated to a specialist bot"
---

# PM Task Dispatch (업무배분 스킬)

PM 봇이 수신된 태스크를 분석하고 가장 적합한 조직 봇에 배분하는 체계적 프로세스.

## 절차

### Step 1: 태스크 분석
태스크를 받으면 다음을 파악한다:
- **주요 영역**: 개발/디자인/성장/운영/연구/제품 중 하나 또는 복합
- **긴급도**: 즉시/오늘중/이번주
- **의존성**: 다른 봇의 산출물이 먼저 필요한지
- **예상 규모**: S(1-2h) / M(반나절) / L(하루+)

### Step 2: 봇 선정
```
태스크 유형 → 담당 봇 (예시 — 실제 org ID는 organizations.yaml 참조)
코드/API/버그  → 개발/엔지니어링 역할 조직
UI/UX/디자인   → 디자인 역할 조직
마케팅/지표    → 성장/마케팅 역할 조직
운영/인프라    → infra 역할 조직 (capabilities: [infra])
시장조사/분석  → 리서치 역할 조직
기획/PRD       → 제품/기획 역할 조직
복합 태스크    → 주담당 봇 + 협업 봇 명시
```

### Step 3: 배분 메시지 작성 (스코프 명시 필수)
```
[태스크 배분] #{태스크ID}
담당: @{봇이름}
내용: {태스크 설명}
긴급도: {즉시/오늘중/이번주}
기대 산출물: {구체적 결과물}
실행 범위: {이 봇이 해야 할 것만 명시 — 범위 외 작업은 별도 서브태스크}
협업 필요: {다른 봇 있으면 명시}
```

> **PM 스코프 원칙**: 각 봇은 배분받은 태스크의 "실행 범위"에 명시된 것만 수행한다.
> 범위에 없는 작업(재기동, push, merge 등)은 PM이 별도 태스크로 분리해 적절한 봇에 배분해야 한다.
> 봇 스스로 범위를 확장하지 않는다 — PM이 명확히 정의하는 것이 책임이다.

### Step 4: 진행 추적
- 배분 후 `orchestration.yaml` docs_root에 태스크 상태 기록
- 완료 예상 시간이 지나면 팔로업 메시지 전송
- 완료 보고 수신 시 Rocky에게 요약 전달

## 복합 태스크 처리
여러 봇이 필요한 태스크:
1. 의존성 그래프 분석
2. **자기파괴 작업 분리**: restart/deploy/reboot/재기동이 포함되면 반드시 별도 서브태스크로 분리
3. 병렬 실행 가능한 부분 식별
4. 순서대로 배분 (병렬 가능한 것은 동시 배분)

> ⚠️ 실행 주체와 kill 대상이 겹치는 작업은 절대 같은 태스크에 넣지 않는다.
> 예: engineering_bot이 코드 수정 + restart_bots.sh 실행 → 자기 자신 kill → 무한 루프

## Prerequisites

배분 대상이 코드 변경 또는 배포를 포함하는 경우, **quality-gate 스킬을 먼저 실행**하라.

```
적용 기준:
- 태스크가 코드 수정/버그픽스/기능 추가인 경우
- 배포(deploy) 또는 병합(merge)이 포함된 경우
- 개발실 봇에 배분하기 전 반드시 quality-gate 통과 확인

실행 순서:
1. quality-gate 스킬 실행 → PASS 확인
2. PASS 시에만 pm-task-dispatch Step 1 진행
3. FAIL 시 → 개발실에 수정 요청 후 재검사
```

> 이유: `.claude/settings.local.json` allowlist가 PreToolUse 훅을 무력화할 수 있으므로,
> 훅 대신 이 지침으로 quality-gate 실행을 보장한다.

## 스코프 분리 원칙 (글로벌 규칙)
각 봇은 자기 전문 영역의 일만 한다. PM이 위임할 때 이를 명시적으로 지정해야 한다.

| 작업 유형 | 담당 봇 | 다른 봇에서 요청 시 |
|-----------|---------|-------------------|
| 재기동 / restart | infra 역할 조직만 | COLLAB 요청 금지, PM이 별도 태스크 |
| git push / merge to main | infra 역할 조직만 | COLLAB 요청 금지, PM이 별도 태스크 |
| 코드 수정 / 버그 수정 | 개발/엔지니어링 역할 조직 | - |
| 시장조사 / 레퍼런스 | 리서치 역할 조직 | - |
| 배포 / 인프라 변경 | infra 역할 조직 | - |

> 봇별 프롬프트에 금지 문구를 박는 것보다, **PM이 위임 시 범위를 명확히 정하는 것**이 글로벌하게 작동한다.

## 안티패턴
- ❌ 모든 태스크를 개발실에만 배분
- ❌ 의존성 고려 없이 동시 배분
- ❌ quality-gate 없이 코드 변경 배분
- ❌ 코드 작업과 restart/deploy를 같은 태스크로 배분 (자기파괴 루프 위험)
- ❌ 실행 범위 없이 태스크 배분 → 봇이 임의로 범위 확장
- ✅ 태스크 성격에 맞는 봇 선정
- ✅ 배분 메시지에 "실행 범위" 항목 명시
- ✅ 명확한 기대 산출물 명시
- ✅ 코드/배포 태스크는 quality-gate 먼저
- ✅ restart/deploy는 ops_bot 별도 서브태스크 (코드 작업 의존성 설정)

## 신규 봇 온보딩 체크리스트

새 조직(봇)을 추가할 때 아래 항목을 반드시 확인한다:

- [ ] `organizations.yaml`에 등록 (capabilities 포함)
- [ ] `orchestration.yaml` → `global_instructions` 자동 적용 확인 (별도 per-org 스코프 문구 추가 불필요)
- [ ] `bots/{org_id}.yaml` 생성 (role, instruction, team_config 포함)
- [ ] `CLAUDE.md`/`AGENTS.md` PM 스코프 원칙 인지 확인 (공통 파일 자동 적용)
- [ ] infra 역할 여부 결정 (capabilities: [infra] → push/restart/deploy 가능)
- [ ] 배분 메시지에 "실행 범위" 항목 포함 여부 확인

> 글로벌 스코프 원칙(`orchestration.yaml` → `global_instructions`)은 신규 봇에도 자동 적용된다.
> per-org 재기동 금지 문구나 개별 예외 규칙을 추가하지 않는다 — 과적합 위험.
