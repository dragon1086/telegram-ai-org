# 장애 기록: E2E S-P1 Timeout (2026-03-26)

> **분류**: 인프라 문제 | **체크포인트**: Q3 (e2e_timeout_sec 불일치) | **해결 소요**: 15분

## 증상

```
asyncio.TimeoutError
E2E 시나리오 S-P1: FAILED (timeout after 60s)
```

- 로컬에서는 간헐적 통과, CI에서는 항상 실패
- `pytest tests/e2e/ --timeout=60` 실행 시 재현

## 이분 판단 경로

| 단계 | 결과 |
|------|------|
| Q1: preflight FAIL? | No (환경변수 정상) |
| Q2: 필수 env 미설정? | No |
| Q3: e2e_timeout_sec < 120? | **Yes → 인프라 경로 확정** |

## 근본 원인

`infra-baseline.yaml`의 `e2e_timeout_sec: 60` 설정이 Telegram API 응답 지연(평균 45~90s)을 수용하지 못함.

## 조치

```bash
# infra-baseline.yaml 수정
# e2e_timeout_sec: 60 → 120
# version: v1.1.0 → v1.2.0
git commit -m "fix(infra): e2e_timeout_sec 60→120 — baseline v1.2.0"
```

## 재발 방지

- `scripts/preflight_check.sh` Q3 자동 체크 로직 추가 완료 (RETRO-01)
- `conftest.py` E2E 로그 헤더에 `baseline_version` 자동 삽입 완료 (RETRO-04)
