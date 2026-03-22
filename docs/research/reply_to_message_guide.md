# Telegram reply_to_message 완전 가이드
# 작성: aiorg_research_bot | 날짜: 2026-03-22
# 태스크: T-aiorg_pm_bot-279

---

## 1. Telegram Bot API — reply_to_message 필드 스펙

### 위치
`Message` 오브젝트 내 optional 필드.
공식 문서: https://core.telegram.org/bots/api#message

### 필드 정의

| 필드명 | 타입 | 설명 |
|--------|------|------|
| `reply_to_message` | Message (optional) | 같은 채팅/스레드 내 답장 시 원문 메시지 객체 |
| `external_reply` | ExternalReplyInfo (optional) | **다른 채팅/포럼 토픽**에서 온 답장의 원문 정보 |
| `quote` | TextQuote (optional) | 원문의 부분 인용 텍스트 |
| `reply_to_story` | Story (optional) | 스토리에 답장한 경우 |

### reply_to_message 내 접근 가능한 하위 필드

```
reply_to_message.message_id     # Integer  — 원문 메시지 ID
reply_to_message.from_user      # User     — 원문 발신자 (익명 채널이면 None)
reply_to_message.text           # String   — 원문 텍스트 (텍스트 메시지일 때)
reply_to_message.caption        # String   — 미디어 캡션 (사진/파일에 달린 설명)
reply_to_message.photo          # List[PhotoSize] — 사진
reply_to_message.document       # Document — 파일
reply_to_message.sticker        # Sticker  — 스티커
reply_to_message.voice          # Voice    — 음성 메시지
reply_to_message.video          # Video    — 비디오
reply_to_message.date           # Integer  — Unix timestamp
reply_to_message.chat           # Chat     — 원문이 속한 채팅
```

### ⚠️ 엣지케이스 및 제약

| 상황 | 동작 |
|------|------|
| 원문 메시지가 삭제된 경우 | `reply_to_message` 필드 자체가 없음 (None 반환) |
| 다른 채팅/포럼에서 온 답장 | `reply_to_message` 없음, `external_reply` 사용 |
| 익명 채널 관리자가 발송한 원문 | `from_user` = None, `sender_chat` 필드 확인 |
| 중첩 답장 (답장의 답장) | `reply_to_message` 안에 또 `reply_to_message` **없음** (1단계만) |
| 봇 자신의 메시지에 답장 | `from_user.is_bot` = True로 구분 가능 |
| 포럼 스레드 내 답장 | `message_thread_id` 함께 확인 |

---

## 2. aiogram v3 — 사용법

### (1) 기본 reply 감지 및 원문 접근

```python
from aiogram import Router
from aiogram.types import Message

router = Router()

@router.message()
async def handle_reply(message: Message):
    # None 체크 필수
    if message.reply_to_message is None:
        await message.answer("이 메시지는 답장이 아닙니다.")
        return

    replied = message.reply_to_message

    # 원문 텍스트
    original_text = replied.text or replied.caption or "(텍스트 없음)"

    # 원문 발신자 (익명 채널이면 None)
    sender = replied.from_user
    sender_name = sender.full_name if sender else "(익명/채널)"

    # 원문 message_id
    original_id = replied.message_id

    await message.answer(
        f"원문 작성자: {sender_name}\n"
        f"원문 ID: {original_id}\n"
        f"원문 내용: {original_text}"
    )
```

### (2) 필터로 reply 메시지만 걸러내기

```python
from aiogram import F

# reply 메시지만 처리하는 핸들러
@router.message(F.reply_to_message.as_("replied"))
async def only_reply_handler(message: Message, replied: Message):
    await message.answer(f"답장 원문: {replied.text}")
```

### (3) 미디어 포함 reply 처리

```python
@router.message()
async def handle_media_reply(message: Message):
    replied = message.reply_to_message
    if replied is None:
        return

    if replied.photo:
        # 가장 큰 해상도 선택
        photo = replied.photo[-1]
        await message.answer(f"사진에 답장함. file_id={photo.file_id}")

    elif replied.document:
        await message.answer(f"파일에 답장함. 파일명={replied.document.file_name}")

    elif replied.sticker:
        await message.answer(f"스티커에 답장함. emoji={replied.sticker.emoji}")

    elif replied.voice:
        await message.answer("음성 메시지에 답장함.")

    elif replied.text:
        await message.answer(f"텍스트에 답장함: {replied.text}")

    else:
        await message.answer("알 수 없는 미디어 타입에 답장함.")
```

### (4) 외부 채팅 답장 처리 (external_reply)

```python
@router.message()
async def handle_external_reply(message: Message):
    if message.external_reply:
        ext = message.external_reply
        # origin 안에 발신자 정보 있음
        await message.answer(f"다른 채팅의 메시지에 답장함: {ext.origin}")
```

---

## 3. python-telegram-bot v20+ — 사용법

### (1) 기본 reply 감지 및 원문 접근

```python
from telegram.ext import Application, MessageHandler, filters
from telegram import Update
from telegram.ext import ContextTypes

async def handle_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if message is None:
        return

    replied = message.reply_to_message  # None이면 reply 아님

    if replied is None:
        await message.reply_text("이 메시지는 답장이 아닙니다.")
        return

    # 원문 텍스트 (없으면 caption 시도)
    original_text = replied.text or replied.caption or "(텍스트 없음)"

    # 원문 발신자 (from_user)
    sender = replied.from_user
    sender_name = sender.full_name if sender else "(익명/채널)"

    await message.reply_text(
        f"원문 작성자: {sender_name}\n"
        f"원문 내용: {original_text}"
    )

app = Application.builder().token("YOUR_TOKEN").build()
app.add_handler(MessageHandler(filters.TEXT & filters.REPLY, handle_reply))
```

### (2) filters.REPLY 필터 활용

```python
# filters.REPLY: reply_to_message가 있는 메시지만 통과
app.add_handler(MessageHandler(filters.REPLY, handle_reply))

# 텍스트 reply만
app.add_handler(MessageHandler(filters.TEXT & filters.REPLY, handle_reply))
```

### (3) 미디어 포함 reply 처리

```python
async def handle_media_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    replied = message.reply_to_message
    if replied is None:
        return

    if replied.photo:
        largest = replied.photo[-1]  # 가장 큰 해상도
        await message.reply_text(f"사진에 답장. file_id={largest.file_id}")

    elif replied.document:
        await message.reply_text(f"파일에 답장. 파일명={replied.document.file_name}")

    elif replied.sticker:
        await message.reply_text(f"스티커에 답장. emoji={replied.sticker.emoji}")

    elif replied.text:
        await message.reply_text(f"텍스트에 답장: {replied.text}")
```

---

## 4. 라이브러리 비교표

| 항목 | aiogram v3 | python-telegram-bot v20+ |
|------|-----------|--------------------------|
| reply 감지 | `message.reply_to_message is not None` | `message.reply_to_message is not None` |
| 필터 | `F.reply_to_message` | `filters.REPLY` |
| 원문 텍스트 | `message.reply_to_message.text` | `message.reply_to_message.text` |
| 원문 발신자 | `reply.from_user` | `reply.from_user` |
| 원문 ID | `reply.message_id` | `reply.message_id` |
| 외부 채팅 답장 | `message.external_reply` | `message.external_reply` |
| 미디어 접근 | `reply.photo`, `reply.document` 등 | 동일 |
| async 지원 | 기본 (완전 async) | v20부터 기본 async |

---

## 5. 주의사항 체크리스트

- [ ] **항상 None 체크**: `reply_to_message`는 Optional — `if message.reply_to_message:` 로 먼저 확인
- [ ] **text vs caption 분기**: 미디어 메시지는 `text`가 None이고 `caption`에 텍스트가 들어옴
- [ ] **익명 발신자**: `from_user`가 None일 수 있음 — 채널 메시지는 `sender_chat` 확인
- [ ] **삭제된 원문**: `reply_to_message` 필드 자체가 없어짐, 방어 코드 필요
- [ ] **중첩 답장**: 1단계만 제공됨 — `reply_to_message.reply_to_message`는 항상 None
- [ ] **외부 채팅**: `reply_to_message` 없고 `external_reply` 사용
- [ ] **포럼 스레드**: `message_thread_id` 함께 체크
- [ ] **봇 자신의 메시지**: `from_user.is_bot == True` 로 구분

---

## 6. 현재 프로젝트(telegram-ai-org) 적용 포인트

사용자가 봇의 응답에 "답장"할 때 원문(봇 메시지) 내용을 컨텍스트로 활용하려면:

```python
# core/telegram_relay.py 또는 메시지 수신 핸들러에 추가
async def handle_incoming(message: Message):
    context_text = ""

    if message.reply_to_message:
        replied = message.reply_to_message
        # 봇이 보낸 원문이면
        if replied.from_user and replied.from_user.is_bot:
            context_text = replied.text or replied.caption or ""

    # context_text를 태스크 배경정보로 주입
    task_context = {
        "user_message": message.text,
        "reply_context": context_text,  # ← 이 필드 추가
    }
```

이 방식으로 사용자가 봇 답변에 답장하면, 그 봇 답변 원문이 자동으로 태스크 컨텍스트에 포함됩니다.

---

## 참고 문서

- Telegram Bot API Message: https://core.telegram.org/bots/api#message
- aiogram v3 Message: https://docs.aiogram.dev/en/latest/api/types/message.html
- python-telegram-bot v21 Message: https://docs.python-telegram-bot.org/en/v21.9/telegram.message.html
- python-telegram-bot examples: https://docs.python-telegram-bot.org/en/stable/examples.html
