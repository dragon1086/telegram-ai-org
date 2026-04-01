"""워크플로우 라이프사이클 다이어그램 생성 스크립트.

Gemini 2.5 Flash Preview Image Generation 모델 사용.
OAuth 2.0 인증 (google.oauth2 기반).
"""
from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path

# venv 기준 실행 가정
from google import genai
from google.genai import types
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request


OAUTH_CREDS_PATH = Path.home() / ".gemini" / "oauth_creds.json"
OUTPUT_PATH = Path("/Users/rocky/telegram-ai-org/docs/assets/workflow_lifecycle_diagram.png")
MODEL = "gemini-2.5-flash-image"  # 실제 사용 가능한 모델명 (2026-04-01 확인)

DIAGRAM_PROMPT = """Create a highly detailed, information-dense technical workflow diagram for a multi-bot AI organization platform.

The diagram must include ALL THREE sections clearly separated:

## SECTION 1: Multi-Bot Dispatch Flow (top section)
- Show: User Message → Telegram → PM Bot (central hub)
- PM Bot routes to 6 department bots IN PARALLEL:
  * 🔵 개발실 (Engineering) - blue
  * 🟣 디자인실 (Design) - purple
  * 🟢 기획실 (Product) - green
  * 🟠 성장실 (Growth) - orange
  * 🩵 리서치실 (Research) - teal
  * 🔴 운영실 (Ops) - red
- Each bot runs Claude Code / Gemini CLI engine
- Results aggregate back to PM Bot → Telegram response

## SECTION 2: E2E Lifecycle Sequence (middle section)
Show numbered steps in a horizontal flow:
1. 사용자 입력 (User sends message to Telegram)
2. PM봇 수신 (PM Bot receives & classifies task)
3. 태스크 분류 (Task type: solo / collab / goal-tracker)
4. 엔진 선택 (Engine: Claude Code / Gemini CLI / Codex)
5. 서브에이전트 실행 (Sub-agent execution with persona)
6. 결과 집계 (Results aggregation with timeout handling)
7. 최종 응답 (Formatted response → Telegram)

## SECTION 3: Department Roles & Engine Map (bottom section)
Show a grid/table of 6 departments with:
- Department name in Korean + English
- Primary engine (Claude Code or Gemini CLI)
- Color-coded icon
- 3 key skills/responsibilities

## Style Requirements:
- White background, clean professional technical diagram style
- Korean labels with English subtitles
- Clear directional arrows showing data flow
- Distinct color coding per department (consistent with section 1)
- Font size readable at 1200x900px resolution
- Include title: "telegram-ai-org 워크플로우 라이프사이클"
- Add subtitle: "Multi-Bot AI Organization Platform — E2E Workflow"
- High information density but organized layout with clear sections
- Use boxes, arrows, icons, and connection lines
- Layer separation with subtle background shading per section"""


def load_oauth_credentials() -> Credentials:
    """~/.gemini/oauth_creds.json 에서 OAuth 자격증명 로드."""
    with open(OAUTH_CREDS_PATH) as f:
        cred_data = json.load(f)

    creds = Credentials(
        token=cred_data.get("access_token"),
        refresh_token=cred_data.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ.get("GOOGLE_CLIENT_ID", ""),
        client_secret=os.environ.get("GOOGLE_CLIENT_SECRET", ""),
        scopes=["https://www.googleapis.com/auth/generative-language.retriever"],
    )

    # 토큰 만료 시 갱신
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    return creds


def generate_with_api_key() -> bytes | None:
    """API Key 방식으로 이미지 생성 (fallback)."""
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None

    client = genai.Client(api_key=api_key)
    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=DIAGRAM_PROMPT,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
            ),
        )
        return _extract_image(response)
    except Exception as e:
        print(f"API Key 방식 실패: {e}", file=sys.stderr)
        return None


def generate_with_oauth() -> bytes | None:
    """OAuth 방식으로 이미지 생성."""
    try:
        creds = load_oauth_credentials()
        client = genai.Client(credentials=creds)
        response = client.models.generate_content(
            model=MODEL,
            contents=DIAGRAM_PROMPT,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
            ),
        )
        return _extract_image(response)
    except Exception as e:
        print(f"OAuth 방식 실패: {e}", file=sys.stderr)
        return None


def _extract_image(response) -> bytes | None:
    """응답에서 이미지 데이터 추출."""
    for candidate in response.candidates:
        for part in candidate.content.parts:
            if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                return part.inline_data.data
    # 텍스트 응답 확인 (디버깅)
    for candidate in response.candidates:
        for part in candidate.content.parts:
            if part.text:
                print(f"텍스트 응답: {part.text[:500]}", file=sys.stderr)
    return None


def main() -> int:
    """메인 실행."""
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    print(f"모델: {MODEL}")
    print(f"출력 경로: {OUTPUT_PATH}")
    print("이미지 생성 중 (thinking mode, budget=8000)...")

    # OAuth 방식 시도
    image_data = generate_with_oauth()

    if image_data is None:
        print("OAuth 실패, API Key 방식 시도...", file=sys.stderr)
        image_data = generate_with_api_key()

    if image_data is None:
        print("❌ 이미지 생성 실패", file=sys.stderr)
        return 1

    OUTPUT_PATH.write_bytes(image_data)
    size_kb = OUTPUT_PATH.stat().st_size // 1024
    print(f"✅ 이미지 저장 완료: {OUTPUT_PATH} ({size_kb} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
