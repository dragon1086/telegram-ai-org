# 스킬 실행코드 패턴 + Hermes Feature Flag 레퍼런스 보고서

> 작성일: 2026-03-31 | 조사 범위: skills/ 전체, core/tool_registry.py, core/platform_adapter.py, core/context_compressor.py
> 목적: 껍데기 구현 및 신규 스킬 작성 시 참고 레퍼런스

---

## ① 디렉토리 컨벤션 요약

### skills/ 최상위 구조 (24개 스킬)

```
skills/
├── __init__.py                      # Python 패키지 마커 (내용 없음)
├── README.md                        # 스킬 가이드 문서
├── _shared/
│   └── save-log.py                  # 공용 로그 저장 유틸
│
├── <skill-name>/                    # 각 스킬 디렉토리
│   ├── SKILL.md  (또는 skill.md)    # ★ 필수: 스킬 정의 + 실행 절차 (frontmatter 포함)
│   ├── gotchas.md                   # ★ 권장: 재발 방지 항목 목록
│   ├── config.json                  # 선택: 라우팅·설정 (pm-task-dispatch, autonomous-skill-proxy)
│   ├── scripts/
│   │   └── run.py  or  run.sh       # 선택: 직접 실행 가능한 CLI 스크립트
│   ├── templates/                   # 선택: 마크다운 템플릿 (bot-triage, weekly-review)
│   ├── references/                  # 선택: 참고 문서 (pm-task-dispatch)
│   └── data/                        # 선택: 데이터 디렉토리 (weekly-review)
```

### SKILL.md frontmatter 표준 (필수)

```yaml
---
name: skill-name                          # kebab-case, 디렉토리명과 일치
description: "트리거 조건 설명 (영+한)"   # 하네스가 이걸 읽어 자동 매칭
allowed-tools: Read, Write, Edit, Bash    # 허용 도구 목록
model: gemini-2.5-flash                   # 선택: 특정 모델 지정 시
hooks:                                    # 선택: 자동 후크
  PostToolUse:
    - matcher: "Write"
      hook: "bash skills/quality-gate/scripts/lint-only.sh"
---
```

### 스킬명 규칙
- 디렉토리명 = `name` frontmatter 값 = kebab-case
- 예외: `pm-progress-tracker`는 `skill.md` (소문자) — 표준은 `SKILL.md` (대문자)

---

## ② 실행코드 패턴 가이드

### 공통 패턴 (3개 사례 분석: error-gotcha, failure-detect-llm, pm-progress-tracker)

#### 패턴 1: 진입점 구조

```python
#!/usr/bin/env python3
"""스킬명 스킬 실행 스크립트.

사용법 docstring — 필수
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# PROJECT_ROOT 계산 패턴 (부모 디렉토리 수는 스크립트 위치에 따라 조정)
PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))  # failure-detect-llm 스타일
# 또는
SKILLS_DIR = PROJECT_ROOT / "skills"   # error-gotcha 스타일

if __name__ == "__main__":
    main()
```

#### 패턴 2: 함수 시그니처 (단순 스킬)

```python
def cmd_add(arg1: str, arg2: str, option: str | None) -> None:
    """기능 설명."""
    # 검증 → 처리 → 출력 순서
    ...

def cmd_list(filter_arg: str | None) -> None:
    """목록 조회."""
    ...

def main() -> None:
    parser = argparse.ArgumentParser(description="스킬명 실행기")
    subparsers = parser.add_subparsers(dest="command")
    # 서브커맨드 등록
    ...
```

#### 패턴 3: 함수 시그니처 (비동기 스킬)

```python
async def main() -> int:
    """반환값: 0=성공, 1=실패 (sys.exit에 전달)"""
    ...
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

#### 패턴 4: 입출력 포맷

| 구분 | 입력 | 출력 |
|------|------|------|
| CLI 스크립트 (`run.py`) | argparse + `--option` 플래그 | stdout 텍스트 또는 JSON |
| 비동기 스킬 | stdin JSON 또는 `--file` 플래그 | `json.dumps(..., ensure_ascii=False, indent=2)` |
| SKILL.md 내장 절차 | `$ARGUMENTS` 환경변수 또는 대화 컨텍스트 | 마크다운 텍스트 |

#### 패턴 5: 오류 처리 방식

```python
# 방식 A: sys.exit(1) + print 메시지 (error-gotcha 스타일)
if not path.exists():
    print(f"❌ 파일 없음: {path}")
    sys.exit(1)

# 방식 B: logger + return 코드 (failure-detect-llm 스타일)
if not diff_path.exists():
    logger.error(f"파일을 찾을 수 없음: {diff_path}")
    return 1

# 공통: 광범위 except 처리 시 로깅 후 재raise
try:
    result = handler(**kwargs)
except Exception as exc:  # noqa: BLE001
    logger.error("... raised %s: %s", type(exc).__name__, exc)
    raise
```

#### 패턴 6: 의존성 선언 방식

```python
# 외부 패키지: loguru, asyncio 등은 직접 import
from loguru import logger

# 내부 모듈: REPO_ROOT → sys.path 추가 후 import
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
from core.llm_failure_detector import LLMFailureDetector

# 선택적 의존성: try/except으로 graceful fallback
try:
    import tiktoken
    enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))
except Exception:
    pass  # fallback 로직 실행
```

---

## ③ Hermes Feature Flag 위치 및 활성화 조건 정리표

### 위치 및 플래그 현황

| 컴포넌트 | 파일 경로 | 환경변수 | 현재 기본값 | 활성화 조건 |
|----------|-----------|----------|-------------|-------------|
| Tool Registry | `core/tool_registry.py` | `ENABLE_TOOL_REGISTRY` | `"true"` (코드 기본값) | `"true"`, `"1"`, `"yes"` |
| Platform Adapter | `core/platform_adapter.py` | `ENABLE_PLATFORM_ADAPTER` | `"true"` (코드 기본값) | `"true"`, `"1"`, `"yes"` |
| Context Compressor | `core/context_compressor.py` | `ENABLE_CONTEXT_COMPRESSOR` | `"true"` (코드 기본값) | `"true"`, `"1"`, `"yes"` |

> `.env.example` 라인 404~412: 세 플래그 모두 `=true` 로 명시됨

### 코드 위치 상세

```
core/
├── tool_registry.py       # ToolEntry, ToolRegistry 클래스 + get_registry() 싱글턴
├── platform_adapter.py    # PlatformAdapter ABC, TelegramPlatformAdapter + get_adapter()
└── context_compressor.py  # ContextCompressor 클래스 + get_compressor() 싱글턴
```

### 현재 통합 상태 ⚠️

**세 모듈 모두 독립 구현은 완료됐으나 메인 런타임에 아직 호출 지점 없음.**
- `core/`, `bots/`, `tools/` 어디에서도 `get_registry()`, `get_adapter()`, `get_compressor()` 호출 코드 미존재
- 테스트 파일(`tests/unit/`, `tests/integration/`)에서만 사용됨
- 즉, **기본값 `true`로 바뀌었어도 실제 스킬 로딩 흐름에 연결되지 않은 상태**

---

## ④ Hermes Feature Flag 변경 전후 대조표

| 항목 | 변경 전 (flag=false) | 변경 후 (flag=true / 현재) |
|------|----------------------|---------------------------|
| **Tool Registry** | 모든 `register()` / `dispatch()` 호출이 no-op, `get()` → None 반환 | 도구 중앙 등록·조회·디스패치 활성화 |
| **도구 등록 절차** | 불필요 (스킵) | `get_registry().register(name, desc, handler, tags, schema)` 호출 필요 |
| **도구 호출** | 기존 함수 직접 호출 | `get_registry().dispatch("tool_name", **kwargs)` 경유 |
| **태그 기반 검색** | 불가 | `get_tools_by_tag("read", "file")` → ToolEntry 리스트 |
| **Platform Adapter** | `normalize_inbound()` → None, `send_message()` → False (no-op) | 텔레그램 Update → InboundMessage 정규화, OutboundMessage → 전송 |
| **메시지 수신 흐름** | 텔레그램 raw 객체를 각 핸들러가 직접 파싱 | `TelegramPlatformAdapter.normalize_inbound(update)` → `InboundMessage` DTO |
| **메시지 발송 흐름** | `bot.send_message(chat_id, text)` 직접 호출 | `adapter.send_message(OutboundMessage(chat_id=..., text=...))` |
| **Context Compressor** | `compress()` → messages 원본 그대로 반환 | system 보존 → keep_last_n 보존 → 예산 내 older 채움 3계층 압축 |
| **컨텍스트 전달** | 전체 대화 히스토리 그대로 전달 | `get_compressor().compress(messages, max_tokens=4000)` 후 압축본 전달 |
| **레지스트리 등록** | 없음 | 스킬 로딩 시 `get_registry().register(skill_name, ...)` 패턴 추가 필요 |
| **런타임 통합** | 기존 코드 그대로 | DispatchService 등 통합 레이어에서 세 모듈 연결 필요 (현재 미구현) |

---

## ⑤ 오픈소스 패턴 비교표

### 비교 대상: LangChain Tool / AutoGPT Plugin / CrewAI Tool

| 항목 | 현재 프로젝트 | LangChain Tool | AutoGPT Plugin | CrewAI Tool |
|------|--------------|----------------|----------------|-------------|
| **정의 방식** | SKILL.md frontmatter + 선택적 run.py | `@tool` 데코레이터 또는 `BaseTool` 상속 | `plugin.json` manifest + Python 클래스 | `@tool` 데코레이터 또는 `BaseTool` 상속 |
| **등록 방식** | 하네스가 `skills/` 스캔 후 자동 로드 | `AgentExecutor(tools=[...])` 에 직접 전달 | `PluginRegistry`에 플러그인 등록 | `Agent(tools=[...])` 에 직접 전달 |
| **입력 타입** | `$ARGUMENTS` 문자열 or argparse | Pydantic BaseModel schema | JSON 스키마 (openapi.yaml) | Pydantic BaseModel schema |
| **출력 타입** | stdout 텍스트 또는 JSON | 문자열 또는 ToolResult 객체 | JSON response | 문자열 또는 ToolOutput 객체 |
| **오류 처리** | sys.exit(1) 또는 logger.error + return 1 | `ToolException` raise | HTTP 상태코드 | `ToolException` raise |
| **비동기 지원** | asyncio.run(main()) 패턴 | `arun()` 메서드 분리 | async/await 지원 | `async_run()` 메서드 분리 |
| **태그/카테고리** | ToolEntry.capability_tags (Set[str]) | 없음 (직접 필터링) | category 필드 | 없음 |
| **Feature Flag** | 환경변수 기반 (`ENABLE_*=true/false`) | 없음 (코드 레벨 분기) | 없음 | 없음 |
| **Manifest 분리** | SKILL.md (마크다운 frontmatter) | 코드와 일체화 | plugin.json 분리 | 코드와 일체화 |
| **공통점** | - | name/description 필수 | name/description 필수 | name/description 필수 |

### 주요 차이점 요약

1. **현재 프로젝트의 강점**: SKILL.md = 절차 문서 + 메타데이터 일체화. 비개발자도 스킬 정의 가능.
2. **현재 프로젝트의 갭**: LangChain/CrewAI처럼 스킬 인스턴스를 런타임에 동적으로 등록·호출하는 통합 레이어(DispatchService)가 미구현 상태.
3. **AutoGPT와 가장 유사**: manifest 분리(SKILL.md ≈ plugin.json) + 레지스트리 패턴(ToolRegistry ≈ PluginRegistry).

---

## ⑥ 권장 구현 패턴 (껍데기 코드 예시)

### 신규 스킬 최소 구조

```
skills/my-new-skill/
├── SKILL.md          # 반드시 작성
├── gotchas.md        # 초기엔 빈 파일도 OK
└── scripts/
    └── run.py        # 실행 코드가 있을 경우
```

### SKILL.md 껍데기 템플릿

```markdown
---
name: my-new-skill
description: "스킬 설명. Triggers: '트리거 키워드1', '트리거 키워드2'"
allowed-tools: Read, Write, Edit
---

# My New Skill

## 실행 조건
- 언제 이 스킬을 실행하는가

## Step 1: 입력 파싱
$ARGUMENTS에서 필요한 값 추출

## Step 2: 핵심 로직
...

## Step 3: 출력
...

## 완료 조건
- [ ] 산출물 생성됨
- [ ] 오류 없음
```

### run.py 껍데기 (단순 CLI 스킬)

```python
#!/usr/bin/env python3
"""my-new-skill 실행 스크립트."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SKILLS_DIR = PROJECT_ROOT / "skills"


def cmd_run(target: str) -> None:
    """핵심 실행 로직."""
    # TODO: 실제 구현
    print(f"✅ 완료: {target}")


def main() -> None:
    parser = argparse.ArgumentParser(description="my-new-skill 실행기")
    parser.add_argument("target", help="처리 대상")
    args = parser.parse_args()
    cmd_run(args.target)


if __name__ == "__main__":
    main()
```

### Hermes Tool Registry 연동 패턴 (flag=true 이후 적용)

```python
# 스킬 로딩 시 레지스트리 등록 패턴
from core.tool_registry import get_registry

def register_skills() -> None:
    """skills/ 디렉토리를 스캔하여 Tool Registry에 등록."""
    reg = get_registry()
    reg.register(
        name="my-new-skill",
        description="스킬 설명",
        handler=cmd_run,           # callable
        tags={"skill", "custom"},  # capability tags
        schema={                   # JSON Schema (선택)
            "type": "object",
            "properties": {"target": {"type": "string"}},
        },
    )

# 디스패치 패턴
result = get_registry().dispatch("my-new-skill", target="입력값")
```

### Context Compressor 연동 패턴 (긴 대화 스킬)

```python
from core.context_compressor import get_compressor

# 스킬 실행 전 컨텍스트 압축
compressor = get_compressor()
compressed_messages = compressor.compress(
    messages=conversation_history,
    max_tokens=4000,
    keep_last_n=4,  # 최근 4개 메시지 보존
)
# compressed_messages를 LLM에 전달
```

---

## 결론 및 권장 사항

### 즉시 적용 가능한 패턴
1. **신규 스킬 생성 시**: `SKILL.md` + `gotchas.md` + `scripts/run.py` 3파일 구조 준수
2. **run.py 작성 시**: `PROJECT_ROOT = Path(__file__).resolve().parents[3]` + argparse 패턴 사용
3. **오류 처리**: 단순 CLI → `print + sys.exit(1)`, 비동기 → `logger.error + return 1`

### Hermes 연동을 위한 다음 구현 필요 사항 (개발실 과제)
- **DispatchService**: 스킬 로딩 시 `get_registry().register()` 호출 통합
- **메시지 처리**: `TelegramPlatformAdapter.normalize_inbound()` → bot handler 연결
- **컨텍스트 관리**: `get_compressor().compress()` → LLM 호출 전 적용

> ⚠️ 현재 세 Hermes 모듈은 코드는 완성됐으나 메인 런타임 호출 지점이 없음.
> 기본값 `true`로 변경됐어도 실제 동작에 미영향. 통합 레이어 구현이 필요.
