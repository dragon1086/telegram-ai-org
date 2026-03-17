"""
Telethon 세션 초기화 스크립트 — 최초 1회만 실행.
Rocky가 직접 터미널에서 실행하면 인증 코드 입력 후 .e2e_session 파일이 생성된다.
이후 e2e_telegram_test.py는 저장된 세션을 자동 사용한다.
"""
import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv
from telethon import TelegramClient

load_dotenv(Path(__file__).parent.parent / ".env")

API_ID   = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
PHONE    = os.environ["TELEGRAM_PHONE"]
SESSION  = str(Path(__file__).parent.parent / ".e2e_session")

async def main():
    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.start(phone=PHONE)
    me = await client.get_me()
    print(f"\n✅ 인증 완료! 로그인 계정: {me.first_name} (@{me.username})")
    print(f"📁 세션 저장: {SESSION}.session")
    print("\n이제 터미널을 닫고 Claude에게 e2e 테스트 실행하라고 하면 돼.")
    await client.disconnect()

asyncio.run(main())
