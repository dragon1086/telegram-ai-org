---
name: gemini-image-gen
description: "Generate images using Google Gemini 3.1 Flash Image model via OAuth 2.0 (no API key required). Use when image generation, visual content creation, or diagram generation is needed. Triggers: '이미지 생성', 'image generation', 'generate image', '이미지 만들어', 'visual', '시각화', 'diagram', 'illustration'"
---

# Gemini 이미지 생성 스킬

Google Gemini 3.1 Flash Image 모델로 이미지를 생성한다.
정확한 모델명: **`gemini-3.1-flash-image-preview`** (절대 다른 모델 사용 금지)

## 호출 방식 (우선순위)

```
1순위: gemini CLI (OAuth)  →  간편, subprocess 기반
2순위: Google GenAI API    →  CLI에 모델 없거나 실패 시 fallback
```

### 방식 1: gemini CLI (OAuth 2.0)

```
OAuth 2.0 (Google Pro Plan)
  ↓
~/.gemini/oauth_creds.json
  ↓
gemini CLI subprocess
```

GeminiCLIRunner가 subprocess 실행 시 `GOOGLE_API_KEY`, `GEMINI_API_KEY` 환경변수를 자동 제거한다.

### 방식 2: Google GenAI API (CLI fallback)

gemini CLI에 `gemini-3.1-flash-image-preview` 모델이 없거나, CLI 호출 실패 시 API를 직접 호출한다.

```python
from google import genai
from google.genai import types
import base64, os
from pathlib import Path

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

response = client.models.generate_content(
    model="gemini-3.1-flash-image-preview",
    contents="아름다운 한국 풍경, 산과 강, 4K, 사실적",
    config=types.GenerateContentConfig(
        response_modalities=["TEXT", "IMAGE"],
    ),
)

# 응답에서 이미지 추출
for part in response.candidates[0].content.parts:
    if part.inline_data and part.inline_data.mime_type.startswith("image/"):
        image_bytes = part.inline_data.data
        Path("output.png").write_bytes(image_bytes)
        break
```

> **필요 패키지**: `pip install google-genai`
> **필요 환경변수**: `GEMINI_API_KEY` (.env에 설정)

## Step 1: 사전 확인

```bash
# Gemini CLI 인증 상태 확인
gemini auth status

# 인증 파일 존재 확인
ls ~/.gemini/oauth_creds.json 2>/dev/null && echo "인증 OK" || echo "인증 필요: gemini auth login"

# Gemini CLI 버전 확인
gemini --version
```

인증이 없으면: `gemini auth login` 실행 후 Google Pro Plan 계정으로 로그인.

## Step 2: 이미지 생성 명령

### 기본 사용법 (CLI 직접 호출)

```bash
# 텍스트 → 이미지 생성
gemini -p "아름다운 한국 풍경, 산과 강, 4K, 사실적" \
  --model gemini-3.1-flash-image-preview \
  --output-format json

# 또는 간단하게
gemini -p "Generate: [이미지 설명]" --model gemini-3.1-flash-image-preview
```

### Python 코드로 호출 (tools/gemini_image_runner.py 사용)

```python
import asyncio
from tools.gemini_image_runner import GeminiImageRunner, ImageGenRequest

async def generate_image(prompt: str, output_path: str) -> str:
    runner = GeminiImageRunner()
    request = ImageGenRequest(
        prompt=prompt,
        output_path=output_path,
        model="gemini-3.1-flash-image-preview",
    )
    result = await runner.generate(request)
    return result.image_path

# 실행
asyncio.run(generate_image(
    prompt="AI 조직 플랫폼 개요 다이어그램",
    output_path="./data/generated_image.png"
))
```

## Step 3: 결과 처리

생성된 이미지:
1. `data/images/` 디렉토리에 저장 (없으면 생성)
2. 파일명: `{timestamp}_{slugified_prompt}.png`
3. Telegram 전송 가능 여부 확인 (파일 크기 < 10MB)

```bash
# 생성 결과 확인
ls -la data/images/
```

## Step 4: Telegram 전송 (선택)

```python
from core.telegram_relay import send_photo

# 이미지 파일 전송
await send_photo(
    chat_id=CHAT_ID,
    photo_path="./data/images/generated_image.png",
    caption="생성된 이미지: {prompt}"
)
```

## 모델 정보 (2026-04-01 기준)

| 모델 | 상태 | 용도 |
|------|------|------|
| `gemini-3.1-flash-image-preview` | Preview | 이미지 생성 |
| `gemini-2.5-flash` | GA (stable) | 텍스트/코드 |
| `gemini-2.0-flash` | **Deprecated** (2026-06-01 종료) | 사용 금지 |

> **주의**: 이미지 생성 모델은 현재 Preview 단계. 프로덕션 사용 시 주의.
> 실제 사용 가능한 최신 모델명은 `gemini models list` 명령으로 확인.

## 코드 구현 가이드 (tools/gemini_image_runner.py)

스킬 호출 시 아래 패턴으로 구현한다. **CLI 우선, 실패 시 API fallback.**

```python
"""Gemini 이미지 생성 러너 — CLI 우선, API fallback."""
from __future__ import annotations

import asyncio
import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.gemini_cli_runner import GeminiCLIRunner, RunnerError
from tools.base_runner import RunContext


@dataclass
class ImageGenRequest:
    """이미지 생성 요청."""
    prompt: str
    output_path: str
    model: str = "gemini-3.1-flash-image-preview"
    width: int = 1024
    height: int = 1024


@dataclass
class ImageGenResult:
    """이미지 생성 결과."""
    image_path: str
    prompt: str
    model: str
    method: str  # "cli" 또는 "api"


class GeminiImageRunner:
    """Gemini 이미지 생성 러너.

    1순위: gemini CLI subprocess (OAuth 2.0)
    2순위: Google GenAI API (GEMINI_API_KEY) — CLI 실패 시 자동 전환
    """

    def __init__(self) -> None:
        self._cli_runner = GeminiCLIRunner()

    async def generate(self, request: ImageGenRequest) -> ImageGenResult:
        """이미지 생성 후 파일로 저장. CLI 실패 시 API fallback."""
        output_dir = Path(request.output_path).parent
        output_dir.mkdir(parents=True, exist_ok=True)

        # 1순위: CLI 시도
        try:
            return await self._generate_via_cli(request)
        except (RunnerError, Exception) as cli_err:
            import logging
            logging.getLogger(__name__).warning(
                f"CLI 이미지 생성 실패 ({cli_err}), API fallback 시도"
            )

        # 2순위: API fallback
        return await self._generate_via_api(request)

    async def _generate_via_cli(self, request: ImageGenRequest) -> ImageGenResult:
        """gemini CLI subprocess로 이미지 생성."""
        prompt = (
            f"Generate an image with the following description: {request.prompt}. "
            f"Return the image as base64 encoded PNG data in the response."
        )
        ctx = RunContext(
            prompt=prompt,
            engine_config={"model": request.model},
        )
        raw_response = await self._cli_runner.run(ctx)
        self._save_image_from_cli(raw_response, request.output_path)
        return ImageGenResult(
            image_path=request.output_path,
            prompt=request.prompt,
            model=request.model,
            method="cli",
        )

    async def _generate_via_api(self, request: ImageGenRequest) -> ImageGenResult:
        """Google GenAI API로 직접 이미지 생성 (CLI fallback)."""
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise RunnerError(
                "google-genai 패키지 필요: pip install google-genai"
            )

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RunnerError(
                "API fallback 실패: GEMINI_API_KEY 환경변수가 설정되지 않았습니다. "
                ".env 파일에 GEMINI_API_KEY=... 를 추가하세요."
            )

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=request.model,  # gemini-3.1-flash-image-preview
            contents=request.prompt,
            config=types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"],
            ),
        )

        # 응답에서 이미지 파트 추출
        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                Path(request.output_path).write_bytes(part.inline_data.data)
                return ImageGenResult(
                    image_path=request.output_path,
                    prompt=request.prompt,
                    model=request.model,
                    method="api",
                )

        raise RunnerError(f"API 응답에 이미지 없음. 텍스트만 반환됨.")

    def _save_image_from_cli(self, response: str, output_path: str) -> None:
        """CLI 응답에서 이미지 데이터를 추출하여 파일로 저장."""
        try:
            data = json.loads(response)
            images = data.get("images", [])
            if images:
                image_data = base64.b64decode(images[0]["data"])
                Path(output_path).write_bytes(image_data)
            else:
                raise RunnerError(f"이미지 데이터 없음. 응답: {response[:200]}")
        except (json.JSONDecodeError, KeyError) as e:
            raise RunnerError(f"이미지 응답 파싱 실패: {e}") from e
```

## OAuth 설정 문제 해결

| 증상 | 원인 | 해결 |
|------|------|------|
| `oauth_creds.json` 없음 | 인증 미완료 | `gemini auth login` 실행 |
| `401 Unauthorized` | 토큰 만료 | `gemini auth login --refresh` |
| `403 Forbidden` | Pro Plan 권한 없음 | Google Pro Plan 구독 확인 |
| `model not found` | 모델명 오타 | `gemini models list` 로 확인 |

## 참고: GeminiCLIRunner 재사용

이 스킬은 `tools/gemini_cli_runner.py`의 `GeminiCLIRunner`를 그대로 활용한다.
별도 인증 코드 불필요 — OAuth는 GeminiCLIRunner가 자동 처리.

```python
# GeminiCLIRunner 인증 흐름
# 1. subprocess 환경에서 GEMINI_API_KEY, GOOGLE_API_KEY 제거
# 2. gemini CLI가 ~/.gemini/oauth_creds.json 자동 사용
# 3. 결과 JSON 파싱 → response 필드 반환
```
