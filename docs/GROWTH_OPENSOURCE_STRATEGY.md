# GROWTH_OPENSOURCE_STRATEGY.md — aimesh 오픈소스 기여자 유입 전략

> 작성일: 2026-03-31 | 성장실 | telegram-ai-org v1.x

---

## 1. 전략 요약

README 전면 개편(마스코트·배지·이미지·기여자 가이드 통합)을 통해 **GitHub 첫 방문자의 설치 전환율과 기여자 유입률을 동시에 높이는** 단기 성장 전략입니다.

핵심 가정: "좋은 README는 최고의 마케팅 채널이다." — 프로젝트 첫인상이 Star/Fork/기여 여부를 결정합니다.

---

## 2. 측정 지표 (KPI)

### 2-1. 핵심 성과 지표

| 지표 | 측정 방법 | 단기 목표 (1개월) | 중기 목표 (3개월) |
|------|-----------|-------------------|-------------------|
| **GitHub Stars** | 리포지토리 stars 카운트 | +50 → 누적 100 | +200 → 누적 300 |
| **Fork 수** | 리포지토리 forks 카운트 | +20 | +60 |
| **이슈 오픈 수** | Issues 탭 total open | 10~20개 (활성도 지표) | 20~50개 유지 |
| **이슈 클로즈 비율** | closed/total | 60%+ | 75%+ |
| **PR 기여자 수** | unique PR authors | 5명 | 20명 |
| **README 클릭→설치 전환율** | (추정) install.sh curl 실행 수 / README 조회 수 | 3% | 8% |
| **Watch 수** | Watchers 카운트 | +30 | +80 |

### 2-2. 설치 전환 퍼널 (예상)

```
GitHub 검색/링크 방문 (100%)
  ↓ README 읽기 완료 (40%)        ← README 개편으로 개선 타겟
  ↓ Quick Start 시도 (15%)        ← install.sh 원클릭으로 마찰 최소화
  ↓ .env 설정 완료 (8%)           ← 봇 토큰 가이드 명확화로 개선
  ↓ 첫 봇 실행 성공 (5%)
  ↓ Star 누름 (3%)
  ↓ Fork 또는 기여 (0.5%)
```

**README 개편 예상 효과**: 읽기 완료율 40% → 55%, Quick Start 시도율 15% → 22%

---

## 3. 유입 채널별 전략

### 3-1. GitHub Trending 노출 최적화

**목표**: 한국어 + Python 카테고리 Trending 진입 (daily 기준 20~50 stars 필요)

| 액션 | 담당 | 시점 |
|------|------|------|
| README topics 태그 추가 (`telegram`, `multi-agent`, `llm`, `claude`, `gemini`, `openai`, `chatbot`, `automation`) | PM/개발 | 즉시 |
| GitHub Description 업데이트: "Multi-bot AI organization on Telegram — Claude/Codex/Gemini in one click" | PM | 즉시 |
| 릴리스 노트에 스크린샷 + GIF 첨부 (GitHub Release) | 개발 | v1.1 릴리스 시 |
| `awesome-telegram-bots`, `awesome-llm-agents` 등 awesome list PR | 성장 | 1주 이내 |

### 3-2. 해커뉴스 (Hacker News) 게시 전략

**타이밍**: 화/수/목 오전 9~11시 EST (한국 기준 밤 10시~자정)
**Show HN 포맷 예시**:
```
Show HN: I built a Telegram-based AI organization with 7 specialist bots (Claude/Codex/Gemini)
```

**핵심 메시지**:
- "한 줄 설치 (`curl ... | bash`) + Telegram 채팅방 = AI 조직"
- API 키 불필요 (OAuth only)
- 3개 엔진 자동 감지·선택

### 3-3. Reddit 게시 전략

| 서브레딧 | 포스트 유형 | 핵심 메시지 |
|----------|-------------|-------------|
| r/LocalLLaMA | 프로젝트 공개 | 3엔진 오케스트레이션, 오프라인 실행 가능 |
| r/MachineLearning | 기술 포스트 | 멀티에이전트 아키텍처 설계 원칙 |
| r/Python | Show r/Python | Python + Telegram + AI 통합 사례 |
| r/artificial | 일반 소개 | Telegram을 AI 오피스로 |

**타이밍**: 평일 오전 (UTC 기준 8~10시) 게시 → 미국 출근 전 최대 노출

### 3-4. 한국 개발자 커뮤니티

| 채널 | 방법 | 예상 효과 |
|------|------|-----------|
| **okky.kr** | "나는 이런 걸 만들었다" 카테고리 게시 | 한국 개발자 500~2,000 노출 |
| **disquiet.io** | 메이커 프로젝트 등록 | 프로덕트 관심층 100~500 노출 |
| **velog.io / tistory** | 기술 블로그 포스트 작성 (설치기 + 사용 사례) | SEO + 장기 유입 |
| **GeekNews (news.hada.io)** | HN 스타일 한국판 게시 | 테크 얼리어답터 500~1,000 노출 |
| **카카오톡 오픈채팅 (개발자방)** | 링크 공유 | 즉각적 피드백 |
| **트위터/X @Korean Dev** | 스크린샷 + 짧은 데모 GIF | 바이럴 가능성 |
| **링크드인** | 프로젝트 포스트 (영문) | 글로벌 개발자 네트워크 |

---

## 4. README 개편 → 유입 예상 효과 분석

### 4-1. 개편 전후 비교

| 항목 | 개편 전 | 개편 후 | 예상 효과 |
|------|---------|---------|-----------|
| 마스코트/로고 | 작은 PNG 텍스트 인라인 | 200px 중앙 정렬 nanobunny2 | 첫인상 개선, 브랜드 식별력 +30% |
| 엔진 배지 | 통합 1개 배지 | 개별 3개 배지 (claude/codex/gemini) | 검색 가시성 + 기술 스택 명확화 |
| 설치 흐름 | 텍스트만 | install_flow.png 이미지 포함 | 설치 시도율 +30% (시각적 확신) |
| 아키텍처 | PNG 1개 | 개선된 architecture_overview.png | 기술 이해도 향상 |
| 기여 가이드 | 브랜치·PR 절차만 | Good First Issue 레이블 + 로드맵 링크 | 첫 기여자 진입 장벽 -50% |

### 4-2. 단기 (1개월) 예상 시나리오

- Hacker News Show HN 게시 → 500~2,000 방문자 → 20~50 Stars
- 한국 커뮤니티 2~3곳 게시 → 500~1,000 방문자 → 10~30 Stars
- awesome-list PR 승인 → 지속적 passive 유입 → 월 10~30 Stars
- **총 예상**: 1개월 내 +50~100 Stars, Fork +15~30

### 4-3. 중기 (3개월) 성장 드라이버

1. **스킬 확장 기여**: Good First Issue 레이블 → 외부 기여자가 새 스킬 PR
2. **다국어 README**: 영문 README 추가 → 글로벌 유입
3. **데모 GIF**: 실제 텔레그램 화면 데모 → 트위터/Reddit 바이럴
4. **v2.0 릴리스**: P2P 협업 기능 → 기술 포스트 소재

---

## 5. 실행 체크리스트

### 즉시 (이번 세션)
- [x] README.md 전면 개편 (마스코트, 배지, 이미지, 기여 가이드)
- [x] docs/GROWTH_OPENSOURCE_STRATEGY.md 작성
- [ ] GitHub 리포지토리 Topics 태그 추가 (수동)
- [ ] GitHub Description 업데이트 (수동)

### 1주 이내
- [ ] 영문 README 섹션 추가 (또는 README_EN.md)
- [ ] awesome-telegram-bots PR 제출
- [ ] Show HN 포스트 초안 작성

### 1개월 이내
- [ ] 데모 GIF 제작 (설치 → 봇 실행 30초)
- [ ] 기술 블로그 포스트 2편 발행
- [ ] GitHub Discussions 활성화

---

## 6. 지표 추적 방법

```bash
# GitHub 통계 확인 (gh CLI)
gh repo view dragon1086/aimesh --json stargazerCount,forkCount,watcherCount

# 트래픽 확인 (14일 이내 pageviews)
gh api repos/dragon1086/aimesh/traffic/views

# 클론 통계
gh api repos/dragon1086/aimesh/traffic/clones

# 참조 소스 (어디서 왔는지)
gh api repos/dragon1086/aimesh/traffic/referrers
```

> 주간 측정 권장: 매주 월요일 오전 위 명령어 실행 → logs/growth_metrics/ 폴더에 저장

---

## 7. 관련 문서

- [README.md](../README.md) — 개편 완료본
- [CONTRIBUTING.md](../CONTRIBUTING.md) — 기여 가이드 상세
- [ROADMAP.md](../ROADMAP.md) — 제품 로드맵
- [docs/OPENSOURCE_PLAN.md](OPENSOURCE_PLAN.md) — 오픈소스화 전체 계획
