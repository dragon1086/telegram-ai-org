# telegram-ai-org

텔레그램 그룹 채팅방 = AI 조직의 오피스.

유저가 방향만 제시하면, PM AI가 R&R 설계 + 팀 구성하고, 각 AI 팀이 Telegram 봇으로 실제 코딩/분석을 실행합니다.

## 차별화 포인트

- **Telegram이 Native UI + 메시지 버스**: 별도 대시보드 불필요, 채팅방 자체가 오피스
- **실사용 봇 ID**: 각 AI가 독립된 Telegram 계정 보유
- **공유 컨텍스트 DB**: 모든 봇이 동일한 맥락 접근
- **완료 검증 프로토콜**: PM이 전체 봇에 확인 요청 후 최종 처리

## 아키텍처 개요

```
유저 → @pm_bot → 태스크 분해 → R&R 할당
                    ↓
         @dev_bot / @analyst_bot / @docs_bot
                    ↓
         실행 (Claude Code / Codex / amp)
                    ↓
         @pm_bot ← 결과 보고 → 완료 검증
```

## 빠른 시작

```bash
# 1. 의존성 설치
./scripts/setup.sh

# 2. 환경변수 설정
cp .env.example .env
# .env 파일 편집

# 3. 모든 봇 시작
./scripts/start_all.sh
```

## 기술 스택

- Python 3.11+
- python-telegram-bot
- SQLite + sqlite-vec (공유 컨텍스트)
- Claude Code / Codex / amp (실행 엔진)
- asyncio + pydantic

## 관련 프로젝트

MetaGPT, AutoGen, CrewAI, OpenAI Swarm에서 영감을 받았으나,
**Telegram을 native 메시지 버스**로 사용하는 것이 핵심 차별점입니다.
