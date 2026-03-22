# 봇 라우팅 레퍼런스

> **주의**: 아래 org ID는 예시(aiorg 조직 기준)이다. 실제 사용 시 `organizations.yaml`의 `id` 필드를 참조한다.
> 인프라/배포/재기동 권한은 `capabilities: [infra]`가 설정된 조직에 귀속된다.

## 부서별 전문 분야 (예시)

| 역할 | 예시 org ID | 전문 분야 | 키워드 |
|------|-------------|-----------|--------|
| 개발/엔지니어링 | aiorg_engineering_bot | 개발/코딩/API/버그 | 코드, API, 버그, 에러, 구현, 개발, Python, TypeScript |
| 디자인 | aiorg_design_bot | UI/UX/디자인 | 디자인, UI, UX, 와이어프레임, 프로토타입, 색상, 레이아웃 |
| 성장/마케팅 | aiorg_growth_bot | 성장/마케팅/지표 | 마케팅, 지표, 전환율, DAU, 캠페인, A/B테스트, 성장 |
| infra (capabilities: infra) | aiorg_ops_bot | 운영/인프라 | 서버, 배포, 인프라, 모니터링, 알림, 운영 |
| 리서치 | aiorg_research_bot | 조사/분석 | 시장조사, 경쟁사, 분석, 리서치, 트렌드 |
| 제품/기획 | aiorg_product_bot | 기획/PRD/전략 | 기획, PRD, 요구사항, 전략, 로드맵, 스펙 |

## 복합 태스크 예시

| 태스크 | 주담당 | 협업 |
|--------|--------|------|
| "랜딩페이지 만들기" | design → engineering | 순차 |
| "신규 기능 출시" | product → engineering → design | 순차 |
| "성과 분석 + 개선안" | research + growth | 병렬 가능 |
| "서비스 장애 대응" | ops → engineering | 순차 |
