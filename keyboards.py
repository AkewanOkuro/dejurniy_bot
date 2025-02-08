from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime

def get_main_keyboard(is_starshina: bool) -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    if is_starshina:
        kb.add(KeyboardButton("Люди"), KeyboardButton("Календарь"))
        kb.add(KeyboardButton("Расписание"), KeyboardButton("Очистить историю"))
    else:
        kb.add(KeyboardButton("Мои дежурства"), KeyboardButton("Настройки"))
    return kb

def get_back_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("Назад"))

def get_calendar_keyboard(mode: str, **kwargs) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    if mode == "year":
        current_year = datetime.now().year
        for year in [current_year - 1, current_year, current_year + 1]:
            kb.add(InlineKeyboardButton(str(year), callback_data=f"year_{year}"))
    return kb