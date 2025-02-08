from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot
from config import TIMEZONE
from database import SwapCRUD, AssignmentCRUD, UserCRUD

scheduler = AsyncIOScheduler(timezone=TIMEZONE)

async def check_pending_swaps():
    pending = SwapCRUD().get_pending()
    for proposal in pending:
        # Автоматическая отмена через 24 часа
        if datetime.now() - proposal.created_at > timedelta(hours=24):
            SwapCRUD().update_status(proposal.id, "expired")
            await Bot.get_current().send_message(
                proposal.from_user,
                f"Предложение обмена на {proposal.date} истекло"
            )

async def send_reminders():
    today = datetime.now().strftime("%Y-%m-%d")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    
    # Напоминания на сегодня
    for assignment in AssignmentCRUD().get_by_date(today):
        user = UserCRUD().get(assignment.user_id)
        if user.reminder_time_day:
            await Bot.get_current().send_message(
                user.telegram_id,
                f"Напоминание: вы дежурите сегодня в {user.reminder_time_day}!"
            )
    
    # Напоминания завтра
    for assignment in AssignmentCRUD().get_by_date(tomorrow):
        user = UserCRUD().get(assignment.user_id)
        if user.reminder_time_before:
            await Bot.get_current().send_message(
                user.telegram_id,
                f"Напоминание: вы дежурите завтра в {user.reminder_time_before}!"
            )

scheduler.add_job(check_pending_swaps, 'interval', hours=1)
scheduler.add_job(send_reminders, 'cron', hour=0, minute=5)