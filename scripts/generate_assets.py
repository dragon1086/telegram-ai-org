#!/usr/bin/env python3
"""
scripts/generate_assets.py
Phase 3: 시각 자료 생성 스크립트

Gemini 이미지 생성 API를 사용하여 프로젝트 로고·아키텍처 다이어그램·온보딩 배너를 생성한다.
- Model: gemini-2.0-flash-preview-image-generation (with thinking mode refinement via gemini-2.5-flash)
- SDK: google-genai v1.68.0+
- Output: assets/logo.png, assets/architecture_diagram.png, assets/onboarding_banner.png

사용법:
    python scripts/generate_assets.py [--asset logo|architecture|onboarding|all]
"""

from __future__ import annotations

import argparse
import base64
import os
import sys
import time
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# .env 로드
try:
    from dotenv import load_dotenv
    load_dotenv(project_root / ".env")
except ImportError:
    pass

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
ASSETS_DIR = project_root / "assets"
IMAGE_GEN_MODEL = "gemini-3.1-flash-image-preview"   # 실제 확인된 이미지 생성 모델
IMAGE_GEN_FALLBACK = "gemini-2.5-flash-image"        # 보조 fallback
IMAGEN_MODEL = "imagen-4.0-fast-generate-001"         # Imagen 4 fallback
THINKING_MODEL = "gemini-2.5-flash"                   # Thinking mode 프롬프트 정제

# ─── 프롬프트 정의 (docs/image_prompts.md 기반) ────────────────────────────

LOGO_PROMPT = """A professional project logo for an open-source AI multi-bot organization platform called "telegram-ai-org".

Visual concept: A cute futuristic mascot called NanoBunny2 — a small banana-shaped AI robot
with big expressive glowing blue eyes, a warm smile, tiny antenna on top emitting signal waves,
and subtle digital circuit board patterns etched on its yellow body.

Composition: Centered character on a clean white circular background with a thin indigo border ring.
The character holds a small holographic display showing a simple org-chart (PM bot at top,
6 department bots below, 3 engine icons at bottom).

Color palette:
- Body: bright warm yellow (#FFD60A)
- Digital accents: indigo (#4F46E5) and emerald (#10B981)
- Eyes: glowing cyan-blue
- Background: pure white circle with very subtle indigo shadow

Style: Clean vector illustration, flat design with soft gradients and minimal shadows.
Professional logo quality. No text in the image.
Output: 1024x1024, high-resolution PNG suitable for both light and dark backgrounds."""

ARCHITECTURE_PROMPT = """A clean, professional software architecture diagram for a multi-bot AI organization platform.
White background, corporate diagram style with Korean and English labels.

Title at the very top (centered, large text): "telegram-ai-org 멀티봇 아키텍처"
Subtitle: "Multi-Bot AI Organization Architecture"

THREE-TIER LAYOUT (top to bottom, with clear visual separation):

TIER 1 — PM Layer (top center):
  Single rounded rectangle box, indigo color (#4F46E5), white text
  Label: "PM봇 (Project Manager Bot)"
  Sub-label: "태스크 라우팅 · 조율 / Task Routing & Coordination"

TIER 2 — Department Layer (middle row, 6 boxes evenly spaced):
  Six department boxes, each with a unique pastel color and emoji icon:
  1. "개발실 (Dev)" — blue, 💻
  2. "운영실 (Ops)" — orange, ⚙️
  3. "디자인실 (Design)" — pink, 🎨
  4. "기획실 (Planning)" — purple, 📋
  5. "성장실 (Growth)" — green, 📈
  6. "리서치실 (Research)" — teal, 🔍
  Arrows flow downward from PM봇 to each department box.

TIER 3 — Engine Layer (bottom row, 3 boxes):
  Three engine boxes with distinct colors and icons:
  1. "Claude Code" — orange (#F97316), brain/code icon
     Used by: 개발실, 디자인실, 기획실, PM봇
  2. "Gemini CLI" — blue (#3B82F6), Google/sparkle icon
     Used by: 운영실, 성장실, 리서치실
  3. "Codex" — green (#10B981), openai/code icon
     Used by: All departments (fallback)

  Dotted arrows show which departments use which engines (color-coded by engine).

VISUAL DETAILS:
- Rounded rectangle boxes with drop shadows
- Clean directional arrows with labels
- Legend box in bottom-right corner showing engine color codes
- Grid/baseline alignment, professional whitespace

Style: Clean corporate tech diagram, Notion/Miro aesthetic, readable at 1920x1080.
No decorative elements. Pure information design."""

ONBOARDING_PROMPT = """A friendly, welcoming onboarding banner for an open-source AI multi-bot Telegram platform.
Landscape format, banner style. White/very light gray background.

TOP SECTION:
  Large centered headline text: "telegram-ai-org"
  Subtitle: "AI 멀티봇 조직 플랫폼 · 원클릭 설치"
  English sub-subtitle: "Multi-Bot AI Organization · One-Click Setup"
  Small cute banana robot mascot icon on the left side of the headline.

MIDDLE SECTION — Three steps displayed horizontally with icons:

Step 1 (left card, blue background):
  Large number "1" badge
  Icon: Terminal/command-line symbol
  Title: "설치 / Install"
  Code block style text: "bash setup.sh"
  Sub-text: "3엔진 자동 감지"

Step 2 (center card, indigo background):
  Large number "2" badge
  Icon: Robot/bot symbol
  Title: "봇 시작 / Start"
  Text: "Python bots auto-start"
  Sub-text: "PM봇 + 6개 조직봇"

Step 3 (right card, emerald background):
  Large number "3" badge
  Icon: Telegram plane logo symbol
  Title: "대화 시작 / Chat"
  Text: "@your_pm_bot"
  Sub-text: "텔레그램에서 즉시 사용"

BOTTOM SECTION:
  Three engine badges (pill-shaped, colored):
  🟠 Claude Code  🔵 Gemini CLI  🟢 Codex
  Small text: "3개 AI 엔진 동시 지원 · MIT License"

OVERALL STYLE:
  Modern, clean, inviting. Rounded card corners with subtle drop shadows.
  Gradient accents on step cards (blue to indigo to emerald left to right).
  Professional open-source project aesthetic.
  Korean and English text mixed naturally. Clear visual hierarchy."""

ASSETS_CONFIG = [
    {
        "name": "logo",
        "output_path": ASSETS_DIR / "logo.png",
        "prompt": LOGO_PROMPT,
        "description": "프로젝트 로고 (NanoBunny2 마스코트)",
    },
    {
        "name": "architecture",
        "output_path": ASSETS_DIR / "architecture_diagram.png",
        "prompt": ARCHITECTURE_PROMPT,
        "description": "아키텍처 다이어그램 (3엔진·봇 구조)",
    },
    {
        "name": "onboarding",
        "output_path": ASSETS_DIR / "onboarding_banner.png",
        "prompt": ONBOARDING_PROMPT,
        "description": "온보딩 배너 (원클릭 설치 3단계)",
    },
]


def refine_prompt_with_thinking(client, base_prompt: str, asset_name: str) -> str:
    """Thinking mode(gemini-2.5-flash)로 프롬프트를 정제한다."""
    print(f"  [Thinking] {asset_name} 프롬프트 정제 중...")
    try:
        from google.genai import types

        refinement_instruction = f"""You are an expert AI image generation prompt engineer.
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
{base_prompt}"""

        response = client.models.generate_content(
            model=THINKING_MODEL,
            contents=refinement_instruction,
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=5000),
                max_output_tokens=2048,
            ),
        )
        refined = response.text.strip()
        if refined and len(refined) > 50:
            print(f"  [Thinking] 정제 완료 ({len(refined)} chars)")
            return refined
        return base_prompt
    except Exception as e:
        print(f"  [Thinking] 정제 스킵 (fallback to original): {e}")
        return base_prompt


def generate_image(client, prompt: str, output_path: Path, asset_name: str, model: str = IMAGE_GEN_MODEL) -> bool:
    """Gemini 이미지 생성 API로 이미지를 생성하고 저장한다."""
    from google.genai import types

    print(f"  [Generate] {asset_name} 이미지 생성 중 (model={model})...")
    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
            ),
        )

        # 이미지 데이터 추출
        for part in response.candidates[0].content.parts:
            if part.inline_data is not None:
                image_data = part.inline_data.data
                # bytes 또는 base64 str 처리
                if isinstance(image_data, str):
                    image_bytes = base64.b64decode(image_data)
                else:
                    image_bytes = image_data

                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(image_bytes)
                size_kb = len(image_bytes) // 1024
                print(f"  ✅ 저장 완료: {output_path} ({size_kb} KB)")
                return True

        print(f"  ⚠️ 이미지 파트 없음 — 텍스트 응답: {response.text[:200] if hasattr(response, 'text') else 'N/A'}")
        return False

    except Exception as e:
        print(f"  ❌ 생성 실패: {e}")
        return False


def generate_image_fallback_imagen(client, prompt: str, output_path: Path, asset_name: str) -> bool:
    """Imagen 3 fallback 생성 시도."""
    print(f"  [Fallback] Imagen 3 으로 재시도 중...")
    try:
        from google.genai import types

        aspect = "1:1" if "logo" in str(output_path) else ("2:1" if "banner" in str(output_path) else "16:9")
        response = client.models.generate_images(
            model=IMAGEN_MODEL,
            prompt=prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio=aspect,
                output_mime_type="image/png",
            ),
        )
        if response.generated_images:
            img = response.generated_images[0]
            image_bytes = img.image.image_bytes
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(image_bytes)
            size_kb = len(image_bytes) // 1024
            print(f"  ✅ Fallback 저장 완료: {output_path} ({size_kb} KB)")
            return True
        return False
    except Exception as e:
        print(f"  ❌ Fallback도 실패: {e}")
        return False


def run_generation(target: str = "all") -> dict:
    """이미지 생성 실행 함수. 결과 딕셔너리 반환."""
    if not GEMINI_API_KEY:
        print("❌ GEMINI_API_KEY 가 설정되지 않았습니다. .env 파일을 확인하세요.")
        sys.exit(1)

    try:
        from google import genai
    except ImportError:
        print("❌ google-genai SDK가 설치되지 않았습니다: pip install google-genai")
        sys.exit(1)

    client = genai.Client(api_key=GEMINI_API_KEY)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    # 대상 필터
    if target == "all":
        targets = ASSETS_CONFIG
    else:
        targets = [a for a in ASSETS_CONFIG if a["name"] == target]
        if not targets:
            print(f"❌ 알 수 없는 asset: {target}. 선택 가능: logo, architecture, onboarding, all")
            sys.exit(1)

    results = {}
    total = len(targets)

    print(f"\n🚀 Phase 3: 시각 자료 생성 시작 ({total}개 대상)\n" + "=" * 60)

    for i, asset in enumerate(targets, 1):
        name = asset["name"]
        output_path = asset["output_path"]
        base_prompt = asset["prompt"]
        desc = asset["description"]

        print(f"\n[{i}/{total}] {desc}")
        print(f"  출력: {output_path}")

        # Step 1: Thinking mode로 프롬프트 정제
        refined_prompt = refine_prompt_with_thinking(client, base_prompt, name)
        time.sleep(1)  # API rate limit 방지

        # Step 2: 이미지 생성 (primary — gemini-3.1-flash-image-preview)
        success = generate_image(client, refined_prompt, output_path, name, model=IMAGE_GEN_MODEL)

        # Step 3: 실패 시 gemini-2.5-flash-image fallback
        if not success:
            print(f"  ↪ Primary 실패 — gemini-2.5-flash-image fallback 시도...")
            success = generate_image(client, refined_prompt, output_path, name, model=IMAGE_GEN_FALLBACK)

        # Step 4: Imagen 4 fallback
        if not success:
            print(f"  ↪ Imagen 4 fallback 시도...")
            success = generate_image_fallback_imagen(client, refined_prompt, output_path, name)

        # Step 5: 원본 프롬프트로 최종 재시도
        if not success:
            print(f"  ↪ Original 프롬프트로 최종 재시도...")
            success = generate_image(client, base_prompt, output_path, name, model=IMAGE_GEN_MODEL)

        results[name] = {
            "success": success,
            "path": str(output_path),
            "exists": output_path.exists(),
            "size_kb": (output_path.stat().st_size // 1024) if output_path.exists() else 0,
        }

        if i < total:
            time.sleep(2)  # 연속 요청 간 간격

    # 결과 요약
    print("\n" + "=" * 60)
    print("📊 생성 결과 요약:")
    success_count = 0
    for name, r in results.items():
        status = "✅" if r["success"] else "❌"
        size_info = f" ({r['size_kb']} KB)" if r["success"] else ""
        print(f"  {status} {name}: {r['path']}{size_info}")
        if r["success"]:
            success_count += 1

    print(f"\n완료: {success_count}/{total} 성공")
    return results


def main():
    parser = argparse.ArgumentParser(description="Phase 3: Gemini 이미지 생성 스크립트")
    parser.add_argument(
        "--asset",
        choices=["logo", "architecture", "onboarding", "all"],
        default="all",
        help="생성할 자산 선택 (기본값: all)",
    )
    args = parser.parse_args()
    run_generation(args.asset)


if __name__ == "__main__":
    main()
