# setup.sh E2E 검증 보고서

**작성일**: 2026-04-01
**작성자**: 운영실 PM (aiorg_ops_bot)
**태스크 ID**: T-aiorg_pm_bot-1083
**검증 방법**: 코드 정적 분석 + 실행 흐름 시뮬레이션
**대상 파일**: `scripts/setup.sh` (1,442줄), `install.sh`
**검증 환경 조건**: Docker ubuntu:22.04 클린 컨테이너 (Node.js 미설치 상태 시뮬레이션)

> ⚠️ **검증 방법 주의사항**: 본 보고서 작성 시점에 Docker CLI가 현재 머신에 미설치 상태였습니다.
> 따라서 실제 컨테이너 기동 대신 `scripts/setup.sh` 소스코드(1,442줄) 전수 정독을 통한
> 정밀 정적 분석 + 실행 흐름 시뮬레이션 방식으로 결과를 도출했습니다.
> 동일 조건의 실 컨테이너 실행 시 동일 결과가 재현될 것으로 판단합니다.

---

## 결론 (요약)

**Ubuntu 22.04 클린 환경(Node.js 미설치)에서 `setup.sh --yes`는 Step 1에서 즉시 `exit 1`로 중단됩니다.**

3개 엔진 CLI 설치를 위한 npm 자동 설치 시도가 모두 실패하고, 스크립트 내 Node.js 자동 설치 코드(`_ensure_nodejs_ubuntu`)가 Step 1 이후(Step 3 구간)에 배치되어 있어 도달 자체가 불가능합니다. 이는 **설계상의 실행 순서 버그**입니다.

추가로 Python 3.11+ 요구사항과 Ubuntu 22.04 기본 Python 3.10.12 간 충돌이 잠재적 2차 차단 지점으로 존재합니다.

---

## Phase 1: 테스트 매트릭스

### 1-1. 컨테이너 3종 조건 정의

| 케이스 ID | 컨테이너 이름 | 기반 이미지 | Node.js 상태 | 네트워크 | 실행 사용자 | Python 버전 |
|-----------|-------------|-------------|--------------|---------|------------|-------------|
| TC-01 | clean-normal | ubuntu:22.04 | 미설치 | 외부 연결 허용 | root | 3.10.12 (기본) |
| TC-02 | clean-no-network | ubuntu:22.04 | 미설치 | `--network none` 차단 | root | 3.10.12 (기본) |
| TC-03 | clean-no-sudo | ubuntu:22.04 | 미설치 | 외부 연결 허용 | testuser (sudo 미설정) | 3.10.12 (기본) |

### 1-2. 컨테이너 기동 명령

```bash
# TC-01: 정상 플로우
docker run --rm -it ubuntu:22.04 bash

# TC-02: 네트워크 차단
docker run --rm -it --network none ubuntu:22.04 bash

# TC-03: 비루트 사용자 (sudo 미설정)
docker run --rm -it ubuntu:22.04 bash -c "
  useradd -m -s /bin/bash testuser
  su - testuser -c 'bash /path/to/scripts/setup.sh --yes'
"
```

### 1-3. 검증 체크포인트 목록

| 체크포인트 ID | 검증 항목 | 검증 명령 | 기대 결과 (정상 시) |
|-------------|---------|---------|------------------|
| CP-01 | Node.js 미설치 확인 | `node --version` | command not found |
| CP-02 | npm 미설치 확인 | `npm --version` | command not found |
| CP-03 | Python 버전 확인 | `python3 --version` | 3.10.12 |
| CP-04 | setup.sh 종료 코드 | `echo $?` | 0 (성공) or 1 (실패) |
| CP-05 | claude-code 설치 | `claude --version` | 버전 출력 |
| CP-06 | codex 설치 | `codex --version` | 버전 출력 |
| CP-07 | gemini-cli 설치 | `gemini --version` | 버전 출력 |
| CP-08 | .env 생성 | `cat .env \| grep AI_ENGINE` | `AI_ENGINE=claude-code` 등 |
| CP-09 | AI_ENGINE 설정 | `grep -E "^AI_ENGINE=" .env` | 값 기재됨 |
| CP-10 | NODE_PATH 설정 | `grep -E "^NODE_PATH=" .env` | 해당 없음 (미존재) |

### 1-4. 오류 케이스 재현 조건 명세

| 케이스 | 재현 방법 | 예상 실패 지점 |
|--------|---------|--------------|
| 네트워크 차단 | `docker run --network none` 또는 `iptables -A OUTPUT -j DROP` | NodeSource curl 다운로드 단계 |
| 권한 부족 | `useradd testuser` + `su - testuser` (sudoers 미설정) | `sudo apt-get install` 호출 시 |

---

## Phase 2: 정상 플로우 E2E 시뮬레이션 (TC-01)

### 2-1. 실행 명령

```bash
git clone <repo> telegram-ai-org
cd telegram-ai-org
bash scripts/setup.sh --yes
```

### 2-2. 단계별 시뮬레이션 결과

#### Step 1/5: AI 엔진 자동 감지 (lines 113~339)

| 순서 | 함수 | 동작 | 결과 |
|------|------|------|------|
| 1 | `detect_claude_code()` | `~/.local/bin/claude` 등 4개 경로 탐색 → `command -v claude` | ❌ FAIL (미설치) |
| 2 | `_try_install_engine "claude-code"` | `command -v npm` → not found → `command -v brew` → not found | ❌ FAIL, warn 출력 후 return 1 |
| 3 | `detect_codex()` | 동일 패턴 | ❌ FAIL |
| 4 | `_try_install_engine "codex"` | `command -v npm` → not found | ❌ FAIL, return 1 |
| 5 | `detect_gemini_cli()` | `/opt/homebrew/bin/gemini` 등 탐색 | ❌ FAIL |
| 6 | `_try_install_engine "gemini-cli"` | brew → not found, npm → not found | ❌ FAIL, return 1 |
| 7 | **종료 분기** | `${#DETECTED_ENGINES[@]} -eq 0` → `exit 1` | **🚨 스크립트 즉시 종료** |

**⚠️ 핵심 버그 발견**: `_try_install_engine()` 함수(lines 252~298)는 npm/brew를 전제로 동작합니다.
Node.js 자동 설치 함수 `_ensure_nodejs_ubuntu()`(lines 557~605)는
**Step 1 엔진 감지 이후(lines 607~651)**에 배치되어 있어, Step 1 실패 시 절대 실행되지 않습니다.

```
실제 코드 흐름:
  Line 300: detect_claude_code → FAIL
  Line 302: _try_install_engine (npm 없어서 실패)
  Line 310: detect_codex → FAIL
  Line 311: _try_install_engine (npm 없어서 실패)
  Line 319: detect_gemini_cli → FAIL
  Line 320: _try_install_engine (npm 없어서 실패)
  Line 328: if [ ${#DETECTED_ENGINES[@]} -eq 0 ] → TRUE
  Line 338: exit 1  ← 여기서 종료
  ...
  Line 607: Node.js 설치 코드 ← 절대 도달 불가
```

#### Step 2~5: 미도달

setup.sh가 Step 1에서 exit 1로 종료되므로 이후 단계는 실행되지 않습니다.

### 2-3. 최종 상태 (TC-01 정상 플로우)

| 항목 | 기대값 | 실제값 | 판정 |
|------|-------|-------|------|
| 종료 코드 | 0 | **1** | ❌ FAIL |
| claude-code 설치 | ✅ | ❌ 미설치 | ❌ FAIL |
| codex 설치 | ✅ | ❌ 미설치 | ❌ FAIL |
| gemini-cli 설치 | ✅ | ❌ 미설치 | ❌ FAIL |
| .env 생성 | ✅ | ❌ 미생성 | ❌ FAIL |
| AI_ENGINE 설정 | ✅ | ❌ 미설정 | ❌ FAIL |

**전체 결과: 3개 엔진 설치 완료 여부 — ❌ 전부 실패**

### 2-4. 단계별 소요시간 (시뮬레이션)

| 단계 | 예상 소요시간 | 비고 |
|------|------------|------|
| Step 1 엔진 감지 실패 | < 5초 | npm/brew 탐색 즉시 실패 |
| exit 1 종료 | - | Step 1에서 중단 |
| Step 2~5 | 미도달 | - |
| **총 소요시간** | **< 5초** | **조기 종료** |

---

## Phase 3: 오류 케이스 재현 테스트

### 3-1. 케이스 ①: 네트워크 차단 (TC-02)

**재현 조건**: `docker run --network none ubuntu:22.04`

| 실패 단계 | 오류 메시지 | 종료 코드 | 재시도 로직 |
|---------|-----------|---------|-----------|
| Step 1: `detect_*` + `_try_install_engine` | `⚠️  npm/brew를 찾을 수 없어 자동 설치 실패` | - (warn 출력 후 계속) | 없음 |
| Step 1: 3엔진 모두 실패 | `❌ AI 엔진이 하나도 감지되지 않았습니다.` | **exit 1** | 없음 |
| (가상) NodeSource curl | `curl: (6) Could not resolve host: deb.nodesource.com` | - | 없음 (단발성) |

**결과**: TC-01과 동일한 지점(Line 338 `exit 1`)에서 중단. 네트워크 차단은 별도 영향 없음 — Node.js 자동 설치 코드 자체에 도달하지 못하기 때문.

**오류 안내 적절성 평가**:
- ✅ `err "AI 엔진이 하나도 감지되지 않았습니다."` — 명확한 오류 메시지
- ✅ 각 엔진별 수동 설치 명령어 안내 (`npm install -g @anthropic-ai/claude-code` 등)
- ❌ Node.js가 없어서 npm이 없다는 근본 원인 안내 없음 — "npm이 왜 없는지" 설명 없음
- ❌ Ubuntu에서 Node.js 먼저 설치해야 한다는 안내 없음

### 3-2. 케이스 ②: 권한 부족 (TC-03)

**재현 조건**: `useradd testuser` 후 `su - testuser` (sudoers 미설정)

**시나리오 A**: 만약 Node.js 설치 코드에 도달했을 경우 (`_ensure_nodejs_ubuntu` 호출 시)

| 실패 단계 | 오류 메시지 | 종료 코드 | 종료 방식 |
|---------|-----------|---------|---------|
| `sudo apt-get install -y curl` | `sudo: command not found` 또는 `testuser is not in the sudoers file` | 127 또는 1 | set -e 에 의한 abrupt 종료 |
| `curl ... \| sudo -E bash -` | Permission denied | 1 | abrupt 종료 |
| `sudo apt-get install -y nodejs` | Permission denied | 1 | abrupt 종료 |

**실제 TC-03 결과**: 현재 코드에서 TC-01과 동일하게 Step 1에서 exit 1 종료. 권한 부족 오류 재현 불가 — Node.js 설치 코드에 도달 자체가 안 됨.

**오류 안내 적절성 평가**:
- ❌ `set -euo pipefail` 설정으로 sudo 실패 시 오류 메시지 없이 abrupt 종료 가능
- ❌ 비루트 사용자 대상 사전 안내 없음
- ❌ 권한 부족 시 graceful exit 처리 없음 (단순 set -e 동작)

### 3-3. 실패 지점 분석 표

| 케이스 ID | 실패 단계 | 오류 메시지 | 종료 코드 | 오류 안내 적절성 |
|---------|---------|-----------|---------|--------------|
| TC-01 (정상 환경) | Step 1 Line 338 | `❌ AI 엔진이 하나도 감지되지 않았습니다.` | 1 | ⚠️ 부분적 (npm 부재 원인 미안내) |
| TC-02 (네트워크 차단) | Step 1 Line 338 (동일) | 동일 | 1 | ⚠️ 부분적 |
| TC-03 (권한 부족) | Step 1 Line 338 (동일) | 동일 | 1 | ⚠️ 부분적 |
| TC-03 가상 (sudo 실패) | `_ensure_nodejs_ubuntu` 내 sudo 호출 | `sudo: command not found` | 127 | ❌ 부적절 (안내 없음) |

---

## Phase 4: E2E 검증 최종 보고서

### 4-1. 테스트 환경 요약

| 항목 | 내용 |
|------|------|
| 기반 이미지 | ubuntu:22.04 (클린, 패키지 미설치 상태) |
| 검증 방법 | 코드 정적 분석 (setup.sh 1,442줄 전수 분석) |
| 대상 스크립트 | `scripts/setup.sh`, `install.sh` |
| Python (Ubuntu 기본) | 3.10.12 |
| Node.js 초기 상태 | 미설치 (npm 미설치) |
| 테스트 케이스 수 | 3종 (정상/네트워크차단/권한부족) |

### 4-2. 정상 플로우 결과

| 항목 | 결과 |
|------|------|
| 3개 엔진 CLI 설치 완료 | **❌ 전부 실패** |
| 설치 실패 지점 | Step 1/5 (Line 338) — `exit 1` |
| .env 생성 | ❌ 미생성 (Step 4 미도달) |
| 전체 소요시간 | < 5초 (조기 종료) |
| 사용자 경험 | "10분 내 봇 기동" 조건 미충족 |

### 4-3. 오류 케이스별 결과 및 스크립트 대응 수준

| 케이스 | 실제 실패 지점 | 스크립트 대응 수준 |
|--------|-------------|-----------------|
| 네트워크 차단 | TC-01과 동일 (Step 1 exit 1) | ⚠️ 에러 메시지 존재, 근본 원인 미안내 |
| 권한 부족 | TC-01과 동일 (Step 1 exit 1) | ⚠️ 에러 메시지 존재, 권한 가이드 없음 |

### 4-4. 발견된 이슈 목록

| 이슈 ID | 심각도 | 재현 조건 | 현상 | 관련 코드 위치 |
|--------|-------|---------|------|--------------|
| ISS-01 | 🔴 Critical | Ubuntu 22.04 + Node.js 미설치 + `setup.sh --yes` | Step 1에서 즉시 exit 1 종료. Node.js 자동 설치 로직이 엔진 설치 시도(Step 1) 이후에 위치해 있어 도달 불가 | Lines 300~338 (Step 1), Lines 607~651 (Node.js 설치, 도달 불가) |
| ISS-02 | 🔴 Critical | Ubuntu 22.04 기본 Python | `python3` = 3.10.12, setup.sh는 3.11+ 요구 → Step 2에서 exit 1 예상 (Step 1 통과 시) | Lines 384~407 |
| ISS-03 | 🟡 High | `_ensure_nodejs_ubuntu()` + 비루트 사용자 | `sudo apt-get` 실패 시 `set -e`로 abrupt 종료, 오류 안내 없음 | Lines 557~605 |
| ISS-04 | 🟡 High | 네트워크 차단 + NodeSource PPA | `curl -fsSL https://deb.nodesource.com/setup_18.x` 실패 시 재시도 없이 종료 | Line 592 |
| ISS-05 | 🟠 Medium | `_try_install_engine` — Ubuntu 환경 | npm/brew 부재 시 "npm이 없어서 실패"만 안내, "Node.js를 먼저 설치하세요" 안내 없음 | Lines 262~273 |
| ISS-06 | 🟠 Medium | Step 1 실패 메시지 | 수동 설치 안내 명령어는 있으나, 왜 npm이 없는지(Node.js 미설치) 근본 원인 미안내 | Lines 329~338 |

### 4-5. 개선 권고사항 (운영 관점)

> 파일 수정 없이 운영 관점 권고 형태로 기술합니다. 코드 변경은 개발실 위임 사항.

#### 권고-1 (즉시) — Node.js 설치 순서 재배치 요청 → 개발실

**현재**: Node.js 설치 코드(`_ensure_nodejs_ubuntu`)가 Step 3 구간(lines 607~)에 위치
**필요**: Step 1 엔진 감지 시작 전 또는 `_try_install_engine()` 내부에서 npm 미존재 시 먼저 호출

**요청 사항**: `_try_install_engine()` 함수 수정 또는 Step 1 진입 전 사전 Node.js 확인 블록 추가:
```
(pseudo)
if Ubuntu AND no npm → _ensure_nodejs_ubuntu() 먼저 실행
then → _try_install_engine()
```

#### 권고-2 (즉시) — Python 3.11 자동 설치 추가 → 개발실

Ubuntu 22.04 기본 Python 3.10.12 → setup.sh 3.11+ 요구. `apt-get install python3.11` 자동 실행 로직 필요.

#### 권고-3 (단기) — sudo 권한 사전 확인 → 개발실

`_ensure_nodejs_ubuntu()` 진입 전 `id -u` 또는 `sudo -n true` 로 권한 확인 후, 실패 시 graceful 오류 안내 출력:
```
"sudo 권한이 없습니다. root로 실행하거나 sudoers에 추가 후 재실행하세요."
```

#### 권고-4 (단기) — 네트워크 curl 실패 재시도 로직 → 개발실

NodeSource PPA curl 실패 시 fallback: `apt-get install nodejs` (Ubuntu 기본 repo) 시도 추가. 또는 curl 실패 시 명확한 오류 메시지 + exit 1 (현재는 set -e에 의한 암묵적 종료).

#### 권고-5 (중기) — 오류 메시지 개선 → 개발실

엔진 미설치 오류 시 "npm이 없어서 자동 설치 실패" 외에 추가 안내:
```
"💡 Ubuntu/Debian에서는 먼저 Node.js를 설치하세요:
   curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
   sudo apt-get install -y nodejs
   그 후 bash scripts/setup.sh --yes 를 재실행하세요."
```

#### 권고-6 (운영 정책) — 사전 선행조건 문서화

README.md 및 QUICKSTART.md에 Ubuntu 선행조건 명시:
- Ubuntu 22.04: `sudo apt-get install -y python3.11 nodejs npm` 또는 `setup.sh --yes` 자동 설치 지원 여부 명기
- 현재 상태에서는 **"setup.sh가 자동 설치 못 함"** 이 사실이므로, v1.0.0 릴리즈 전 코드 수정 필수

---

## 종합 판정

| 항목 | 결과 |
|------|------|
| Ubuntu 22.04 클린 환경 자동 설치 | **❌ FAIL** |
| "아무것도 모르는 사용자" 경험 | **❌ 불합격** — 즉시 오류 종료, 해결책 불명확 |
| 3개 엔진 CLI 설치 완료 | **❌ 0/3** |
| v1.0.0 릴리즈 준비 상태 | **⛔ 보류** — ISS-01, ISS-02 해결 필수 |

**v1.0.0 태그 push는 ISS-01(Node.js 순서 버그) + ISS-02(Python 3.11 요구사항) 해결 후 권고합니다.**

---

*보고서 생성: 운영실 PM | 배포 대상: Rocky(PM), 개발실*
