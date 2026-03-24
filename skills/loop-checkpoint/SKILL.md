---
name: loop-checkpoint
description: "Use during long-running autonomous loops to save progress state so execution can resume after interruption. Triggers: 'checkpoint', 'loop checkpoint', '체크포인트', 'save state', 'resume', automatically every 30 minutes during ralph/ultrawork loops"
allowed-tools: Read, Write
---

# Loop Checkpoint (루프 체크포인트)

everything-claude-code의 `/checkpoint` + `/loop-start` 패턴 적용.
장시간 자율 실행 중 상태를 저장하여 중단 후 재개를 가능하게 한다.

## 체크포인트 저장
```json
// .omc/checkpoint.json
{
  "timestamp": "ISO8601",
  "run_id": "run-YYYYMMDDTHHMMSSZ",
  "current_story": "US-003",
  "completed_stories": ["US-001", "US-002"],
  "files_modified": ["..."],
  "next_action": "story 구현 시작",
  "context_summary": "..."
}
```

## 사용 패턴
```python
# 매 주요 단계 완료 후 체크포인트
/loop-checkpoint save "US-002 완료 후"

# 재개 시
/loop-checkpoint resume
```

## 자동 체크포인트 조건
- 각 PRD 스토리 완료 시
- 파일 5개 이상 수정 후
- 30분 이상 실행 후
- 오류 발생 전

## 재개 절차
1. `.omc/checkpoint.json` 읽기
2. 완료된 스토리 스킵
3. `next_action`부터 재개
4. 체크포인트 업데이트
