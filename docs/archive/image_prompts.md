# docs/image_prompts.md
# telegram-ai-org 시각 자료 생성 프롬프트 설계서
# Phase 2 산출물 — 3종 시각 자료 프롬프트 + 요구사항 정의
# 생성 모델: gemini-3.1-flash-image-preview (thinking mode 활성화)
# 작성일: 2026-03-30

---

## 설계 전략

### thinking mode 프롬프트 전략

정보밀도 높은 시각 자료를 생성하기 위해 2단계 프롬프트 파이프라인을 사용한다:

1. **1단계 (Thinking)**: `gemini-2.5-flash` thinking mode로 프롬프트를 분석·정제
   - 구도, 색상, 정보 계층을 추론
   - 핵심 시각 요소 우선순위 결정
   - 모델이 잘 해석할 수 있는 구체적 지시어로 변환

2. **2단계 (Generation)**: 정제된 프롬프트로 `gemini-3.1-flash-image-preview` 이미지 생성

### 톤앤매너 공통 원칙

| 항목 | 방향 |
|------|------|
| 배경 | 흰색 (#FFFFFF) 또는 아주 연한 그레이 (#F8F9FA) |
| 주요 컬러 | 인디고 (#4F46E5), 에메랄드 (#10B981), 앰버 (#F59E0B) |
| 폰트 스타일 | Sans-serif, 명확한 한국어+영어 레이블 |
| 스타일 | 플랫 디자인 + 미니멀 일러스트레이션 |
| 해상도 | 충분히 높은 품질 (PNG 출력) |

---

## Asset 1: 프로젝트 로고

### 요구사항 정의

| 항목 | 내용 |
|------|------|
| 목적/용도 | README 헤더, GitHub 리포지토리 대표 이미지, 텔레그램 봇 프로필 |
| 권장 해상도 | 1024×1024 (정사각형) |
| 포맷 | PNG (투명 배경 호환) |
| 핵심 정보 | 프로젝트명 "telegram-ai-org", AI 멀티봇 조직 개념, 나노바나나2 마스코트 |
| 디자인 톤 | 귀엽고 미래적, 밝은 노랑+인디고, 디지털 회로 패턴 |

### 생성 프롬프트

```
output_path: assets/logo.png
model: gemini-3.1-flash-image-preview
thinking_mode: true
width: 1024
height: 1024
```

**프롬프트 (English for best quality):**

```
A professional project logo for an open-source AI multi-bot organization platform called "telegram-ai-org".

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
Output: 1024x1024, high-resolution PNG suitable for both light and dark backgrounds.
```

---

## Asset 2: 아키텍처 다이어그램

### 요구사항 정의

| 항목 | 내용 |
|------|------|
| 목적/용도 | README 아키텍처 섹션, 기술 문서, 발표 자료 |
| 권장 해상도 | 1920×1080 (16:9 와이드) |
| 포맷 | PNG |
| 핵심 정보 | PM봇 → 6개 조직봇 → 3엔진(Claude Code/Gemini CLI/Codex) 계층 구조, 엔진 배정 관계 |
| 디자인 톤 | 깔끔한 기업용 다이어그램, 정보밀도 높음, 한국어+영어 혼용 레이블 |

### 생성 프롬프트

```
output_path: assets/architecture_diagram.png
model: gemini-3.1-flash-image-preview
thinking_mode: true
width: 1920
height: 1080
```

**프롬프트 (English for best quality):**

```
A clean, professional software architecture diagram for a multi-bot AI organization platform.
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
- Small checkmark (✓) badges on department→engine connections showing primary assignment

Style: Clean corporate tech diagram, Notion/Miro aesthetic, readable at 1920x1080.
No decorative elements. Pure information design.
```

---

## Asset 3: 온보딩 배너

### 요구사항 정의

| 항목 | 내용 |
|------|------|
| 목적/용도 | README 온보딩 섹션 헤더, GitHub 소셜 프리뷰 이미지, 문서 배너 |
| 권장 해상도 | 1280×640 (2:1 배너 비율) |
| 포맷 | PNG |
| 핵심 정보 | 원클릭 설치(setup.sh), 3엔진 자동 감지, 텔레그램 봇 즉시 사용 가능 3단계 메시지 |
| 디자인 톤 | 친근하고 초대적인 톤, 오픈소스 프로젝트 웰컴 배너 스타일 |

### 생성 프롬프트

```
output_path: assets/onboarding_banner.png
model: gemini-3.1-flash-image-preview
thinking_mode: true
width: 1280
height: 640
```

**프롬프트 (English for best quality):**

```
A friendly, welcoming onboarding banner for an open-source AI multi-bot Telegram platform.
Landscape format 1280x640, banner style. White/very light gray background.

TOP SECTION:
  Large centered headline text: "telegram-ai-org"
  Subtitle: "AI 멀티봇 조직 플랫폼 · 원클릭 설치"
  English sub-subtitle: "Multi-Bot AI Organization · One-Click Setup"
  Small NanoBunny2 mascot icon (cute banana robot) on the left side of the headline.

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
  Gradient accents on step cards (blue → indigo → emerald left to right).
  Professional open-source project aesthetic (like GitHub's social preview style).
  Korean and English text mixed naturally. Clear visual hierarchy.
```

---

## 생성 파라미터 요약

| Asset | 출력 경로 | 모델 | 해상도 | Thinking |
|-------|-----------|------|--------|---------|
| 로고 | `assets/logo.png` | gemini-3.1-flash-image-preview | 1024×1024 | ✅ |
| 아키텍처 다이어그램 | `assets/architecture_diagram.png` | gemini-3.1-flash-image-preview | 1920×1080 | ✅ |
| 온보딩 배너 | `assets/onboarding_banner.png` | gemini-3.1-flash-image-preview | 1280×640 | ✅ |
