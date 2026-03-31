# Dashboard Tunnel 운영 가이드

**작성일**: 2026-03-31
**작성자**: 운영실 인프라 에이전트
**관련 문서**: `docs/dashboard-tunnel-comparison.md`

---

## 1. 전체 구성 개요

FastAPI 대시보드(포트 8000)를 ngrok 터널을 통해 외부에 노출하고,
macOS LaunchAgent(launchd)로 상시 운영하는 구성입니다.

```
[FastAPI :8000] ←── [ngrok 프로세스] ←──TLS──→ [ngrok Cloud] ←── [외부 접속]
                          │
                   [로컬 API :4040]
                          │
              [issue_dashboard_url.sh]   ← URL 조회 + .env 갱신 + Telegram 알림
              [tunnel_healthcheck.sh]    ← cron 5분 간격 헬스체크 + 자동 복구
```

### 구성 파일 목록

| 파일 경로 | 역할 |
|-----------|------|
| `infra/ngrok-dashboard.plist` | macOS LaunchAgent plist |
| `scripts/issue_dashboard_url.sh` | URL 발급 + `.env` 갱신 + Telegram 알림 |
| `scripts/tunnel_healthcheck.sh` | 헬스체크 + 자동 복구 |
| `.env` (DASHBOARD_URL) | 현재 활성 터널 URL 저장 |
| `logs/ngrok.log` | ngrok stdout 로그 |
| `logs/ngrok.error.log` | ngrok stderr 로그 |

---

## 2. ngrok 설치 방법 (macOS)

```bash
# Homebrew로 설치
brew install ngrok/ngrok/ngrok

# 설치 확인
ngrok version
# 출력 예: ngrok version 3.x.x

# 바이너리 위치 확인
which ngrok
# 출력 예: /opt/homebrew/bin/ngrok
```

---

## 3. ngrok authtoken 설정 방법

ngrok 무료 계정을 생성하고 인증 토큰을 설정해야 합니다.

```bash
# 1. https://dashboard.ngrok.com/signup 에서 계정 생성
# 2. https://dashboard.ngrok.com/get-started/your-authtoken 에서 토큰 복사
# 3. 토큰 등록
ngrok config add-authtoken <YOUR_AUTHTOKEN>

# 설정 파일 위치 확인
cat ~/.config/ngrok/ngrok.yml
```

> 참고: authtoken 없이도 임시 터널은 생성되지만, 세션 시간 제한이 있습니다.
> 무료 계정 인증 시 세션 유지 시간이 크게 향상됩니다.

---

## 4. LaunchAgent 등록 절차

### 4-1. plist 파일 복사

```bash
cp /Users/rocky/telegram-ai-org/infra/ngrok-dashboard.plist \
   ~/Library/LaunchAgents/com.telegram-ai-org.ngrok-dashboard.plist
```

### 4-2. LaunchAgent 등록 및 시작

```bash
# 등록 + 즉시 시작
launchctl load ~/Library/LaunchAgents/com.telegram-ai-org.ngrok-dashboard.plist

# 상태 확인
launchctl list | grep ngrok
# 출력 예: 12345  0  com.telegram-ai-org.ngrok-dashboard
```

### 4-3. 로그 확인

```bash
# stdout 로그
tail -f /Users/rocky/telegram-ai-org/logs/ngrok.log

# stderr 로그
tail -f /Users/rocky/telegram-ai-org/logs/ngrok.error.log
```

### 4-4. LaunchAgent 중지/제거

```bash
# 중지
launchctl unload ~/Library/LaunchAgents/com.telegram-ai-org.ngrok-dashboard.plist

# 완전 제거
launchctl unload ~/Library/LaunchAgents/com.telegram-ai-org.ngrok-dashboard.plist
rm ~/Library/LaunchAgents/com.telegram-ai-org.ngrok-dashboard.plist
```

---

## 5. URL 발급 방법

ngrok 실행 후 `issue_dashboard_url.sh`를 실행하면 URL을 조회하고
`.env`를 자동 갱신한 뒤 Telegram으로 알림을 발송합니다.

```bash
cd /Users/rocky/telegram-ai-org
bash scripts/issue_dashboard_url.sh
```

정상 출력 예시:
```
[INFO]  ngrok 프로세스 확인됨.
[INFO]  ngrok 로컬 API에서 URL 조회 중: http://localhost:4040/api/tunnels
[INFO]  조회된 public URL: https://xxxx-xxx-xxx-xxx-xxx.ngrok-free.app
[INFO]  .env DASHBOARD_URL 업데이트 완료.
[INFO]  Telegram 알림 발송 완료.

============================================
  Dashboard URL: https://xxxx-xxx-xxx-xxx-xxx.ngrok-free.app
============================================
```

---

## 6. cron 헬스체크 등록 방법 (5분 간격)

```bash
# 현재 crontab 확인
crontab -l

# 헬스체크 cron 등록 (5분 간격)
(crontab -l 2>/dev/null; echo "*/5 * * * * /Users/rocky/telegram-ai-org/scripts/tunnel_healthcheck.sh >> /Users/rocky/telegram-ai-org/logs/tunnel_healthcheck.log 2>&1") | crontab -

# 등록 확인
crontab -l | grep tunnel_healthcheck
```

### cron 로그 확인

```bash
tail -f /Users/rocky/telegram-ai-org/logs/tunnel_healthcheck.log
```

---

## 7. 트러블슈팅 가이드

### 7-1. ngrok 연결 실패

**증상**: `ngrok: command not found`

```bash
# ngrok 설치 확인
which ngrok || brew install ngrok/ngrok/ngrok

# PATH 확인
echo $PATH | grep homebrew
```

**증상**: `ERR_NGROK_108` (authtoken 없음)

```bash
ngrok config add-authtoken <YOUR_AUTHTOKEN>
```

**증상**: `ERR_NGROK_302` (세션 제한)

- 무료 계정은 동시 세션 1개 제한
- `launchctl unload` 후 기존 터널 종료 → 재시작

### 7-2. URL 조회 실패 (포트 4040 무응답)

```bash
# ngrok 프로세스 확인
pgrep -a ngrok

# 포트 4040 확인
lsof -i :4040

# ngrok 로컬 API 직접 테스트
curl -s http://localhost:4040/api/tunnels | python3 -m json.tool
```

ngrok가 아직 초기화 중이면 수초 대기 후 재시도:
```bash
sleep 5 && curl -s http://localhost:4040/api/tunnels
```

### 7-3. 포트 충돌 (포트 8000)

```bash
# 포트 8000 사용 프로세스 확인
lsof -i :8000

# FastAPI 서버가 실행 중인지 확인
pgrep -a uvicorn
```

### 7-4. LaunchAgent 시작 실패

```bash
# 상세 로그 확인
log show --predicate 'subsystem == "com.apple.launchd"' --last 5m | grep ngrok

# plist 문법 검증
plutil -lint ~/Library/LaunchAgents/com.telegram-ai-org.ngrok-dashboard.plist

# 권한 확인
ls -la ~/Library/LaunchAgents/com.telegram-ai-org.ngrok-dashboard.plist
```

### 7-5. Telegram 알림 미수신

```bash
# .env에서 토큰 확인
grep TELEGRAM_BOT_TOKEN /Users/rocky/telegram-ai-org/.env
grep TELEGRAM_GROUP_CHAT_ID /Users/rocky/telegram-ai-org/.env

# 수동 테스트
source /Users/rocky/telegram-ai-org/.env
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  -d "chat_id=${TELEGRAM_GROUP_CHAT_ID}" \
  -d "text=test message"
```

---

## 8. URL 재발급 방법

ngrok 세션이 만료되거나 URL이 변경된 경우:

```bash
# 방법 1: issue_dashboard_url.sh 직접 실행
bash /Users/rocky/telegram-ai-org/scripts/issue_dashboard_url.sh

# 방법 2: LaunchAgent 재시작 후 URL 재발급
launchctl unload ~/Library/LaunchAgents/com.telegram-ai-org.ngrok-dashboard.plist
launchctl load ~/Library/LaunchAgents/com.telegram-ai-org.ngrok-dashboard.plist
sleep 5
bash /Users/rocky/telegram-ai-org/scripts/issue_dashboard_url.sh

# 방법 3: 헬스체크 스크립트 수동 실행 (자동 복구 포함)
bash /Users/rocky/telegram-ai-org/scripts/tunnel_healthcheck.sh
```

### 현재 URL 빠른 확인

```bash
# .env에서 직접 확인
grep DASHBOARD_URL /Users/rocky/telegram-ai-org/.env

# ngrok API에서 직접 확인
curl -s http://localhost:4040/api/tunnels | python3 -c "
import json,sys; d=json.load(sys.stdin)
for t in d.get('tunnels',[]): print(t.get('public_url',''))
"
```

---

## 9. 운영 체크리스트

- [ ] ngrok 설치 및 authtoken 설정 완료
- [ ] `infra/ngrok-dashboard.plist` → `~/Library/LaunchAgents/` 복사
- [ ] `launchctl load` 로 LaunchAgent 등록
- [ ] `bash scripts/issue_dashboard_url.sh` 로 초기 URL 발급
- [ ] `.env`에 `DASHBOARD_URL` 값 확인
- [ ] cron 헬스체크 등록 (`*/5 * * * *`)
- [ ] Telegram 알림 수신 확인
