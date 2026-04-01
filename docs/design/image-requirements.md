# Image Generation Requirements
# telegram-ai-org Visual Assets — Phase 4 Mascot & Brand Extension

**Created**: 2026-04-01
**Model**: gemini-2.5-flash-preview-image-generation
**Tool**: tools/generate_assets.py + google-genai SDK

---

## Overview

This document defines requirements and prompts for three new image categories:
1. NanoBunny mascot character set (assets/mascot/)
2. Project logo variants (assets/logo/)
3. Architecture diagram updates (assets/diagrams/)

---

## Image 1: NanoBunny Mascot Character

**Target path**: `assets/mascot/mascot_v1.png`
**Dimensions**: 1024x1024 (1:1 aspect ratio)
**Format**: PNG with white background

### Design Spec

- **Character**: Cute cartoon rabbit AI bot — "NanoBunny"
- **Style**: Cartoon, flat illustration with subtle gradients
- **Colors**: Mint (#4ECDC4), Coral (#FF6B6B), White (#FFFFFF), soft gray accent
- **Pose**: Sitting upright, friendly expression, one paw raised in wave
- **Details**: Small antenna on head with glowing tip, circuit board pattern subtly visible on ears
- **Background**: Clean white or transparent-ready white

### Generation Prompt

```
A cute cartoon AI bot rabbit mascot named NanoBunny. Friendly sitting rabbit character with:
- Mint green (#4ECDC4) and coral pink (#FF6B6B) color scheme
- Big expressive round eyes with sparkle highlights
- Small golden antenna on top of head with glowing tip
- Subtle circuit board pattern on the ears
- Soft rounded cartoon style, clean vector illustration look
- Simple sitting pose with one paw raised in a friendly wave
- White clean background
- Flat design with gentle gradients, professional mascot quality
- No text or lettering in the image
Style: kawaii cartoon, clean edges, pastel palette, mascot logo quality
```

### Variants

| File | Pose | Use Case |
|------|------|----------|
| `mascot_v1.png` | Sitting, waving | Primary mascot, README header |
| `mascot_wave_v1.png` | Standing, both arms raised | Welcome/success state |
| `mascot_think_v1.png` | Sitting, chin on paw, thinking | Processing/loading state |

---

## Image 2: Project Logo

**Target path**: `assets/logo/logo_primary_v1.png`
**Dimensions**: 1200x400 (horizontal, 3:1 ratio)
**Format**: PNG

### Design Spec

- **Text**: "telegram-ai-org"
- **Style**: Modern tech, minimal, dark theme
- **Colors**: Dark background (#1A1A2E), electric blue accent (#4FC3F7), white text
- **Layout**: Horizontal — small NanoBunny icon on left, text on right
- **Font style**: Clean sans-serif, monospace hint for tech feel

### Generation Prompt

```
A modern tech project logo for "telegram-ai-org". Horizontal format (3:1 ratio):
- Dark navy background (#1A1A2E)
- Left side: small cute rabbit mascot icon in mint and coral colors
- Right side: "telegram-ai-org" text in clean white with electric blue (#4FC3F7) accent
- Subtle circuit/network pattern in background (very faint)
- Clean minimal tech aesthetic
- Professional open source project logo quality
- No gradients on text, crisp and readable
Style: modern developer tool branding, GitHub project banner style
```

### Variants

| File | Format | Use Case |
|------|--------|----------|
| `logo_primary_v1.png` | 1200x400 horizontal | README header, GitHub banner |
| `logo_square_v1.png` | 512x512 square | Social preview, bot avatar |

---

## Image 3: Architecture Diagram

**Target path**: `assets/diagrams/arch_diagram_v1.png`
**Dimensions**: 1920x1080
**Format**: PNG

### Design Spec

- **Content**: Multi-agent AI organization system
- **Elements**: 6 department bots + PM bot + 3 engine types
- **Style**: Clean technical diagram, light background
- **Layout**: Top-down hierarchy flow

### Generation Prompt

```
A clean professional software architecture diagram on white background.
Title: "telegram-ai-org Multi-Agent Architecture"

Layout (top to bottom):
TOP: Single box "PM Bot" (blue, center)
MIDDLE: Six department boxes connected from PM Bot:
  - Dev (개발실) — orange
  - Ops (운영실) — green
  - Design (디자인실) — pink
  - Planning (기획실) — purple
  - Growth (성장실) — teal
  - Research (리서치실) — yellow
BOTTOM: Three engine boxes:
  - Claude Code — warm orange
  - Gemini CLI — blue
  - Codex — green

Arrows show clear flow: PM Bot → Departments → Engines
Dotted lines show which departments use which engine.
Style: clean corporate tech diagram, rounded rectangle boxes, colored arrows,
subtle drop shadows, white background, professional documentation quality.
English and Korean labels (Korean in parentheses).
```

### Variants

| File | Content | Use Case |
|------|---------|----------|
| `arch_diagram_v1.png` | Full architecture overview | README, documentation |
| `arch_diagram_v2.png` | Engine assignment matrix | Technical docs |

---

## Quality Criteria

| Criterion | Requirement |
|-----------|-------------|
| Resolution | Minimum 512x512 for mascot, 1024+ for diagrams |
| File size | Under 2MB per image |
| Background | Clean white (no artifacts) |
| Style consistency | Consistent color palette across all assets |
| Text readability | All text (if any) must be legible at 100% zoom |
| No watermarks | Clean output, no AI watermarks |

---

## Regeneration Command

```bash
# Full regeneration
python tools/generate_assets.py

# Mascot only
python tools/generate_assets.py --id mascot_v1

# Dry run to check config
python tools/generate_assets.py --dry-run
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| v1.0 | 2026-04-01 | Initial mascot + logo + diagram requirements |
