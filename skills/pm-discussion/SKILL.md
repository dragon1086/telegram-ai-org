---
name: pm-discussion
description: "Use when multiple department bots need to debate or align on a decision, with the PM facilitating. Runs Diverge→Synthesize→Converge without human input. Triggers: 'pm discussion', '토론', 'discuss', '회의', 'debate', '논의', when bots need to reach consensus on a technical or business decision"
---

# PM Discussion (토론 조율 스킬)

PM 봇이 여러 조직 봇이 참여하는 토론을 구조적으로 조율한다.
자율 실행 가능 — AskUserQuestion 없이 봇들의 응답을 자동 수집한다.

## 토론 구조 (Diverge → Converge)

### Phase 1: Diverge (발산)
각 봇에게 독립적으로 의견을 요청한다:
```
[토론 시작] 의제: {topic}
각 조직은 자신의 관점에서 의견을 제시해주세요.
응답 형식:
- 핵심 관점: (1-2문장)
- 근거: (3가지 이하)
- 우려사항: (있다면)
```

### Phase 2: Synthesize (종합)
PM이 각 봇의 응답을 분석:
- 공통점 추출
- 핵심 갈등 지점 식별
- 통합 가능한 요소 파악

### Phase 3: Converge (수렴)
갈등 지점에 대해 추가 논의 요청 (최대 2라운드):
```
[2차 토론] {갈등_지점}에 대해:
A안: {요약}
B안: {요약}
각 조직은 선호 방안과 이유를 제시해주세요.
```

### Phase 4: 결론 도출
컨센서스가 형성되면:
- 결정 사항 공식화
- 반대 의견도 기록 (추후 참고)
- Rocky에게 결론 보고

## 자율 실행 시 주의
- 토론은 자동으로 진행 (사람 개입 없이)
- 3라운드 후에도 합의 안 되면: "미결 상태"로 Rocky에 보고
- 긴급 결정은 PM이 단독 결정 가능 (근거 명시 필수)

## 사용 예시
```
/pm-discussion "B2B vs B2C 우선순위 결정"
/pm-discussion "기술 스택 선택: FastAPI vs Django"
```
