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