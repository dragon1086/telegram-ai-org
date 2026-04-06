# 배포 절차서 — telegram-ai-org v1.0.0
> Phase 3 산출물 | 작성: 운영실(aiorg_ops_bot) | 날짜: 2026-03-29

---

## 1. 배포 원칙

1. **배포 전 항상 테스트** — pre-flight + CI 통과 없이 배포 금지
2. **단계적 변경** — 코드·인프라·설정 변경은 분리하여 단계적으로 적용
3. **롤백 준비** — 배포 전 롤백 포인트 확인 필수
4. **안전한 재기동** — `request_restart.sh` 사용 (직접 재기동 금지)

---

## 2. 배포 유형 분류

| 유형 | 트리거 | 테스트 요구 | 예시 |
|-----|-------|----------|------|
| **핫픽스** | 버그 긴급 수정 | unit + e2e | 봇 응답 오류 수정 |
| **일반 배포** | PR → main 머지 | CI 전체 통과 | 기능 추가 |
| **인프라 변경** | infra-baseline.yaml 수정 | pre-flight + E2E | timeout 조정 |
| **릴리즈** | tag push | 전체 테스트 스위트 | v1.x.x 게시 |

---

## 3. 일반 배포 절차 (Step-by-Step)

### Step 1: 사전 검증 (배포 전)
```bash
# 1-1. pre-flight 체크 실행
bash scripts/preflight_check.sh

# 1-2. 단위 테스트 통과 확인
python -m pytest tests/unit/ -v

# 1-3. E2E 테스트 통과 확인
python -m pytest tests/e2e/ --timeout=120 -v

# 1-4. 현재 봇 상태 확인
bash scripts/bot_control.sh status
```

**✅ 모두 통과 시에만 Step 2 진행**

### Step 2: 배포 실행
```bash
# 2-1. PR → main 머지 (GitHub UI 또는 CLI)
gh pr merge <PR번호> --merge

# 2-2. 안전한 재기동 요청 (직접 재기동 절대 금지)
bash scripts/request_restart.sh --reason "배포 사유 기재"

# ⚠️  절대 사용 금지:
# bash scripts/restart_bots.sh        (직접 재기동 — 태스크 결과 유실)
# bash scripts/bot_control.sh restart (직접 재기동)
```

### Step 3: 배포 후 검증
```bash
# 3-1. 봇 상태 확인 (재기동 완료까지 ~30초 대기)
bash scripts/bot_control.sh status

# 3-2. 헬스체크
python scripts/health_check.py

# 3-3. 봇 배포 헬스체크 (상세)
python scripts/bot_deploy_healthcheck.py

# 3-4. E2E smoke test (핵심 플로우만)
python -m pytest tests/e2e/test_pm_dispatch_e2e.py -v -k "smoke"
```

### Step 4: 완료 보고
- 텔레그램 채팅방에 배포 완료 + 변경 내역 보고
- CHANGELOG.md 업데이트

---

## 4. 인프라 변경 특별 절차

**infra-baseline.yaml 변경 시 반드시 이 절차 준수**

```bash
# 4-1. 변경 내용 PR 생성 (직접 push 금지)
git checkout -b infra/baseline-vX.Y.Z
# ... 파일 수정 ...
git commit -m "infra: update baseline to vX.Y.Z"
gh pr create --title "infra: baseline vX.Y.Z"

# 4-2. CI 통과 확인 (특히 E2E)
gh pr checks <PR번호>

# 4-3. 머지 후 모니터링 15분
python scripts/ops_rollout_monitor.py --duration 15m
```

---

## 5. 봇별 배포 순서 (의존성 기준)

```
1. PM 봇 (마지막에 재기동 — 라우팅 허브이므로)
   ↑ 의존
2. 각 조직 봇 (병렬 재기동 가능)
   - 개발실, 디자인실, 기획실, 운영실, 성장실, 리서치실
   ↑ 의존
3. telethon_listener (가장 먼저 — 메시지 수신 게이트웨이)
```

**주의**: PM 봇이 먼저 올라오면 조직 봇 미기동 상태로 태스크 분배 → 오류 발생

---

## 6. 롤백 절차

### 코드 롤백
```bash
# 이전 커밋으로 revert PR 생성
git revert HEAD --no-edit
gh pr create --title "revert: 롤백 사유"
# → CI 통과 후 머지 → request_restart.sh
```

### infra-baseline.yaml 롤백
```bash
# 이전 버전으로 복구
git checkout HEAD~1 -- infra-baseline.yaml
git commit -m "infra: rollback baseline to vX.Y.Z (긴급 롤백)"
bash scripts/request_restart.sh --reason "인프라 긴급 롤백"
```

---

## 7. 릴리즈 배포 절차 (v1.x.x)

```bash
# 1. 버전 태그 생성
git tag v1.x.x -m "Release v1.x.x"
git push origin v1.x.x

# 2. GitHub Release 자동 생성 (release.yml 트리거)
# → scripts/create_release.sh 내부적으로 사용

# 3. PyPI 게시 (publish-pypi.yml 트리거)
# → 자동으로 pip install telegram-ai-org 가능
```

**현황**: v1.0.0 2026-03-26 릴리즈 완료
