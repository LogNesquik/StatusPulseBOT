import asyncio
import logging
import os

import httpx
from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message

from bot.api_client import StatusPulseAPI

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)
router = Router()
api = StatusPulseAPI()


def _chat_id(message: Message) -> int:
    # Only private chats are supported; never link a group chat to an account.
    return message.chat.id


def _status_icon(value: str) -> str:
    return {"up": "✅ UP", "down": "🔴 DOWN", "unknown": "⚪ UNKNOWN"}.get(value, "⚪ UNKNOWN")


@router.message(CommandStart())
async def start(message: Message, command: CommandObject):
    if message.chat.type != "private":
        await message.answer("StatusPulse works in a private chat. Open the bot directly to continue.")
        return
    if command.args:
        await _link_account(message, command.args.strip())
        return
    await message.answer(
        "👋 StatusPulse\n\n"
        "Я отправляю уведомления о сбоях и восстановлении твоих сайтов/API.\n\n"
        "1. Войди в StatusPulse API и создай код привязки: POST /api/v1/telegram/link-code/\n"
        "2. Отправь сюда /link КОД\n\n"
        "/status — состояние сайтов\n"
        "/incidents — последние инциденты\n"
        "/help — помощь"
    )


async def _link_account(message: Message, code: str):
    try:
        data = await api.link(code, _chat_id(message))
        await message.answer(f"✅ Telegram подключён к аккаунту {data.get('username', '')}.\nТеперь можно использовать /status и /incidents.")
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json().get("detail", "Не удалось привязать аккаунт.")
        except ValueError:
            detail = "Не удалось привязать аккаунт. Проверь код и попробуй снова."
        await message.answer(f"❌ {detail}")
    except httpx.HTTPError:
        logger.exception("Could not contact StatusPulse API")
        await message.answer("Сейчас не удаётся связаться с сервером. Попробуй немного позже.")


@router.message(Command("link"))
async def link_command(message: Message, command: CommandObject):
    if message.chat.type != "private":
        await message.answer("Для безопасности привяжи аккаунт в личном чате с ботом.")
        return
    if not command.args:
        await message.answer("Использование: /link КОД\nКод можно создать через POST /api/v1/telegram/link-code/ после авторизации в API.")
        return
    await _link_account(message, command.args.strip())


@router.message(Command("status"))
async def status_command(message: Message):
    if message.chat.type != "private":
        await message.answer("Используй команду в личном чате с ботом.")
        return
    try:
        data = await api.monitors(_chat_id(message))
        monitors = data.get("monitors", [])
        if not monitors:
            await message.answer("Пока нет сайтов для мониторинга. Создай монитор через API: POST /api/v1/monitors/.")
            return
        lines = [f"📡 StatusPulse — {data.get('username', 'account')}", ""]
        for item in monitors[:30]:
            active_label = "" if item["is_active"] else " (пауза)"
            lines.append(f"{_status_icon(item['status'])} {item['name']}{active_label}\n{item['url']}")
        if len(monitors) > 30:
            lines.append(f"… и ещё {len(monitors) - 30}")
        await message.answer("\n\n".join(lines), disable_web_page_preview=True)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            await message.answer("Аккаунт не подключён. Создай код в API и отправь /link КОД.")
        else:
            await message.answer("Не удалось загрузить состояние. Попробуй позже.")
    except httpx.HTTPError:
        logger.exception("Could not contact StatusPulse API")
        await message.answer("Сейчас не удаётся связаться с сервером. Попробуй позже.")


@router.message(Command("incidents"))
async def incidents_command(message: Message):
    if message.chat.type != "private":
        await message.answer("Используй команду в личном чате с ботом.")
        return
    try:
        incidents = await api.incidents(_chat_id(message))
        if not incidents:
            await message.answer("Инцидентов пока нет.")
            return
        lines = ["🧾 Последние инциденты:", ""]
        for item in incidents[:10]:
            state = "🔴 Открыт" if item["state"] == "open" else "✅ Решён"
            lines.append(f"{state}: {item['monitor_name']}\nНачало: {item['started_at']}\n{item['monitor_url']}")
        await message.answer("\n\n".join(lines), disable_web_page_preview=True)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            await message.answer("Аккаунт не подключён. Создай код в API и отправь /link КОД.")
        else:
            await message.answer("Не удалось загрузить инциденты. Попробуй позже.")
    except httpx.HTTPError:
        logger.exception("Could not contact StatusPulse API")
        await message.answer("Сейчас не удаётся связаться с сервером. Попробуй позже.")


@router.message(Command("help"))
async def help_command(message: Message):
    await message.answer(
        "Команды StatusPulse:\n"
        "/start — старт и инструкция\n"
        "/link КОД — привязать аккаунт\n"
        "/status — текущие статусы сайтов\n"
        "/incidents — последние инциденты"
    )


async def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN is empty. Set it in .env to start the bot container.")
        return
    bot = Bot(token=token)
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    logger.info("Starting StatusPulse Telegram bot polling")
    await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
