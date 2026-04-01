#!/usr/bin/env python3
"""봇 캐릭터 이미지 생성 스크립트.

gemini-3.1-flash-image-preview 모델을 사용해 6개 봇 캐릭터 PNG를 생성한다.
이미지 생성 실패 시 스킵하며, 대시보드는 emoji fallback으로 동작한다.
"""

import base64
import os
import shutil
from pathlib import Path

# .env 로드 (python-dotenv 없으면 수동 파싱)
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

OUT_DIR = Path(__file__).parent.parent / "core" / "api" / "static" / "chars"
OUT_DIR.mkdir(parents=True, exist_ok=True)

MODEL = "gemini-3.1-flash-image-preview"

BOTS: list[tuple[str, str]] = [
    (
        "pm",
        "A cartoon robot PM manager in a dark navy suit, holding a clipboard with glowing todo items, "
        "confident expression, hexagon badge on chest, flat vector style, transparent background",
    ),
    (
        "engineering",
        "A cartoon robot engineer with a gear-shaped head, wearing a dark hoodie, holding a wrench that "
        "glows blue, focused expression, flat vector style, transparent background",
    ),
    (
        "design",
        "A cartoon robot designer with a paintbrush and color palette, wearing a beret, bright creative "
        "expression, flat vector style, pastel color accents, transparent background",
    ),
    (
        "growth",
        "A cartoon robot marketer holding a rocket and bar chart, energetic pose, wearing a blazer, "
        "flat vector style, orange accent colors, transparent background",
    ),
    (
        "research",
        "A cartoon robot researcher with a magnifying glass and floating data charts around them, "
        "thoughtful expression, lab coat, flat vector style, transparent background",
    ),
    (
        "ops",
        "A cartoon robot ops engineer monitoring screens, multiple small displays around them, calm "
        "focused expression, dark uniform, flat vector style, transparent background",
    ),
]


def generate_via_sdk(name: str, prompt: str, out_path: Path) -> bool:
    """google-genai SDK로 이미지 생성 시도."""
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        print(f"[SKIP] google-genai SDK not available for {name}")
        return False

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print(f"[SKIP] No GEMINI_API_KEY / GOOGLE_API_KEY for {name}")
        return False

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=f"models/{MODEL}",
            contents=f"Generate an image: {prompt}",
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"]
            ),
        )
        for part in response.candidates[0].content.parts:
            if hasattr(part, "inline_data") and part.inline_data:
                data = part.inline_data.data
                if isinstance(data, str):
                    data = base64.b64decode(data)
                out_path.write_bytes(data)
                print(f"[OK] {name}.png saved via SDK")
                return True
        print(f"[WARN] No image data in SDK response for {name}")
    except Exception as e:
        print(f"[WARN] SDK error for {name}: {e}")
    return False


def generate_via_cli(name: str, prompt: str, out_path: Path) -> bool:
    """gemini CLI subprocess로 이미지 생성 시도."""
    import glob as _glob
    import subprocess

    gemini_bin = os.environ.get("GEMINI_CLI_PATH", "/opt/homebrew/bin/gemini")
    if not Path(gemini_bin).exists():
        print(f"[SKIP] gemini CLI not found at {gemini_bin}")
        return False

    full_prompt = f"Generate an image: {prompt}"
    work_dir = OUT_DIR

    try:
        result = subprocess.run(
            [gemini_bin, "-m", MODEL, full_prompt],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(work_dir),
        )
        # CLI가 현재 디렉토리에 PNG 저장할 수 있음
        new_pngs = (
            _glob.glob(str(work_dir / "*.png"))
            + _glob.glob(str(work_dir / "image*.png"))
            + _glob.glob(str(work_dir / "generated*.png"))
        )
        # out_path 자체가 이미 생성됐을 수도 있음
        if out_path.exists():
            print(f"[OK] {name}.png saved via CLI")
            return True
        for p in new_pngs:
            if Path(p) != out_path:
                shutil.move(p, str(out_path))
                print(f"[OK] {name}.png moved from {p}")
                return True
        print(
            f"[WARN] CLI ran but no PNG found for {name}. "
            f"stdout: {result.stdout[:200]!r} stderr: {result.stderr[:200]!r}"
        )
    except subprocess.TimeoutExpired:
        print(f"[WARN] CLI timeout for {name}")
    except Exception as e:
        print(f"[WARN] CLI error for {name}: {e}")
    return False


def generate_image(name: str, prompt: str) -> bool:
    """SDK → CLI 순서로 시도."""
    out_path = OUT_DIR / f"{name}.png"
    if out_path.exists():
        print(f"[SKIP] {name}.png already exists")
        return True
    # SDK 우선
    if generate_via_sdk(name, prompt, out_path):
        return True
    # CLI fallback
    if generate_via_cli(name, prompt, out_path):
        return True
    print(f"[FALLBACK] {name} — emoji placeholder will be used in dashboard")
    return False


def main() -> None:
    print(f"Output directory: {OUT_DIR}")
    print(f"Model: {MODEL}\n")
    results = []
    for bot_name, bot_prompt in BOTS:
        ok = generate_image(bot_name, bot_prompt)
        results.append((bot_name, ok))

    print("\n── 결과 요약 ──")
    for bot_name, ok in results:
        status = "OK" if ok else "FALLBACK(emoji)"
        print(f"  {bot_name:15s}: {status}")

    generated = sum(1 for _, ok in results if ok)
    print(f"\n{generated}/{len(BOTS)} 이미지 생성 완료")
    if generated < len(BOTS):
        print("생성 실패한 봇은 대시보드에서 emoji로 자동 표시됩니다.")


if __name__ == "__main__":
    main()
