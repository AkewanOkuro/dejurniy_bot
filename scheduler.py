from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot
from config import TIMEZONE

scheduler = AsyncIOScheduler(timezone=TIMEZONE)

async def send_reminder(user_id: int, text: str):
    try:
        await Bot.get_current().send_message(user_id, text)
    except Exception as e:
        pass  # Логирование ошибок можно добавить здесь