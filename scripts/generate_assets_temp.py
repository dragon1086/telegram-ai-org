#!/usr/bin/env python3
"""scripts/generate_assets_temp.py

Temporary image generation script for Phase 4 mascot/logo/diagram assets.
Uses google-genai SDK with GEMINI_API_KEY from .env

Usage:
    python scripts/generate_assets_temp.py
"""
from __future__ import annotations

import os
import sys
import struct
import zlib
import time
from pathlib import Path

# Load .env
PROJECT_ROOT = Path(__file__).parent.parent
env_path = PROJECT_ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())


def create_placeholder_png(path: Path, width: int = 200, height: int = 200, color: tuple = (78, 205, 196), label: str = "") -> None:
    """Create a minimal solid-color PNG as placeholder."""
    path.parent.mkdir(parents=True, exist_ok=True)

    def png_chunk(chunk_type: bytes, data: bytes) -> bytes:
        c = chunk_type + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))

    raw = b""
    for y in range(height):
        raw += b"\x00" + bytes(color) * width

    compressed = zlib.compress(raw)
    idat = png_chunk(b"IDAT", compressed)
    iend = png_chunk(b"IEND", b"")

    with open(path, "wb") as f:
        f.write(signature + ihdr + idat + iend)

    print(f"  [placeholder] Created {path} ({width}x{height}, color={color})")


def try_generate_image(client, model: str, prompt: str, output_path: Path) -> bool:
    """Try to generate an image via google-genai API. Returns True on success."""
    try:
        from google.genai import types

        print(f"  [api] Calling model={model}")
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
            ),
        )

        # Extract image data
        if response.candidates:
            for part in response.candidates[0].content.parts:
                if hasattr(part, "inline_data") and part.inline_data and part.inline_data.mime_type.startswith("image/"):
                    image_bytes = part.inline_data.data
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_bytes(image_bytes)
                    size_kb = len(image_bytes) // 1024
                    print(f"  [saved] {output_path} ({size_kb} KB)")
                    return True

        # Check text response for clues
        text = getattr(response, "text", "") or ""
        if text:
            print(f"  [text-only] Model returned text (no image): {text[:120]}")
        return False

    except Exception as e:
        print(f"  [error] {e}")
        return False


IMAGES = [
    {
        "id": "mascot_v1",
        "output_path": "assets/mascot/mascot_v1.png",
        "placeholder_color": (78, 205, 196),  # mint
        "width": 512,
        "height": 512,
        "prompt": (
            "A cute cartoon AI bot rabbit mascot named NanoBunny. Friendly sitting rabbit character with "
            "mint green (#4ECDC4) and coral pink (#FF6B6B) color scheme. Big expressive round eyes with sparkle highlights. "
            "Small golden antenna on top of head with glowing tip. Subtle circuit board pattern on the ears. "
            "Soft rounded cartoon style, clean vector illustration look. Simple sitting pose with one paw raised "
            "in a friendly wave. White clean background. Flat design with gentle gradients, professional mascot quality. "
            "No text or lettering in the image. Style: kawaii cartoon, clean edges, pastel palette, mascot logo quality."
        ),
    },
    {
        "id": "mascot_wave_v1",
        "output_path": "assets/mascot/mascot_wave_v1.png",
        "placeholder_color": (255, 107, 107),  # coral
        "width": 512,
        "height": 512,
        "prompt": (
            "A cute cartoon AI bot rabbit mascot named NanoBunny in a happy standing pose with both arms raised "
            "in celebration/welcome. Mint green and coral pink color scheme. Big expressive eyes, small antenna. "
            "White background. Cartoon kawaii style, flat design, mascot quality. No text."
        ),
    },
    {
        "id": "mascot_think_v1",
        "output_path": "assets/mascot/mascot_think_v1.png",
        "placeholder_color": (200, 200, 220),  # soft purple-gray
        "width": 512,
        "height": 512,
        "prompt": (
            "A cute cartoon AI bot rabbit mascot named NanoBunny in a thinking pose — sitting with chin resting "
            "on one paw, eyes looking upward thoughtfully. Small thought bubble above head. Mint green and coral pink "
            "color scheme. Antenna with pulsing glow. White background. Kawaii cartoon style, flat design, "
            "professional mascot quality. No text."
        ),
    },
    {
        "id": "logo_primary_v1",
        "output_path": "assets/logo/logo_primary_v1.png",
        "placeholder_color": (26, 26, 46),  # dark navy
        "width": 1200,
        "height": 400,
        "prompt": (
            "A modern tech project logo for 'telegram-ai-org'. Horizontal banner format (3:1 ratio). "
            "Dark navy background (#1A1A2E). Left side has a small cute cartoon rabbit mascot icon in mint and coral colors. "
            "Right side shows the text 'telegram-ai-org' in clean white letters with electric blue (#4FC3F7) accent. "
            "Very faint circuit/network pattern in the background. Clean minimal tech aesthetic. "
            "Professional open source project banner quality. Style: modern developer tool branding, GitHub banner style."
        ),
    },
    {
        "id": "logo_square_v1",
        "output_path": "assets/logo/logo_square_v1.png",
        "placeholder_color": (26, 26, 46),  # dark navy
        "width": 512,
        "height": 512,
        "prompt": (
            "A square social preview icon for 'telegram-ai-org'. Dark navy background (#1A1A2E). "
            "Centered cute cartoon rabbit mascot NanoBunny in mint green and coral pink. "
            "Below the mascot: small text 'telegram-ai-org' in electric blue. "
            "Clean minimal tech style. Professional bot avatar quality."
        ),
    },
    {
        "id": "arch_diagram_v1",
        "output_path": "assets/diagrams/arch_diagram_v1.png",
        "placeholder_color": (240, 248, 255),  # light blue-white
        "width": 1920,
        "height": 1080,
        "prompt": (
            "A clean professional software architecture diagram on white background. "
            "Title: 'telegram-ai-org Multi-Agent Architecture'. "
            "Top-down hierarchy: PM Bot (blue center box) at top, "
            "six department boxes in middle row connected by arrows: Dev, Ops, Design, Planning, Growth, Research "
            "(each in different pastel color), "
            "three engine boxes at bottom: Claude Code (orange), Gemini CLI (blue), Codex (green). "
            "Arrows show flow PM Bot -> Departments -> Engines. Dotted lines show engine assignments. "
            "Style: clean corporate tech diagram, rounded boxes, colored arrows, subtle shadows, white background, "
            "English labels with Korean in parentheses."
        ),
    },
    {
        "id": "arch_diagram_v2",
        "output_path": "assets/diagrams/arch_diagram_v2.png",
        "placeholder_color": (240, 255, 240),  # light green-white
        "width": 1920,
        "height": 1080,
        "prompt": (
            "A clean engine assignment matrix diagram on white background. "
            "Title: 'Engine Assignment Matrix — telegram-ai-org'. "
            "Table layout: rows are 6 departments (Dev/개발실, Ops/운영실, Design/디자인실, Planning/기획실, "
            "Growth/성장실, Research/리서치실), columns are 3 engines (Claude Code, Gemini CLI, Codex). "
            "Filled colored circles show primary assignment: Dev/Design/Planning/PM use Claude Code (orange), "
            "Ops/Growth/Research use Gemini CLI (blue), all can use Codex (green, fallback). "
            "Feature comparison rows below: search capability, code reasoning, image generation, real-time web access. "
            "Style: clean data table, alternating row shading, icon indicators, professional documentation quality."
        ),
    },
]


def main() -> None:
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    image_model = "gemini-2.5-flash-image"

    # Try to import google-genai
    client = None
    if api_key:
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            print(f"[init] google-genai client ready, model={image_model}")
        except Exception as e:
            print(f"[init] Failed to init google-genai client: {e}")
    else:
        print("[init] No GEMINI_API_KEY found, will use placeholders only")

    results = []

    for img in IMAGES:
        img_id = img["id"]
        output_path = PROJECT_ROOT / img["output_path"]
        color = img["placeholder_color"]
        w, h = img.get("width", 512), img.get("height", 512)

        print(f"\n[{img_id}] -> {output_path}")

        success = False
        real_image = False

        if client:
            print(f"  Attempting API generation...")
            success = try_generate_image(client, image_model, img["prompt"], output_path)
            if success:
                real_image = True
                print(f"  [OK] Real image generated!")
            else:
                print(f"  API generation failed, creating placeholder...")

        if not success:
            create_placeholder_png(output_path, w, h, color)
            success = True

        results.append({
            "id": img_id,
            "path": str(output_path),
            "real": real_image,
            "success": success,
        })

        # Rate limit protection
        if client and real_image and img != IMAGES[-1]:
            print("  Waiting 3s for rate limit...")
            time.sleep(3)

    # Summary
    print("\n" + "=" * 60)
    print("GENERATION SUMMARY")
    print("=" * 60)
    real = [r for r in results if r["real"]]
    placeholder = [r for r in results if not r["real"]]
    print(f"Real images generated: {len(real)}/{len(results)}")
    for r in real:
        print(f"  REAL     {r['id']} -> {r['path']}")
    print(f"Placeholders created: {len(placeholder)}/{len(results)}")
    for r in placeholder:
        print(f"  PLACEHOLDER  {r['id']} -> {r['path']}")

    return results


if __name__ == "__main__":
    main()
