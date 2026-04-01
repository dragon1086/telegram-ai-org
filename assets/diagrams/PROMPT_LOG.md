# Architecture Diagram Prompt Log
# assets/diagrams/

**Generated**: 2026-04-01
**Model**: `gemini-2.5-flash-image`
**Tool**: `scripts/generate_assets_temp.py` (google-genai SDK v1.68.0)
**Status**: Both new diagrams generated successfully (real, not placeholders)

---

## arch_diagram_v1.png — Full Architecture Overview

**File**: `assets/diagrams/arch_diagram_v1.png`
**Size**: ~996 KB
**Dimensions**: 1920x1080 (target)

### Prompt

```
A clean professional software architecture diagram on white background.
Title: 'telegram-ai-org Multi-Agent Architecture'.

Layout (top to bottom):
TOP: Single box 'PM Bot' (blue, center)
MIDDLE: Six department boxes connected by arrows from PM Bot:
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

Arrows show flow PM Bot -> Departments -> Engines.
Dotted lines show which departments use which engine.
Style: clean corporate tech diagram, rounded boxes, colored arrows, subtle shadows, white background,
English labels with Korean in parentheses.
```

### Content Description
Shows the full multi-agent hierarchy: PM Bot orchestrates 6 department bots, each connected
to one or more of 3 AI engine backends. Top-down layout emphasizes the command/dispatch flow.

### Use Cases
- README.md architecture section
- Technical documentation
- Conference presentations
- Onboarding materials

---

## arch_diagram_v2.png — Engine Assignment Matrix

**File**: `assets/diagrams/arch_diagram_v2.png`
**Size**: ~1009 KB
**Dimensions**: 1920x1080 (target)

### Prompt

```
A clean engine assignment matrix diagram on white background.
Title: 'Engine Assignment Matrix — telegram-ai-org'.

Table layout: rows are 6 departments (Dev/개발실, Ops/운영실, Design/디자인실, Planning/기획실,
Growth/성장실, Research/리서치실), columns are 3 engines (Claude Code, Gemini CLI, Codex).
Filled colored circles show primary assignment:
  - Dev/Design/Planning/PM -> Claude Code (orange)
  - Ops/Growth/Research -> Gemini CLI (blue)
  - All departments -> Codex (green, fallback)
Feature comparison rows below: search capability, code reasoning, image generation, real-time web access.
Style: clean data table, alternating row shading, icon indicators, professional documentation quality.
```

### Content Description
Matrix view of which AI engine each department uses as primary. Includes feature comparison
to explain WHY each assignment was made (e.g., Gemini CLI for departments needing real-time web search).

### Use Cases
- Technical documentation explaining engine selection
- Contributor guide
- Configuration reference

---

## Pre-existing Diagram Files

| File | Status | Notes |
|------|--------|-------|
| `architecture_diagram.png` | Pre-existing (2026-03-30) | Original architecture diagram |
| `architecture_overview.png` | Pre-existing (2026-03-30) | Listed in README but may not exist |
| `engine_compat.png` | Pre-existing (2026-03-30) | Engine compatibility chart |

The new `arch_diagram_v1.png` and `arch_diagram_v2.png` are updated versions with improved
visual design and updated engine assignments (Ops/Growth/Research now use Gemini CLI,
reflecting the 2026-03-26 migration from Codex).

---

## Generation Notes

- Model: `gemini-2.5-flash-image` (confirmed working 2026-04-01)
- Actual output dimensions controlled by model; 1920x1080 specified in prompt as target
- Both English and Korean labels requested to support international contributors
