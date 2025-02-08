from aiogram import Bot
from scheduler import scheduler
from database import UserCRUD, AssignmentCRUD
from datetime import datetime, timedelta
from aiogram import types
from database import UserCRUD

async def notify_starshina(message: str):
    starshinas = UserCRUD.get_starshinas()
    for s in starshinas:
        await types.Bot.get_current().send_message(s.telegram_id, message)

def validate_starshina(func):
    async def wrapper(message: types.Message, *args, **kwargs):
        if not UserCRUD.is_starshina(message.from_user.id):
            await message.answer("❌ Доступ запрещён!")
            return
        return await func(message, *args, **kwargs)
    return wrapper

async def schedule_reminders(user_id: int, date: str):
    """Настраивает напоминания для пользователя"""
    user = UserCRUD().get(user_id)
    
    # Напоминание в день дежурства
    if user.reminder_time_day:
        hour, minute = map(int, user.reminder_time_day.split(':'))
        scheduler.add_job(
            send_reminder,
            'date',
            run_date=datetime.strptime(date, "%Y-%m-%d").replace(hour=hour, minute=minute),
            args=[user_id, f"Напоминание: вы дежурите сегодня в {user.reminder_time_day}!"]
        )
    
    # Напоминание за день до дежурства
    if user.reminder_time_before:
        day_before = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=1)).date()
        hour, minute = map(int, user.reminder_time_before.split(':'))
        scheduler.add_job(
            send_reminder,
            'date',
            run_date=datetime.combine(day_before, datetime.min.time()).replace(hour=hour, minute=minute),
            args=[user_id, f"Напоминание: вы дежурите завтра в {user.reminder_time_before}!"]
        )

async def send_reminder(user_id: int, text: str):
    """Отправляет напоминание пользователю"""
    try:
        await Bot.get_current().send_message(user_id, text)
    except Exception as e:
        pass  # Игнорируем ошибки (например, пользователь заблокировал бота)
