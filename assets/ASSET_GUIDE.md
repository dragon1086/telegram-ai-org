# Asset Usage Guide
# telegram-ai-org Visual Assets

**Last Updated**: 2026-04-01

---

## Overview

This guide explains how to use, regenerate, and extend the visual assets in this directory.

---

## Asset Categories

### 1. Mascot (assets/mascot/)

The NanoBunny mascot is a cute cartoon rabbit AI bot character with mint green (#4ECDC4)
and coral pink (#FF6B6B) color scheme.

| File | Use Case | When to Use |
|------|----------|-------------|
| `mascot_v1.png` | README header, main brand identity | Default mascot display |
| `mascot_wave_v1.png` | Success messages, welcome screens | Bot task completed successfully |
| `mascot_think_v1.png` | Loading states, processing indicators | Bot is working on a task |

**In README.md**:
```markdown
![NanoBunny Mascot](assets/mascot/mascot_v1.png)
```

**In Telegram bot responses** (as a sticker/image):
```python
await bot.send_photo(chat_id, photo=open("assets/mascot/mascot_wave_v1.png", "rb"))
```

---

### 2. Logo (assets/logo/)

| File | Dimensions | Use Case |
|------|------------|----------|
| `logo_primary_v1.png` | ~1200x400 | README header banner, GitHub social preview |
| `logo_square_v1.png` | ~512x512 | Telegram bot profile picture, social icons |
| `nanobunny2_logo.png` | 1024x1024 | Legacy mascot logo |
| `nanobunny2_logo_sm.png` | 256x256 | Small icon, favicon |

**GitHub Social Preview**: Upload `logo_primary_v1.png` to repository Settings > Social preview.

**Telegram Bot Avatar**: Use `logo_square_v1.png` — upload via BotFather or
`bot.set_chat_photo()`.

---

### 3. Architecture Diagrams (assets/diagrams/)

| File | Content | Use Case |
|------|---------|----------|
| `arch_diagram_v1.png` | Full system hierarchy | README architecture section |
| `arch_diagram_v2.png` | Engine assignment matrix | Technical documentation |
| `architecture_diagram.png` | Original overview | Legacy reference |
| `architecture_overview.png` | Detailed overview | Documentation |
| `engine_compat.png` | Engine compatibility | Engine selection guide |

**In README.md**:
```markdown
## Architecture
![Architecture](assets/diagrams/arch_diagram_v1.png)
```

---

### 4. Onboarding (assets/onboarding/)

| File | Content | Use Case |
|------|---------|----------|
| `install_flow.png` | 4-step installation | Getting started guide |
| `skill_guide.png` | Skill directory structure | Contributor guide |
| `e2e_flow.png` | E2E test flow | Testing documentation |

---

## Color Palette

| Name | Hex | Usage |
|------|-----|-------|
| Mint | `#4ECDC4` | NanoBunny primary color, success states |
| Coral | `#FF6B6B` | NanoBunny accent, warning states |
| Navy | `#1A1A2E` | Logo dark background |
| Electric Blue | `#4FC3F7` | Text accent, links |
| White | `#FFFFFF` | Clean backgrounds |

---

## Regenerating Images

### Prerequisites
```bash
# Ensure GEMINI_API_KEY is set in .env
grep GEMINI_API_KEY .env
```

### Phase 3 images (original set)
```bash
python tools/generate_assets.py          # all
python tools/generate_assets.py --id nanobunny2_logo
python tools/generate_assets.py --dry-run
```

### Phase 4 images (mascot + new logo + new diagrams)
```bash
python scripts/generate_assets_temp.py
```

### Single image regeneration (quick Python snippet)
```python
from google import genai
from google.genai import types
import os

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
response = client.models.generate_content(
    model="gemini-2.5-flash-image",
    contents="Your prompt here...",
    config=types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
)
for part in response.candidates[0].content.parts:
    if part.inline_data and part.inline_data.mime_type.startswith("image/"):
        open("output.png", "wb").write(part.inline_data.data)
```

---

## Image Prompt Logs

Each subdirectory contains a `PROMPT_LOG.md` with the exact prompts used:

- `assets/mascot/PROMPT_LOG.md` — NanoBunny character prompts
- `assets/logo/PROMPT_LOG.md` — Logo generation prompts
- `assets/diagrams/PROMPT_LOG.md` — Architecture diagram prompts

Refer to these when regenerating to reproduce the same style.

---

## Adding New Assets

1. Add entry to `assets/asset_prompts.yaml` (for `tools/generate_assets.py`) or
   add to the `IMAGES` list in `scripts/generate_assets_temp.py`
2. Document the prompt in the relevant `PROMPT_LOG.md`
3. Update `assets/README.md` directory tree and file table
4. Update this guide if a new category is added

---

## Model Reference

| Model | Status | Use For |
|-------|--------|---------|
| `gemini-2.5-flash-image` | Active (2026-04-01) | All image generation |
| `gemini-3.1-flash-image-preview` | Active (in asset_prompts.yaml) | Phase 3 assets |
| `gemini-2.5-flash-preview-image-generation` | 404 Not Found | Do NOT use |
| `imagen-4.0-generate-001` | Available (predict API) | Alternative for higher quality |
