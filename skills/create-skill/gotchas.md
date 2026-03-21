# Create Skill — Gotchas

## Gotcha 1: description을 요약으로 작성하면 자동 매칭 안 됨

- **상황**: description에 "이 스킬은 X를 합니다" 식으로 요약을 적음
- **증상**: Claude가 해당 스킬을 자동으로 트리거하지 못함
- **해결**: description은 트리거 조건으로 작성. "Use when..." 또는 "Use to..." 형식. Triggers: 키워드 목록 포함

## Gotcha 2: On Demand Hooks에서 exit 1 사용 시 Write 차단

- **상황**: PreToolUse:Write 훅에서 검증 실패 시 exit 1 반환
- **증상**: Claude가 코드를 수정하려 해도 Write가 차단되어 데드락
- **해결**: PostToolUse:Write 사용하거나, 훅이 항상 exit 0으로 경고만 출력하도록 설계
