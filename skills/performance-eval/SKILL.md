---
name: performance-eval
description: "Use to evaluate how well each department bot is performing over a period. Scores bots on completion rate, quality, speed, collaboration, and learning. Triggers: '성과평가', '평가', 'performance eval', 'evaluation', '봇 평가', 'bot performance'"
---

# Performance Eval (성과평가 스킬)

AI 조직 봇들의 성과를 데이터 기반으로 평가한다.

## 평가 기준
1. **완료율**: 배분된 태스크 중 완료한 비율
2. **품질**: 코드 리뷰 통과율, 재작업 횟수
3. **속도**: 평균 태스크 완료 시간
4. **협업**: 다른 봇과의 협력 횟수
5. **학습**: 같은 실수 반복 여부

## 평가 프로세스
1. 지난 기간 태스크 이력 수집 (`.ai-org/runs/` 분석)
2. 봇별 점수 계산
3. 강점/약점 식별
4. 개선 제안 생성
5. 평가 보고서: `docs/evals/YYYY-MM-DD-eval.md`
