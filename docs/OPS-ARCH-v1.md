# 인프라 아키텍처 문서 — telegram-ai-org v1.0.0
> Phase 1 산출물 | 작성: 운영실(aiorg_ops_bot) | 날짜: 2026-03-29

---

## 1. 개요

telegram-ai-org는 3개 AI 엔진(claude-code / codex / gemini-cli)을 조직별로 배정하여
텔레그램 채팅방에서 멀티봇 AI 조직을 운영하는 플랫폼이다.

**현행 버전**: v1.0.0 (GitHub Release 2026-03-26 게시)
**인프라 베이스라인**: infra-baseline.yaml v1.2.0 (2026-03-29 현행화)

---

## 2. 아키텍처 전체 구성

```
[텔레그램 채팅방]
      │
      ▼
[telethon_listener.py]  ← min_id 필터링 (ETC-03, cross-contamination 방지)
      │
      ▼
[PM 봇 (claude-code)]  ← 태스크 수신·분배·보고
      │
      ├── [개발실 봇 (claude-code)]   — 코딩, API, 버그수정
      ├── [디자인실 봇 (claude-code)] — UI/UX, 와이어프레임
      ├── [기획실 봇 (claude-code)]   — PRD, 요구사항
      ├── [운영실 봇 (gemini-cli)]    — 배포, 인프라, 모니터링
      ├── [성장실 봇 (gemini-cli)]    — 지표, 마케팅
      └── [리서치실 봇 (gemini-cli)]  — 조사, 분석
```

---

## 3. 컴포넌트 상세

### 3.1 봇 프로세스 관리
| 컴포넌트 | 경로 | 역할 |
|---------|------|------|
| bot_manager.py | scripts/ | 전체 봇 프로세스 생명주기 관리 |
| bot_watchdog.py | scripts/ | 봇 비정상 종료 감지 + 자동 재기동 |
| bot_control.sh | scripts/ | 봇 시작/중지/재시작 CLI |
| request_restart.sh | scripts/ | 안전한 재기동 요청 (플래그 파일 방식) |

### 3.2 pre-flight 체크 시스템 (RETRO-01 완료)
| 컴포넌트 | 경로 | 역할 |
|---------|------|------|
| preflight_check.sh | scripts/ | 환경 유효성 검증 (E2E 실행 전) |
| preflight_check.py | scripts/ | Python 기반 pre-flight (infra-baseline.yaml 읽기) |
| infra-baseline.yaml | / | E2E 환경 베이스라인 명세 v1.2.0 |

### 3.3 인프라 베이스라인 핵심 명세 (v1.2.0)
| 항목 | 값 | 비고 |
|-----|----|----|
| e2e_timeout_sec | 120 | ETC-02: 60→120 상향 |
| telethon_min_id_filter | record_on_activation | ETC-03 적용 |
| baseline_version | v1.2.0 | RETRO-03 현행화 |
| last_updated | 2026-03-29 | |

### 3.4 CI/CD 파이프라인 (.github/workflows/)
| 워크플로 | 트리거 | 내용 |
|---------|-------|------|
| ci.yml | PR → main | lint→unit-test→docker-build→e2e 순차 실행 |
| cd-main.yml | push → main | 메인 배포 파이프라인 |
| release.yml | tag push | GitHub Release 생성 |
| publish-pypi.yml | release | PyPI 패키지 게시 |
| ci-lint.yml | PR | lint 전용 빠른 검증 |

### 3.5 데이터 계층
| 스토리지 | 용도 | 비고 |
|---------|------|------|
| ai_org.db (SQLite) | 봇 상태·대화 이력 | 로컬 프로덕션 DB |
| context.db (SQLite) | 컨텍스트 캐시 | 세션별 임시 |
| logs/ | E2E 로그·experiment_log.yaml | RETRO-10 헤더 자동삽입 적용 |

---

## 4. 네트워크 경계

```
인터넷
  ├── Telegram API (api.telegram.org)
  ├── Anthropic API (api.anthropic.com)   — claude-code 엔진용
  ├── OpenAI API (api.openai.com)         — codex 엔진용
  └── Google Gemini (googleapis.com)      — gemini-cli 엔진용

로컬 (macOS)
  ├── /opt/homebrew/bin/gemini           — Gemini CLI 바이너리
  ├── ~/.gemini/oauth_creds.json         — OAuth 2.0 인증
  └── ~/telegram-ai-org/                — 메인 레포지토리
```

---

## 5. 보안 원칙

- `.env` 파일: 절대 커밋 금지 (`.gitignore` 등록됨)
- `.env.example`: 키 없는 템플릿만 공개
- 토큰/시크릿: 환경변수만 사용 (코드 하드코딩 금지)
- ST-09 보안 감사 완료 (2026-03-25)

---

## 6. 아키텍처 변경 이력

| 날짜 | 변경 | 담당 |
|-----|------|------|
| 2026-03-26 | 운영실 엔진 codex → gemini-cli 전환 | 운영실 |
| 2026-03-26 | infra-baseline.yaml v1.2.0 현행화 | 운영실 |
| 2026-03-27 | pre-flight 자동화 (RETRO-01/03/04) | 개발실·운영실 |
| 2026-03-29 | design-baseline.yaml v1.3 적용 | 디자인실 |
