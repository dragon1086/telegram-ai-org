#!/usr/bin/env python3
"""OKR 시스템 다이어그램 생성 스크립트.

Gemini 이미지 생성 API로 OKR 목표 관리 시스템 다이어그램을 생성한다.
- Model: gemini-3.1-flash-image-preview (thinking mode refinement via gemini-2.5-flash)
- Output: assets/diagrams/feat_okr_system.png
"""
from __future__ import annotations

import base64
import os
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from dotenv import load_dotenv
    load_dotenv(project_root / ".env")
except ImportError:
    pass

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
OUTPUT_PATH = project_root / "assets" / "diagrams" / "feat_okr_system.png"
IMAGE_GEN_MODEL = "gemini-3.1-flash-image-preview"
IMAGE_GEN_FALLBACK = "gemini-2.5-flash-image"
THINKING_MODEL = "gemini-2.5-flash"

OKR_DIAGRAM_PROMPT = """Create an OKR Goal Management System diagram for a Telegram AI bot platform.
White background, clean modern style, 1920x1080.

The diagram must show exactly these 3 sections side by side:

LEFT SECTION - "OKR Hierarchy" title at top:
Four rounded rectangles stacked vertically, connected by downward arrows:
1. Dark blue box labeled "Objective" with target emoji
2. Medium blue box labeled "Key Result" with subtitle "KPI-based"
3. Light blue box labeled "Initiative"
4. Cyan box labeled "Task" with subtitle "Auto-assigned"

CENTER SECTION - "Review Cycle" title at top:
Four green circles arranged in a clockwise cycle with curved arrows connecting them:
- Top: "Daily Retro"
- Right: "Weekly Review"
- Bottom: "Monthly Review"
- Left: "Quarterly Eval"

RIGHT SECTION - "Performance & Evolution" title at top:
Three boxes stacked vertically with downward arrows:
1. Amber/yellow box: "Performance Score (S/A/B/C/D/F)"
2. Orange box: "Bot Personality Evolution"
3. Red-orange box: "Prompt Injection"

Horizontal arrows connecting: Left section to Center section, Center section to Right section.

Bottom bar with 3 colored pills: "NL Goal Setting" (blue), "KPI Tracking" (green), "Dashboard" (purple).

Title at very top: "OKR Goal Management System"
Style: Flat design, corporate tech diagram, minimal, readable."""


def refine_prompt(client, prompt: str) -> str:
    """Thinking mode로 프롬프트 정제."""
    print("  [Thinking] 프롬프트 정제 중...")
    try:
        from google.genai import types

        instruction = f"""You are an expert AI image generation prompt engineer.
Analyze the following image generation prompt and return an IMPROVED version that will produce
a higher quality, more information-dense, visually clear image.

Keep the same content and requirements but:
1. Make spatial layout instructions more precise
2. Add specific color values where missing
3. Clarify font and text element positions
4. Ensure technical diagram elements are unambiguous
5. Keep it concise but complete (under 400 words)

Return ONLY the improved prompt text, no explanation.

ORIGINAL PROMPT:
{prompt}"""

        response = client.models.generate_content(
            model=THINKING_MODEL,
            contents=instruction,
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=5000),
                max_output_tokens=2048,
            ),
        )
        refined = response.text.strip()
        if refined and len(refined) > 50:
            print(f"  [Thinking] 정제 완료 ({len(refined)} chars)")
            return refined
        return prompt
    except Exception as e:
        print(f"  [Thinking] 정제 스킵: {e}")
        return prompt


def generate_image(client, prompt: str, model: str = IMAGE_GEN_MODEL) -> bool:
    """이미지 생성 및 저장."""
    from google.genai import types

    print(f"  [Generate] 이미지 생성 중 (model={model})...")
    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
            ),
        )

        for part in response.candidates[0].content.parts:
            if part.inline_data is not None:
                image_data = part.inline_data.data
                if isinstance(image_data, str):
                    image_bytes = base64.b64decode(image_data)
                else:
                    image_bytes = image_data

                OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
                OUTPUT_PATH.write_bytes(image_bytes)
                size_kb = len(image_bytes) // 1024
                print(f"  OK: {OUTPUT_PATH} ({size_kb} KB)")
                return True

        print("  No image part in response")
        return False

    except Exception as e:
        print(f"  Failed: {e}")
        return False


def main() -> int:
    if not GEMINI_API_KEY:
        print("ERROR: GEMINI_API_KEY not set")
        return 1

    from google import genai

    client = genai.Client(api_key=GEMINI_API_KEY)

    # Step 1: 이미지 생성 (primary model, skip thinking refinement)
    if generate_image(client, OKR_DIAGRAM_PROMPT, IMAGE_GEN_MODEL):
        return 0

    # Step 3: Fallback model
    print("  [Fallback] Trying fallback model...")
    if generate_image(client, refined_prompt, IMAGE_GEN_FALLBACK):
        return 0

    # Step 4: Original prompt로 재시도
    print("  [Retry] Trying with original prompt...")
    if generate_image(client, OKR_DIAGRAM_PROMPT, IMAGE_GEN_MODEL):
        return 0

    print("All attempts failed.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
