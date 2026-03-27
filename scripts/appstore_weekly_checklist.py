#!/usr/bin/env python3
"""
앱스토어 주간 점검 체크리스트 텔레그램 전송 스크립트
실행 주기: 매주 월요일 09:02 KST
등록 크론: scripts/register_crons.sh → appstore_weekly_checklist
"""
from __future__ import annotations

import json
import logging
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

# ── 환경변수 로드 (.env fallback) ───────────────────────────────────────────
def _load_env() -> None:
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())


_load_env()

BOT_TOKEN = os.environ.get("PM_BOT_TOKEN", "")
# 그룹 채팅 사용 (개인 DM은 /start 선행 필요 → 403 위험)
CHAT_ID = os.environ.get("TELEGRAM_GROUP_CHAT_ID", "-5203707291")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

CHECKLIST_TEXT = """📋 *[PRISM 앱스토어 주간 점검 체크리스트]*
_매주 월요일 Rocky 수동 확인 항목_

━━━━━━━━━━━━━━━━━━━━━━
🍎 *iOS — App Store Connect*

📥 *다운로드 지표*
☐ 1. 이번 주 신규 다운로드 수
☐ 2. 출처별 다운로드 비율 (유기적 vs 검색)
☐ 3. 국가별 다운로드 Top 3 확인

⭐ *리뷰/평점*
☐ 4. 신규 리뷰 확인 및 답변 필요 여부
☐ 5. 평균 평점 변동 (전주 대비)

🔧 *안정성*
☐ 6. Crash Rate 확인 (Xcode Organizer / Crashlytics)
☐ 7. 심사 중인 버전 상태 (없으면 패스)

💳 *수익화 — 크레딧 전환율*
☐ 8. 이번 주 IAP 결제 건수 / 금액
☐ 9. 크레딧 구매 전환율 (설치 대비 결제 %)
☐ 10. 무료→유료 전환 추이

━━━━━━━━━━━━━━━━━━━━━━
🤖 *Android — Google Play Console*

📥 *다운로드 지표*
☐ 11. 이번 주 신규 설치 수 (신규 + 업데이트 구분)
☐ 12. 설치 출처 (스토어 검색 / 탐색 / 외부)
☐ 13. 국가별 설치 Top 3

⭐ *리뷰/평점*
☐ 14. 신규 리뷰 확인 및 답변 필요 여부
☐ 15. 평균 평점 (iOS vs Android 비교)

🔧 *안정성*
☐ 16. ANR Rate / Crash Rate (Android Vitals)
☐ 17. 현재 프로덕션 배포 버전 상태

💳 *수익화 — 크레딧 전환율*
☐ 18. 이번 주 인앱 구매 건수 / 금액
☐ 19. 크레딧 구매 전환율 (설치 대비 결제 %)
☐ 20. 구독/단건 비율 추이

━━━━━━━━━━━━━━━━━━━━━━
📊 *공통 — 월간 누적 (해당 주 확인)*

☐ 21. 누적 다운로드 (iOS + Android 합산)
☐ 22. MAU / DAU 현황 (앱 내 analytics 기준)
☐ 23. 버전 정합성 — 현재 스토어 버전 vs GitHub 최신 릴리스

━━━━━━━━━━━━━━━━━━━━━━
🎯 *3개월 목표 대비 현황*

다운로드:  1M 목표 500 | 3M 목표 3,000 | 현재 ?
크레딧 전환율: 1M 목표 2% | 3M 목표 5% | 현재 ?
텔레그램 구독자: 1M 목표 300 | 3M 목표 1,500 | 현재 ?

✍️ *확인 후 이 채팅방에 수치를 올려주세요!*"""


def send_telegram_message(bot_token: str, chat_id: str, text: str) -> bool:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
    }
    data = urllib.parse.urlencode(payload).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            if result.get("ok"):
                logger.info("✅ 텔레그램 전송 성공 (message_id=%s)", result["result"]["message_id"])
                return True
            else:
                logger.error("❌ 텔레그램 응답 실패: %s", result)
                return False
    except Exception as exc:
        logger.exception("❌ 텔레그램 전송 예외: %s", exc)
        return False


def main() -> int:
    if not BOT_TOKEN:
        logger.error("PM_BOT_TOKEN 환경변수 미설정")
        return 1
    ok = send_telegram_message(BOT_TOKEN, CHAT_ID, CHECKLIST_TEXT)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
