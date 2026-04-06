# Skills & MCP 표준 구조 가이드

> **목적**: telegram-ai-org에서 Skills와 MCP를 체계적으로 추가·관리하는 표준 절차를 정의한다.
> **참조**: `skills/create-skill/SKILL.md` — 개별 스킬 제작 가이드 (더 상세)

---

## 1. Skills 표준 구조

### 디렉토리 레이아웃

```
skills/
├── README.md                    # 스킬 인덱스 (자동화 트리거 목록)
├── _shared/                     # 공통 유틸리티
│   └── save-log.py              # 실행 로그 저장 헬퍼
│
├── {skill-name}/                # 개별 스킬
│   ├── SKILL.md                 # 필수: frontmatter + 실행 절차
│   ├── gotchas.md               # 권장: 실제 인시던트 기반 엣지케이스
│   ├── templates/               # 선택: 출력 템플릿
│   │   └── report-template.md
│   ├── references/              # 선택: 참조 문서 (라우팅 테이블, API 스펙)
│   │   └── example-ref.md
│   └── scripts/                 # 선택: 스킬 전용 자동화 스크립트
│       └── validate.sh
```

### 심볼릭 링크 구조 (Claude Code 연동)

```
.claude/
└── skills/                      # Claude Code가 로드하는 스킬 디렉토리
    ├── {skill-name} -> ../../skills/{skill-name}/   # 심볼릭 링크
    └── ...
```

### 새 스킬 추가 절차

```bash
# 1. 스킬 디렉토리 생성
mkdir -p skills/{skill-name}

# 2. SKILL.md 작성 (frontmatter 필수)
cat > skills/{skill-name}/SKILL.md << 'EOF'
---
name: {skill-name}
description: "{한 줄 설명}. Triggers: '{트리거1}', '{트리거2}'"
---
# {스킬 제목}
...
EOF

# 3. Claude Code 심볼릭 링크 생성
ln -sf ../../skills/{skill-name}/ .claude/skills/{skill-name}

# 4. organizations.yaml 등록
# common_skills 또는 해당 봇 preferred_skills에 추가

# 5. skills/README.md 업데이트
```

### SKILL.md frontmatter 필수 필드

```yaml
---
name: skill-name           # 슬래시 커맨드 이름 (kebab-case)
description: "..."         # Claude 자동 매칭용 설명 + Triggers 포함
# 선택 필드:
disable-model-invocation: true   # 수동 호출만 허용
context: fork              # 서브에이전트로 실행
agent: Explore             # fork 시 에이전트 유형
allowed-tools: [Bash, Read]      # 도구 제한
hooks:                     # 스킬 라이프사이클 훅
  PreToolUse:
    - matcher: "Write"
      hook: "echo 'pre-write hook'"
---
```

---

## 2. MCP (Model Context Protocol) 표준 구조

### MCP 서버 디렉토리 레이아웃

```
mcp/
├── README.md                    # MCP 서버 인덱스
├── {server-name}/               # 개별 MCP 서버
│   ├── README.md                # 서버 설명, 설치, 사용법
│   ├── server.py                # Python MCP 서버 구현
│   ├── config.json              # 서버 설정 예시
│   └── tests/
│       └── test_server.py
```

### 현재 등록된 MCP 서버

| 서버 | 파일 | 용도 |
|------|------|------|
| memory-mcp | `tools/memory_mcp_server.py` | 봇 간 공유 메모리 |

### MCP 서버 등록 절차 (settings.json)

```bash
# 1. MCP 서버 구현
mkdir -p mcp/{server-name}
# server.py 작성 (MCP SDK 사용)

# 2. .claude/settings.json 에 등록
# (update-config 스킬 사용 권장)
```

`.claude/settings.json` MCP 등록 예시:
```json
{
  "mcpServers": {
    "{server-name}": {
      "command": ".venv/bin/python",
      "args": ["mcp/{server-name}/server.py"],
      "env": {
        "DB_PATH": "./data/memory.db"
      }
    }
  }
}
```

### 기존 `tools/memory_mcp_server.py` 활용

```bash
# settings.json에 이미 등록된 메모리 MCP 서버 확인
cat .claude/settings.local.json | python3 -m json.tool
```

---

## 3. Skills 카테고리 분류

| 카테고리 | 설명 | 예시 |
|----------|------|------|
| Process Enforcement | 팀 프로세스 강제 | `engineering-review`, `quality-gate` |
| Domain Knowledge | 조직 고유 지식 주입 | `design-critique` |
| Workflow Automation | 반복 작업 자동화 | `weekly-review`, `retro`, `pm-task-dispatch` |
| Business Process | 팀 협업 절차 자동화 | `pm-discussion`, `performance-eval` |
| Code Scaffolding | 보일러플레이트 생성 | (향후 추가) |
| Code Quality | 코드 품질 기준 강제 | `safe-modify`, `failure-detect-llm` |
| CI/CD & Deployment | 배포 자동화 | (향후 추가) |
| Runbooks | 장애 대응 런북 | `bot-triage`, `harness-audit` |
| Infrastructure Ops | 인프라 운영 | `loop-checkpoint` |

---

## 4. 스킬 등록 체크리스트

새 스킬 추가 시 반드시 아래 항목을 완료한다:

- [ ] `skills/{name}/SKILL.md` 생성 (frontmatter 유효성 확인)
- [ ] `.claude/skills/{name}` 심볼릭 링크 생성
- [ ] `organizations.yaml`에 등록 (common_skills 또는 preferred_skills)
- [ ] `skills/README.md` 스킬 목록 업데이트
- [ ] `CLAUDE.md` 스킬 전략 테이블 업데이트 (해당 시)
- [ ] `AGENTS.md` 스킬 전략 테이블 업데이트 (해당 시)
- [ ] `GEMINI.md` 스킬 전략 테이블 업데이트 (해당 시)
- [ ] gotchas.md 초안 작성 (최소 1개 엣지케이스)

---

## 5. MCP 추가 가이드라인

### 언제 MCP를 추가하는가?
- 상태를 유지해야 하는 외부 서비스 연동 (DB, API)
- 스킬로 해결하기 어려운 구조화된 도구 인터페이스 필요 시
- 여러 봇이 공유하는 공통 기능

### 언제 스킬로 충분한가?
- 단순 프로세스/가이드라인 제공
- 단발성 작업 자동화
- 특정 봇에만 필요한 도메인 지식

### MCP vs Skill 선택 기준
```
상태 유지 필요? → MCP
공유 도구 인터페이스? → MCP
가이드/프로세스 강제? → Skill
워크플로 자동화? → Skill
```

---

## 6. 현재 스킬 전체 목록

| 스킬 | 카테고리 | 트리거 키워드 |
|------|----------|--------------|
| `pm-task-dispatch` | Business Process | 업무배분, pm dispatch |
| `pm-discussion` | Business Process | 토론, discuss |
| `weekly-review` | Workflow Automation | 주간회의, weekly review |
| `retro` | Workflow Automation | 회고, retrospective |
| `performance-eval` | Workflow Automation | 성과평가, evaluation |
| `engineering-review` | Code Quality | 코드리뷰, code review |
| `quality-gate` | Code Quality | 품질검사, quality gate |
| `safe-modify` | Code Quality | 안전 수정, safe modify |
| `failure-detect-llm` | Code Quality | LLM 실패감지, failure detect |
| `harness-audit` | Runbook | 하네스 감사, harness audit |
| `bot-triage` | Runbook | 봇 장애, bot down, triage |
| `loop-checkpoint` | Infrastructure Ops | 체크포인트, checkpoint |
| `design-critique` | Domain Knowledge | 디자인 리뷰, design review |
| `growth-analysis` | Domain Knowledge | 성장분석, growth analysis |
| `brainstorming-auto` | Business Process | 자동 설계, auto design |
| `autonomous-skill-proxy` | Process Enforcement | 자율모드, autonomous mode |
| `create-skill` | Workflow Automation | 스킬 만들기, create skill |
| `skill-evolve` | Process Enforcement | 스킬 진화, skill evolution |
| `error-gotcha` | Process Enforcement | 에러 회고, error gotcha |
| `e2e-regression` | Code Quality | e2e 테스트, regression test |
| `gemini-image-gen` | Workflow Automation | 이미지 생성, image generation |

---

*최종 업데이트: 2026-03-24 | 관리: aiorg_pm_bot*
