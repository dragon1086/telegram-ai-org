#!/usr/bin/env python3
"""tools/generate_assets.py

telegram-ai-org 프로젝트 시각 자산 일괄 생성 스크립트.
assets/asset_prompts.yaml 에서 설정을 읽어 Gemini 이미지 생성 모델로 이미지를 생성한다.

사용법:
    python tools/generate_assets.py                  # 전체 생성
    python tools/generate_assets.py --id logo        # ID 필터
    python tools/generate_assets.py --dry-run        # 설정만 출력 (생성 안 함)

인증: GEMINI_API_KEY 환경변수 (또는 .env 파일)
모델: gemini-2.5-flash-preview-image-generation (이미지 생성 전용 Preview 모델)
"""
from __future__ import annotations

import argparse
import base64
import os
import sys
import time
from pathlib import Path
from typing import Any

# .env 로드 (dotenv 있으면 사용)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml not installed. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

try:
    from google import genai
    from google.genai import types
    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False
    print("ERROR: google-genai not installed. Run: pip install google-genai", file=sys.stderr)
    sys.exit(1)


# ── 설정 ──────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.parent
PROMPTS_FILE = PROJECT_ROOT / "assets" / "asset_prompts.yaml"
IMAGE_MODEL = "gemini-3.1-flash-image-preview"   # gemini-3.1-flash 이미지 생성 모델 (2026-03-30 확인)
THINKING_MODEL = "gemini-2.5-flash"              # 프롬프트 정제용 thinking 모델
MAX_RETRIES = 3
RETRY_DELAY_SEC = 5


# ── 유틸 ──────────────────────────────────────────────────────────────────────

def load_config(path: Path) -> dict[str, Any]:
    """asset_prompts.yaml 로드."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_client() -> genai.Client:
    """Google Generative AI 클라이언트 초기화."""
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY 환경변수가 없습니다.", file=sys.stderr)
        sys.exit(1)
    return genai.Client(api_key=api_key)


def refine_prompt_with_thinking(client: genai.Client, raw_prompt: str, image_id: str) -> str:
    """Gemini Flash thinking mode로 프롬프트를 정제한다.

    실제 이미지 생성 전에 캐릭터 디자인 의도와 구도를 추론하게 한다.
    """
    meta_prompt = (
        f"You are an expert visual designer planning an image for '{image_id}'.\n"
        f"Analyze the following image description and rewrite it as a highly specific, "
        f"detailed image generation prompt that will produce the best possible result.\n"
        f"Focus on: composition, colors, style, lighting, key visual elements.\n"
        f"Keep the refined prompt under 300 words. Output only the refined prompt, no explanation.\n\n"
        f"Original description:\n{raw_prompt}"
    )
    try:
        response = client.models.generate_content(
            model=THINKING_MODEL,
            contents=meta_prompt,
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=1024),
                temperature=0.7,
            ),
        )
        refined = response.text.strip()
        print(f"  [thinking] 프롬프트 정제 완료 ({len(refined)} chars)")
        return refined
    except Exception as e:
        print(f"  [thinking] 정제 실패, 원본 사용: {e}")
        return raw_prompt


def generate_image(
    client: genai.Client,
    prompt: str,
    output_path: Path,
    image_id: str,
    use_thinking: bool = True,
) -> bool:
    """이미지를 생성하고 파일로 저장한다. 성공 여부 반환."""

    # thinking mode: 프롬프트 정제
    final_prompt = refine_prompt_with_thinking(client, prompt, image_id) if use_thinking else prompt

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"  [생성] 시도 {attempt}/{MAX_RETRIES} …")
            response = client.models.generate_content(
                model=IMAGE_MODEL,
                contents=final_prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE", "TEXT"],
                ),
            )

            # 응답에서 이미지 데이터 추출
            image_saved = False
            for part in response.candidates[0].content.parts:
                if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                    image_bytes = part.inline_data.data
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_bytes(image_bytes)
                    size_kb = len(image_bytes) // 1024
                    print(f"  [저장] {output_path} ({size_kb} KB)")
                    image_saved = True
                    break

            if image_saved:
                return True

            # 이미지 데이터가 없는 경우 (텍스트만 반환)
            print(f"  [경고] 이미지 데이터 없음. 응답 텍스트: {response.text[:100] if hasattr(response, 'text') else 'N/A'}")

        except Exception as e:
            print(f"  [오류] 시도 {attempt} 실패: {e}")

        if attempt < MAX_RETRIES:
            print(f"  {RETRY_DELAY_SEC}초 후 재시도 …")
            time.sleep(RETRY_DELAY_SEC)

    return False


# ── 메인 ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="telegram-ai-org 시각 자산 일괄 생성")
    parser.add_argument("--id", help="특정 이미지 ID만 생성 (예: nanobunny2_logo)")
    parser.add_argument("--dry-run", action="store_true", help="설정 출력만, 실제 생성 안 함")
    parser.add_argument(
        "--config",
        default=str(PROMPTS_FILE),
        help=f"설정 파일 경로 (기본: {PROMPTS_FILE})",
    )
    parser.add_argument(
        "--no-thinking",
        action="store_true",
        help="thinking mode 프롬프트 정제 건너뜀",
    )
    args = parser.parse_args()

    # 설정 로드
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"ERROR: 설정 파일 없음: {config_path}", file=sys.stderr)
        sys.exit(1)

    config = load_config(config_path)
    images = config.get("images", [])

    # ID 필터
    if args.id:
        images = [img for img in images if img.get("id") == args.id]
        if not images:
            print(f"ERROR: ID '{args.id}'를 찾을 수 없습니다.", file=sys.stderr)
            sys.exit(1)

    print(f"📋 생성 대상: {len(images)}개 이미지")
    print(f"📁 설정 파일: {config_path}")
    print()

    if args.dry_run:
        for img in images:
            print(f"  [{img['id']}] → {img['output_path']}")
            print(f"    model: {img.get('model', IMAGE_MODEL)}")
            print(f"    thinking: {img.get('thinking_mode', True)}")
            print(f"    prompt (첫 100자): {str(img.get('prompt', ''))[:100]}")
            print()
        print("dry-run 완료. 실제 생성하려면 --dry-run 없이 실행.")
        return

    # 클라이언트 초기화
    client = get_client()

    # 이미지 생성
    results: list[dict[str, Any]] = []
    for img in images:
        img_id = img.get("id", "unknown")
        output_path = PROJECT_ROOT / img["output_path"]
        use_thinking = img.get("thinking_mode", True) and not args.no_thinking

        print(f"🎨 [{img_id}] 생성 중 …")
        print(f"   출력: {output_path}")

        success = generate_image(
            client=client,
            prompt=str(img["prompt"]),
            output_path=output_path,
            image_id=img_id,
            use_thinking=use_thinking,
        )

        results.append({"id": img_id, "path": str(output_path), "success": success})
        print(f"   {'✅ 완료' if success else '❌ 실패'}")
        print()

        # API 레이트 리밋 방지
        if img != images[-1]:
            time.sleep(2)

    # 결과 요약
    print("=" * 60)
    print("📊 생성 결과 요약")
    print("=" * 60)
    ok = [r for r in results if r["success"]]
    fail = [r for r in results if not r["success"]]
    print(f"✅ 성공: {len(ok)}/{len(results)}")
    for r in ok:
        print(f"   {r['id']} → {r['path']}")
    if fail:
        print(f"❌ 실패: {len(fail)}")
        for r in fail:
            print(f"   {r['id']}")
    print()


if __name__ == "__main__":
    main()
