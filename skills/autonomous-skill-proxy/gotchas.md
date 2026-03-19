# Autonomous Skill Proxy — Gotchas

## 1. AUTONOMOUS_MODE 환경변수 미설정
`.env`에 `AUTONOMOUS_MODE=false`가 기본값.
자율 실행 시 반드시 `AUTONOMOUS_MODE=true`로 설정하거나
실행 커맨드에 `AUTONOMOUS_MODE=true claude ...` 형태로 명시.

## 2. 인터랙티브 스킬을 직접 호출하는 실수
brainstorming, deep-interview, ralplan --interactive 등은
AskUserQuestion을 사용하므로 자율 에이전트에서 직접 호출하면 멈춤.
반드시 brainstorming-auto, pm-discussion 등 비인터랙티브 버전 사용.

## 3. 컨텍스트 기반 추론 한계
태스크 설명이 너무 짧거나 모호하면 "합리적 기본값"이 틀릴 수 있음.
Rocky에게 텔레그램으로 방향성을 충분히 설명하는 것이 최선의 예방책.

## 4. config.json의 autonomous_mode는 런타임 설정 아님
이 파일은 기본값 문서화용. 실제 활성화는 환경변수로만 가능.
코드에서 `os.environ.get("AUTONOMOUS_MODE", "false").lower() == "true"` 로 체크.

## 5. 멈추는 것보다 틀린 진행이 낫다
자율 모드에서는 완벽보다 진행이 우선.
불확실하면 "[AUTONOMOUS] 합리적 기본값 사용: ..." 로그 후 진행.
