# telegram-ai-org 시각 자산 (Assets)

이 디렉토리는 프로젝트의 로고, 아키텍처 다이어그램, 온보딩 시각 자료를 포함합니다.

생성일: 2026-03-30
생성 모델: `gemini-3.1-flash-image-preview` (thinking mode 적용, gemini-2.5-flash 프롬프트 정제)
재생성 명령: `python scripts/generate_assets.py`

---

## Phase 3 핵심 자산 (2026-03-30 신규 생성)

| 파일 | 용도 | 크기 | 모델 |
|------|------|------|------|
| `logo.png` | README 헤더, GitHub 리포 대표 이미지, 봇 프로필 | 548 KB | gemini-3.1-flash-image-preview |
| `architecture_diagram.png` | README 아키텍처 섹션, 기술 문서 | 510 KB | gemini-3.1-flash-image-preview |
| `onboarding_banner.png` | README 온보딩 헤더, GitHub 소셜 프리뷰 | 422 KB | gemini-3.1-flash-image-preview |

품질 검토: [`quality_check.md`](quality_check.md) — 3/3 PASS

---

## 디렉토리 구조

```
assets/
├── logo/
│   ├── nanobunny2_logo.png      # 나노바나나2 캐릭터 로고 (1024x1024)
│   └── nanobunny2_logo_sm.png   # 소형 아이콘 버전 (256x256)
├── diagrams/
│   ├── architecture_overview.png  # 멀티봇 전체 아키텍처 다이어그램
│   └── engine_compat.png          # 3엔진 호환 매트릭스
└── onboarding/
    ├── install_flow.png    # 설치 흐름 인포그래픽
    ├── skill_guide.png     # 스킬 추가 가이드 일러스트
    └── e2e_flow.png        # E2E 테스트 흐름도
```

---

## 파일별 상세

### 로고 (logo/)

| 파일 | 용도 | 크기 |
|------|------|------|
| `nanobunny2_logo.png` | README, 공식 문서, SNS 프로필 | ~376 KB |
| `nanobunny2_logo_sm.png` | Telegram 봇 아이콘, 파비콘 | ~342 KB |

**캐릭터 컨셉**: 나노바나나2 — 귀엽고 미래지향적인 AI 조직 봇 마스코트.
노란색 바나나 로봇 몸체, 반짝이는 파란 눈, 안테나, 디지털 회로 패턴 장식.

---

### 아키텍처 다이어그램 (diagrams/)

| 파일 | 용도 | 크기 |
|------|------|------|
| `architecture_overview.png` | 전체 멀티봇 조직 구조 설명 | ~371 KB |
| `engine_compat.png` | 3엔진 호환 구조 및 조직별 배정 매트릭스 | ~343 KB |

**아키텍처 내용**: PM봇 → 6개 조직(개발/운영/디자인/기획/성장/리서치) → 3엔진(Claude Code / Gemini CLI / Codex)

---

### 온보딩 시각 자료 (onboarding/)

| 파일 | 용도 | 크기 |
|------|------|------|
| `install_flow.png` | 신규 기여자 설치 4단계 인포그래픽 | ~400 KB |
| `skill_guide.png` | skills/ 디렉토리 구조 및 스킬 추가 방법 | ~289 KB |
| `e2e_flow.png` | E2E 테스트 흐름도 (7단계) | ~450 KB |

**대상 독자**: 오픈소스 신규 기여자, 처음 설치하는 사용자

---

## 재생성 방법

### 전체 재생성
```bash
python tools/generate_assets.py
```

### 특정 이미지만 재생성
```bash
python tools/generate_assets.py --id nanobunny2_logo
python tools/generate_assets.py --id architecture_overview
python tools/generate_assets.py --id install_flow
```

### 설정 확인 (생성 없이)
```bash
python tools/generate_assets.py --dry-run
```

### Thinking mode 건너뜀 (빠른 재생성)
```bash
python tools/generate_assets.py --no-thinking
```

---

## 생성 모델 정보

| 항목 | 값 |
|------|-----|
| 이미지 생성 모델 | `gemini-3.1-flash-image-preview` |
| 프롬프트 정제 모델 | `gemini-2.5-flash` (thinking_budget=1024) |
| 인증 방식 | `GEMINI_API_KEY` 환경변수 |
| 설정 파일 | `assets/asset_prompts.yaml` |

> **참고**: 모델명은 API 업데이트에 따라 변경될 수 있습니다.
> `python -c "from google import genai; [print(m.name) for m in genai.Client(...).models.list()]"` 로 최신 목록을 확인하세요.

---

## 프롬프트 수정

`assets/asset_prompts.yaml` 에서 각 이미지의 프롬프트·모델·thinking_mode를 수정할 수 있습니다.

```yaml
images:
  - id: nanobunny2_logo
    output_path: assets/logo/nanobunny2_logo.png
    model: gemini-3.1-flash-image-preview
    thinking_mode: true
    prompt: |
      수정할 프롬프트 내용...
```

수정 후 `python tools/generate_assets.py --id nanobunny2_logo` 로 해당 이미지만 재생성.
