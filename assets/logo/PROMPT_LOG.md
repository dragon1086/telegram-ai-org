# Logo Image Prompt Log
# assets/logo/

**Generated**: 2026-04-01
**Model**: `gemini-2.5-flash-image`
**Tool**: `scripts/generate_assets_temp.py` (google-genai SDK v1.68.0)
**Status**: Both images generated successfully (real, not placeholders)

---

## logo_primary_v1.png — Horizontal Banner Logo

**File**: `assets/logo/logo_primary_v1.png`
**Size**: ~915 KB
**Dimensions**: 1200x400

### Prompt

```
A modern tech project logo for 'telegram-ai-org'. Horizontal banner format (3:1 ratio).
Dark navy background (#1A1A2E). Left side has a small cute cartoon rabbit mascot icon in mint and coral colors.
Right side shows the text 'telegram-ai-org' in clean white letters with electric blue (#4FC3F7) accent.
Very faint circuit/network pattern in the background. Clean minimal tech aesthetic.
Professional open source project banner quality. Style: modern developer tool branding, GitHub banner style.
```

### Selection Reason
Primary logo used in README.md header, GitHub repository social preview, and official documentation.
Dark background provides high contrast for readability. NanoBunny icon on left provides brand continuity.

### Use Cases
- README.md header image
- GitHub social preview (1200x630 crop)
- Project landing page header

---

## logo_square_v1.png — Square Social/Avatar Logo

**File**: `assets/logo/logo_square_v1.png`
**Size**: ~937 KB
**Dimensions**: 512x512

### Prompt

```
A square social preview icon for 'telegram-ai-org'. Dark navy background (#1A1A2E).
Centered cute cartoon rabbit mascot NanoBunny in mint green and coral pink.
Below the mascot: small text 'telegram-ai-org' in electric blue. Clean minimal tech style.
Professional bot avatar quality.
```

### Selection Reason
Square format optimized for Telegram bot avatar (512x512 is the standard bot profile picture size).
Also usable as GitHub profile picture and social media icon.

### Use Cases
- Telegram bot profile picture
- GitHub organization avatar
- NPM package icon
- Discord server icon

---

## Pre-existing Logo Files

| File | Status | Notes |
|------|--------|-------|
| `nanobunny2_logo.png` | Pre-existing (2026-03-30) | Original mascot, banana-robot concept |
| `nanobunny2_logo_sm.png` | Pre-existing (2026-03-30) | Small icon version |

The new `logo_primary_v1.png` and `logo_square_v1.png` use the NanoBunny rabbit concept
(mint+coral palette) which is distinct from the original NanoBunny2 banana-robot character.

---

## Generation Notes

- Model: `gemini-2.5-flash-image` (confirmed working 2026-04-01)
- The 1200x400 aspect ratio was specified in the prompt; actual output dimensions depend on model
- Electric blue (#4FC3F7) accent color from brand tokens (docs/design/tokens.css)
