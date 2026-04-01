# Dependency Extras Guide

`telegram-ai-org` 패키지는 핵심 기능만 포함하는 경량 기본 설치를 제공합니다.
선택적 기능은 extras로 분리되어 필요할 때만 설치합니다.

## 기본 설치 (경량)

```bash
pip install telegram-ai-org
```

설치 크기: ~50MB (ML 라이브러리, SDK 번들 CLI 제외)

---

## Extras 목록

### `sdk` — Claude Agent SDK

`claude_agent_sdk` 패키지를 사용하는 `ClaudeAgentRunner`를 활성화합니다.
미설치 시 `base_runner._create_claude_runner()`가 자동으로 `ClaudeSubprocessRunner`로
폴백하므로 대부분의 경우 불필요합니다.

```bash
pip install 'telegram-ai-org[sdk]'
```

포함 패키지:
- `claude-agent-sdk>=0.1.50`

> 주의: `claude-agent-sdk`는 설치 시 `_bundled/` 디렉토리에 184MB의 Claude CLI 바이너리를
> 포함합니다. 이미 `claude-code` CLI가 설치되어 있다면 subprocess runner 폴백으로 충분합니다.

---

### `ml` — ML / 시각화 라이브러리

차트 생성, 이미지 처리, 폰트 렌더링 등 ML 관련 기능에 필요합니다.

```bash
pip install 'telegram-ai-org[ml]'
```

포함 패키지:
- `matplotlib>=3.0` (~20MB)
- `numpy>=1.20` (~23MB)
- `Pillow>=9.0` (~13MB)
- `fontTools>=4.0`

사용 예시 (코드 내 optional import 패턴):
```python
try:
    import matplotlib.pyplot as plt
    _MATPLOTLIB_AVAILABLE = True
except ImportError:
    _MATPLOTLIB_AVAILABLE = False
    # pip install 'telegram-ai-org[ml]' 안내
```

---

### `claude` — Anthropic SDK

`claude-code` 엔진 직접 API 연동에 필요합니다.

```bash
pip install 'telegram-ai-org[claude]'
```

---

### `codex` — OpenAI SDK

`codex` 엔진 직접 API 연동에 필요합니다.

```bash
pip install 'telegram-ai-org[codex]'
```

---

### `gemini` — Google GenAI SDK

`gemini-cli` 엔진 직접 API 연동에 필요합니다.

```bash
pip install 'telegram-ai-org[gemini]'
```

---

### `all` — 모든 엔진 SDK

```bash
pip install 'telegram-ai-org[all]'
```

---

### `dev` — 개발 도구

```bash
pip install 'telegram-ai-org[dev]'
```

---

## 복합 설치 예시

```bash
# SDK + ML 동시 설치
pip install 'telegram-ai-org[sdk,ml]'

# 개발 환경 전체
pip install 'telegram-ai-org[dev,sdk,ml]'
```

---

## 버전 이력

| 버전 | 변경 내용 |
|------|-----------|
| 1.2.0 | `claude-agent-sdk` 필수 → `[sdk]` optional 분리; `[ml]` extras 추가 |
| 1.1.0 | `fastapi`, `uvicorn` 필수 deps 추가 |
| 1.0.0 | 최초 공개 릴리스 |
