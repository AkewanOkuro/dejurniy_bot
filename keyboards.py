from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta

def get_main_keyboard(is_starshina: bool):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    if is_starshina:
        kb.row(KeyboardButton("Люди"), KeyboardButton("Календарь"))
        kb.row(KeyboardButton("Расписание"), KeyboardButton("Очистить историю"))
    else:
        kb.row(KeyboardButton("Мои дежурства"), KeyboardButton("Настройки"))
    return kb

def get_back_keyboard():
    return ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("Назад"))

def generate_week_buttons(year: int, week: int):
    kb = InlineKeyboardMarkup(row_width=7)
    start_date = datetime.fromisocalendar(year, week, 1)
    for day in range(7):
        current_date = start_date + timedelta(days=day)
        kb.insert(InlineKeyboardButton(
            text=current_date.strftime("%d.%m"),
            callback_data=f"day_{current_date.strftime('%Y-%m-%d')}"
        ))
    return kb