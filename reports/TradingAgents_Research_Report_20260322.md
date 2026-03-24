# TradingAgents (TauricResearch) 리서치 보고서

> 조사 기준일: 2026-03-22 | 조사자: aiorg_research_bot (PM 단독 실행)
> 대상 리포: https://github.com/TauricResearch/TradingAgents

---

## 1. 핵심 요약 (Executive Summary)

TradingAgents는 **실제 금융사의 조직 구조를 LLM 멀티에이전트로 재현한 오픈소스 트레이딩 프레임워크**다.
2024년 12월 arXiv 논문으로 공개, 2025~2026년에 걸쳐 빠르게 버전업 중이며 현재 v0.2.2 (2026-03-22 기준).
단일 에이전트 모델 대비 누적 수익률·샤프 비율·최대 낙폭(MDD) 전 지표에서 우위를 입증.
LangGraph 기반, OpenAI/Google/Anthropic/xAI 등 멀티프로바이더 LLM 지원.

---

## 2. 프레임워크 목적 및 배경

| 항목 | 내용 |
|------|------|
| **리포 주소** | https://github.com/TauricResearch/TradingAgents |
| **라이선스** | Apache-2.0 |
| **언어** | Python 3.13 |
| **논문** | arXiv:2412.20138 (2024-12) |
| **스타** | 급증 중 (2026년 초 AI 트레이딩 관심 급등 배경) |

**해결하려는 문제**:
- 기존 단일 LLM 에이전트는 복잡한 시장 상황 분석에 한계
- 독립적으로 데이터 수집하는 다중 에이전트도 역할 분담·협업 미흡
- 실제 트레이딩 펌의 조직적 의사결정 구조를 AI로 재현하지 못함

---

## 3. 아키텍처 및 에이전트 구조

### 계층 구조 (4-Layer)

```
[Layer 1] 분석팀 (Analysts)
  ├── Fundamentals Analyst  — 재무제표, 밸류에이션
  ├── Sentiment Analyst     — 감성 분석 (소셜/커뮤니티)
  ├── News Analyst          — 뉴스 해석 및 이벤트 탐지
  └── Technical Analyst     — 기술지표 (MACD, RSI, KDJ 등)

[Layer 2] 연구팀 (Researchers)
  ├── Bull Researcher       — 강세 논거 수집·강화
  └── Bear Researcher       — 약세 논거 수집·반박

[Layer 3] 거래팀 (Trader)
  └── Trader                — 분석 종합 → 매수/중립/매도 결정

[Layer 4] 위험관리 (Risk Management)
  ├── Risk Manager          — 변동성·유동성·포트폴리오 평가
  └── Portfolio Manager     — 최종 승인
```

### 코드 구조 (`tradingagents/agents/`)
```
agents/
├── analysts/    # 4개 분석 에이전트
├── researchers/ # Bull/Bear 연구원
├── trader/      # 거래 실행
├── risk_mgmt/   # 위험 관리
├── managers/    # 포트폴리오 관리
└── utils/       # 공통 도구
```

---

## 4. 기술 스택

| 구성 요소 | 기술 |
|-----------|------|
| **에이전트 오케스트레이션** | LangGraph |
| **지원 LLM** | OpenAI (GPT-5.x), Google (Gemini 3.x), Anthropic (Claude 4.x), xAI (Grok 4.x), OpenRouter, Ollama |
| **벡터 검색** | BM25 (v0.2.0부터 ChromaDB 대체) |
| **데이터 소스** | Alpha Vantage API, 기타 금융 데이터 |
| **실행 환경** | Python 3.13, CLI + Python SDK |

---

## 5. 릴리즈 히스토리 (최신순)

### v0.2.2 — 2026-03-22 (최신)
- **5단계 평가 척도 도입**: Buy / Overweight / Hold / Underweight / Sell
- OpenAI Responses API + **Anthropic Claude 4.5+** 공식 지원
- 통합 LLM 프로바이더 정규화 (OpenAI, Google, Anthropic)
- **국제 거래소 티커 지원**: CNC.TO (TSX), 7203.T (도쿄), 0700.HK (홍콩)
- UTF-8 크로스플랫폼 호환성 강화

### v0.2.1 — 2026-03-15
- **신규 모델**: GPT-5.4, Claude Opus 4.6, Gemini 3.1 Pro
- CSV 파싱 및 NaN 처리 자동화
- 윈도우 호환성 인코딩 수정
- CVE-2026-22218 취약점 패치

### v0.2.0 — 2026-02-04
- **멀티프로바이더 LLM 팩토리 패턴** 도입
- ChromaDB → BM25 교체 (속도·경량화)
- 에이전트 명칭 체계 정비 (공격적/보수적 → 역할 명칭)
- 분석 보고서 자동 저장 기능

---

## 6. 성능 벤치마크

### 실험 설정
- **데이터**: 멀티에셋·멀티모달 금융 데이터셋
  - 기간: 2024년 1~3월 (학습), 2024년 6~11월 (거래 평가)
  - 포함: 주가, 뉴스, 소셜미디어 감성, 내부자 거래, 재무제표, 기술지표

### 비교 대상 (Baseline)
| 전략 | 유형 |
|------|------|
| Buy and Hold | 패시브 |
| MACD 모멘텀 | 기술적 |
| KDJ+RSI 복합 모멘텀 | 기술적 |
| ZMR 평균 회귀 | 통계적 |
| SMA 추세추종 | 기술적 |

### 결과
- **누적 수익률**: 모든 베이스라인 대비 개선
- **샤프 비율**: 위험 조정 수익 우위
- **최대 낙폭(MDD)**: 낮은 드로다운 유지하며 고수익 달성

> ⚠️ 논문(arXiv:2412.20138) 상 구체적 수치는 원문 Table 참조 필요.
> TraderBench(arXiv:2603.00285) 기준 2026년 모델별 비교: Gemini-3-Pro(64.3점) > Grok 4.1 Fast(63.7점) > GPT-5.2(61.9점)

---

## 7. 경쟁 프레임워크 비교

| 프레임워크 | 특징 | TradingAgents와 차이 |
|-----------|------|---------------------|
| **FinGPT** | 금융 특화 파인튜닝 LLM | 단일 모델, 멀티에이전트 구조 없음 |
| **FinAgent** | 멀티모달 금융 에이전트 | 협업 토론 메커니즘 부재 |
| **AI-Trader (HKUDS)** | 라이브 트레이딩 벤치마크 | 실시간 포지션 중심 |
| **TradingAgents-Dashboard** | TradingAgents + Obsidian 메모리 | 커뮤니티 포크, 대시보드 추가 |

**TradingAgents의 차별점**:
1. Bull/Bear 연구원 간 **구조화된 논쟁(토론)** 후 결정
2. **4단계 계층** 의사결정 (분석→연구→거래→위험관리)
3. 특정 LLM에 종속되지 않는 **프로바이더 독립적 설계**
4. **국제 거래소** 티커 지원 (v0.2.2~)

---

## 8. 설치 및 빠른 시작

```bash
# 설치
git clone https://github.com/TauricResearch/TradingAgents.git
cd TradingAgents
pip install .

# CLI 실행 (인터랙티브)
tradingagents

# Python SDK
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

ta = TradingAgentsGraph(config=DEFAULT_CONFIG.copy())
_, decision = ta.propagate("NVDA", "2026-01-15")
print(decision)
```

**필수 API 키** (최소 1개 선택):
- `OPENAI_API_KEY` / `GOOGLE_API_KEY` / `ANTHROPIC_API_KEY` / `XAI_API_KEY`
- `ALPHAVANTAGE_API_KEY` (금융 데이터)

---

## 9. 주요 인사이트

1. **시장 포지셔닝**: "AI 트레이딩" 분야에서 멀티에이전트 오케스트레이션을 가장 완성도 있게 구현한 오픈소스. LangGraph + 역할 분리 구조가 핵심 경쟁력.

2. **빠른 모델 추종**: GPT-5, Claude 4.x, Gemini 3.x 출시와 거의 동시에 지원 — 모델 종속성 탈피 전략이 성공적.

3. **국제화 신호**: v0.2.2에서 글로벌 거래소(캐나다·일본·홍콩) 티커 지원 시작 → 한국 KRX 지원 가능성 있음.

4. **Bull/Bear 토론 구조**: 단순 분석 취합이 아닌 **반론 포함 토론** 설계 — 편향 감소·결정 품질 향상에 실질적 기여.

5. **한계**: 백테스트 기반 성능이며 슬리피지·수수료·유동성 충격 미반영. 실시간 라이브 트레이딩 검증은 별도 필요.

---

## 10. 참고 출처

| 번호 | 출처 | URL |
|------|------|-----|
| 1 | GitHub 리포지토리 | https://github.com/TauricResearch/TradingAgents |
| 2 | 공식 문서 | https://tauricresearch.github.io/TradingAgents/ |
| 3 | arXiv 논문 (2412.20138) | https://arxiv.org/abs/2412.20138 |
| 4 | 릴리즈 노트 | https://github.com/TauricResearch/TradingAgents/releases |
| 5 | DigitalOcean 가이드 | https://www.digitalocean.com/resources/articles/tradingagents-llm-framework |
| 6 | TraderBench 논문 | https://arxiv.org/html/2603.00285v1 |
| 7 | Tauric Research 공식 | https://tauric.ai/ |
| 8 | OpenReview 논문 | https://openreview.net/pdf/bf4d31f6b4162b5b1618ab5db04a32aec0bcbc25.pdf |

---
*보고서 생성: 2026-03-22 | aiorg_research_bot*
