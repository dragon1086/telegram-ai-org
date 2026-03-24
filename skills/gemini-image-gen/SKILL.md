---
name: gemini-image-gen
description: "Generate images using Google Gemini 2.5 Flash Image model via OAuth 2.0 (no API key required). Use when image generation, visual content creation, or diagram generation is needed. Triggers: '이미지 생성', 'image generation', 'generate image', '이미지 만들어', 'visual', '시각화', 'diagram', 'illustration'"
---

# Gemini 이미지 생성 스킬

Google Gemini 2.5 Flash Image 모델을 OAuth 2.0으로 사용해 이미지를 생성한다.
**API Key 사용 금지** — OAuth 기반 인증 전용.

## 인증 방식

```
OAuth 2.0 (Google Pro Plan)
  ↓
~/.gemini/oauth_creds.json
  ↓
gemini CLI subprocess
```

API Key(`GOOGLE_API_KEY`, `GEMINI_API_KEY`)는 사용하지 않는다.
GeminiCLIRunner가 subprocess 실행 시 해당 환경변수를 자동 제거한다.

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
  --model gemini-2.5-flash-preview-image-generation \
  --output-format json

# 또는 간단하게
gemini -p "Generate: [이미지 설명]" --model gemini-2.5-flash-preview-image-generation
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
        model="gemini-2.5-flash-preview-image-generation",
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

## 모델 정보 (2026-03-24 기준)

| 모델 | 상태 | 용도 |
|------|------|------|
| `gemini-2.5-flash-preview-image-generation` | Preview | 이미지 생성 |
| `gemini-2.5-flash` | GA (stable) | 텍스트/코드 |
| `gemini-2.0-flash` | **Deprecated** (2026-06-01 종료) | 사용 금지 |

> **주의**: 이미지 생성 모델은 현재 Preview 단계. 프로덕션 사용 시 주의.
> 실제 사용 가능한 최신 모델명은 `gemini models list` 명령으로 확인.

## 코드 구현 가이드 (tools/gemini_image_runner.py)

스킬 호출 시 아래 패턴으로 구현한다:

```python
"""Gemini 이미지 생성 러너 — OAuth subprocess 기반."""
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
    model: str = "gemini-2.5-flash-preview-image-generation"
    width: int = 1024
    height: int = 1024


@dataclass
class ImageGenResult:
    """이미지 생성 결과."""
    image_path: str
    prompt: str
    model: str


class GeminiImageRunner:
    """Gemini CLI를 사용한 이미지 생성 러너.

    OAuth 2.0 기반. API Key 사용 안 함.
    gemini CLI subprocess를 통해 이미지 생성 후 base64 디코딩하여 저장.
    """

    def __init__(self) -> None:
        self._cli_runner = GeminiCLIRunner()

    async def generate(self, request: ImageGenRequest) -> ImageGenResult:
        """이미지 생성 후 파일로 저장."""
        # 출력 디렉토리 생성
        output_dir = Path(request.output_path).parent
        output_dir.mkdir(parents=True, exist_ok=True)

        # Gemini CLI로 이미지 생성 프롬프트 실행
        prompt = (
            f"Generate an image with the following description: {request.prompt}. "
            f"Return the image as base64 encoded PNG data in the response."
        )

        ctx = RunContext(
            prompt=prompt,
            engine_config={"model": request.model},
        )

        # subprocess 실행 (OAuth 인증 사용)
        raw_response = await self._cli_runner.run(ctx)

        # base64 이미지 데이터 추출 및 저장
        # (실제 응답 구조에 따라 파싱 로직 조정 필요)
        self._save_image(raw_response, request.output_path)

        return ImageGenResult(
            image_path=request.output_path,
            prompt=request.prompt,
            model=request.model,
        )

    def _save_image(self, response: str, output_path: str) -> None:
        """응답에서 이미지 데이터를 추출하여 파일로 저장."""
        try:
            data = json.loads(response)
            # Gemini API 응답 구조: {"response": "...", "images": [{"data": "base64..."}]}
            images = data.get("images", [])
            if images:
                image_data = base64.b64decode(images[0]["data"])
                Path(output_path).write_bytes(image_data)
            else:
                # 텍스트 응답만 있는 경우 (이미지 생성 실패)
                raise RunnerError(f"이미지 데이터 없음. 응답: {response[:200]}")
        except (json.JSONDecodeError, KeyError) as e:
            raise RunnerError(f"이미지 응답 파싱 실패: {e}. 응답: {response[:200]}") from e
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
