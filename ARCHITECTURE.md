# ARCHITECTURE.md — telegram-ai-org 상세 설계

## 1. 비전

텔레그램 그룹 채팅방을 AI 조직의 오피스로 활용한다.
유저가 방향만 제시하면 PM AI가 R&R을 설계하고 팀을 구성한다.
각 AI 팀은 독립된 Telegram 봇 계정을 보유하며 실제 코딩/분석을 실행한다.

## 2. 핵심 구성요소

### 2.1 PM Bot (`@pm_bot`)
- **역할**: 오케스트레이터
- **기능**:
  - 유저 요청 수신 → 태스크 분해 → R&R 할당
  - 모든 봇의 작업 상태 추적
  - 완료 판단 → 전체 봇에 완료 확인 요청 → 최종 처리
- **모델**: claude-sonnet-4-6 (빠른 판단 + 오케스트레이션)

### 2.2 Worker Bots
| 봇 | 전문 영역 | 실행 엔진 |
|---|---|---|
| `@dev_bot` | 코딩 전담 | Claude Code / Codex |
| `@analyst_bot` | 분석/리서치 | amp MCP / GPT |
| `@docs_bot` | 문서화/README | Claude |

특징:
- 각 봇은 전문 프롬프트 + 툴셋 보유
- 동적 추가/제거 가능 (플러그인 구조)

### 2.3 Shared Context DB (`~/.ai-org/context.db`)
- SQLite + 벡터 임베딩 (sqlite-vec)
- 모든 봇 읽기 접근
- PM만 쓰기 (버전 관리)
- 프로젝트별 컨텍스트 슬롯

### 2.4 Message Bus (Telegram)

#### 메시지 포맷
```
[TO: @dev_bot | FROM: @pm_bot | TASK: T001 | STATUS: assign]
태스크 내용...
```

#### 라우팅 규칙
- `[TO: @dev_bot]` → dev_bot만 처리
- `[TO: ALL]` → 모든 봇 처리
- `[TO: @dev_bot, @analyst_bot]` → 지정된 봇들만 처리

봇들은 자기 @mention 또는 [TO: ALL] 메시지만 처리한다.

### 2.5 Completion Protocol
```
PM: "T001 완료로 보임. 각자 확인해주세요 [TO: ALL]"
dev_bot: "✅ 내 파트 완료 확인"
analyst_bot: "✅ 분석 완료 확인"
docs_bot: "✅ 문서 완료 확인"
PM: "T001 CLOSED ✅"
```

## 3. 메시지 스키마

```python
class OrgMessage(BaseModel):
    to: str | list[str]  # "@dev_bot" | ["@dev_bot", "@analyst_bot"] | "ALL"
    from_: str           # "@pm_bot"
    task_id: str         # "T001"
    msg_type: Literal["assign", "report", "query", "ack", "complete", "broadcast"]
    content: str
    context_ref: str | None  # context DB 슬롯 ID
    attachments: list[str]   # 파일 경로
```

## 4. 기술 스택

| 레이어 | 기술 |
|---|---|
| 언어 | Python 3.11+ |
| 봇 프레임워크 | python-telegram-bot 20.x |
| 공유 DB | SQLite + sqlite-vec |
| 실행 엔진 | subprocess (claude CLI, codex CLI) |
| 비동기 | asyncio |
| 스키마 검증 | pydantic v2 |
| 의존성 관리 | uv + pyproject.toml |

## 5. 디렉토리 구조

```
telegram-ai-org/
├── core/
│   ├── pm_bot.py          # PM 봇 (오케스트레이터)
│   ├── worker_bot.py      # Worker 봇 베이스 클래스
│   ├── message_schema.py  # OrgMessage pydantic 모델
│   ├── context_db.py      # 공유 컨텍스트 DB
│   ├── task_manager.py    # 태스크 상태 추적
│   └── completion.py      # 완료 검증 프로토콜
├── bots/
│   ├── dev_bot.py         # 코딩 전담 봇
│   ├── analyst_bot.py     # 분석 전담 봇
│   └── docs_bot.py        # 문서화 봇
├── tools/
│   ├── claude_code_runner.py  # Claude Code 실행 래퍼
│   ├── codex_runner.py        # Codex 실행 래퍼
│   └── amp_caller.py          # amp MCP 연동
└── scripts/
    ├── start_all.sh       # 모든 봇 시작
    └── setup.sh           # 초기 설정
```

## 6. 데이터 흐름

```
유저 메시지
    │
    ▼
PM Bot (수신 + 파싱)
    │
    ├─ 태스크 분해 (claude-sonnet-4-6)
    │
    ├─ Context DB에 프로젝트 컨텍스트 저장
    │
    ├─ Worker Bots에 할당 메시지 전송 (Telegram)
    │
    └─ Task Manager에 상태 등록
         │
         ▼
Worker Bots (각자 처리)
    │
    ├─ @dev_bot → Claude Code Runner → 코드 실행
    ├─ @analyst_bot → amp caller → 분석
    └─ @docs_bot → 문서 생성
         │
         ▼
결과 보고 (Telegram → PM Bot)
    │
    ▼
Completion Protocol
    │
    └─ 전체 확인 → CLOSED
```

## 7. 보안 고려사항

- 봇 토큰은 환경변수로만 관리 (.env)
- PM Bot만 Context DB 쓰기 권한
- 메시지 발신자 검증 (화이트리스트)
- 외부 코드 실행 시 샌드박스 적용 고려

## 8. 확장성

- 봇 플러그인 구조: `bots/` 디렉토리에 새 파일 추가만으로 봇 확장
- 실행 엔진 교체 가능: `tools/` 래퍼 교체로 Claude ↔ Codex ↔ GPT 전환
- 컨텍스트 벡터화: sqlite-vec → pgvector 마이그레이션 가능
