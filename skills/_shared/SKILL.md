---
name: _shared
description: "Shared utilities and scripts used by multiple skills. Use when importing common helpers like save-log.py. Triggers: referenced internally by other skills that need atomic JSONL logging or shared script utilities."
---

# _shared

공유 유틸리티 모음. 여러 스킬에서 공통으로 사용하는 스크립트가 위치한다.

## 포함 파일

- `save-log.py` — 원자적 JSONL append 유틸리티 (flock 기반 race condition 방지)
