# Mascot Image Prompt Log
# assets/mascot/

**Generated**: 2026-04-01
**Model**: `gemini-2.5-flash-image`
**Tool**: `scripts/generate_assets_temp.py` (google-genai SDK v1.68.0)
**Status**: All 3 images generated successfully (real, not placeholders)

---

## mascot_v1.png — Primary Sitting Mascot

**File**: `assets/mascot/mascot_v1.png`
**Size**: ~970 KB
**Dimensions**: 512x512

### Prompt

```
A cute cartoon AI bot rabbit mascot named NanoBunny. Friendly sitting rabbit character with
mint green (#4ECDC4) and coral pink (#FF6B6B) color scheme. Big expressive round eyes with sparkle highlights.
Small golden antenna on top of head with glowing tip. Subtle circuit board pattern on the ears.
Soft rounded cartoon style, clean vector illustration look. Simple sitting pose with one paw raised
in a friendly wave. White clean background. Flat design with gentle gradients, professional mascot quality.
No text or lettering in the image. Style: kawaii cartoon, clean edges, pastel palette, mascot logo quality.
```

### Selection Reason
Primary mascot used in README header and main documentation. Sitting pose with waving paw conveys
friendliness and approachability — ideal for first impression.

---

## mascot_wave_v1.png — Celebration/Welcome Pose

**File**: `assets/mascot/mascot_wave_v1.png`
**Size**: ~993 KB
**Dimensions**: 512x512

### Prompt

```
A cute cartoon AI bot rabbit mascot named NanoBunny in a happy standing pose with both arms raised
in celebration/welcome. Mint green and coral pink color scheme. Big expressive eyes, small antenna.
White background. Cartoon kawaii style, flat design, mascot quality. No text.
```

### Selection Reason
Used for success/completion states in bot responses and onboarding completion screens.

---

## mascot_think_v1.png — Thinking/Processing Pose

**File**: `assets/mascot/mascot_think_v1.png`
**Size**: ~993 KB
**Dimensions**: 512x512

### Prompt

```
A cute cartoon AI bot rabbit mascot named NanoBunny in a thinking pose — sitting with chin resting
on one paw, eyes looking upward thoughtfully. Small thought bubble above head. Mint green and coral pink
color scheme. Antenna with pulsing glow. White background. Kawaii cartoon style, flat design,
professional mascot quality. No text.
```

### Selection Reason
Used for loading/processing states when the AI is thinking. The thought bubble reinforces the "AI reasoning" concept.

---

## Generation Notes

- **Model discovery**: `gemini-2.5-flash-preview-image-generation` returned 404; actual available model is `gemini-2.5-flash-image`
- **API**: google-genai SDK, `generateContent` with `response_modalities=["IMAGE", "TEXT"]`
- **Rate limiting**: 3 second delay between requests
- **All images**: PNG format, inline_data from API response

## Regeneration

```bash
python scripts/generate_assets_temp.py
# or for mascot only, filter in the script by commenting out other entries
```
