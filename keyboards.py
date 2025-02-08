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

def get_calendar_keyboard(mode: str, year: int = None, week: int = None):
    kb = InlineKeyboardMarkup()
    
    # Для выбора года
    if mode == "year":
        current_year = datetime.now().year
        for y in [current_year - 1, current_year, current_year + 1]:
            kb.add(InlineKeyboardButton(str(y), callback_data=f"year_{y}"))
    
    # Для выбора недели
    elif mode == "week":
        for w in range(1, 53):
            kb.add(InlineKeyboardButton(f"Неделя {w}", callback_data=f"week_{w}"))
    
    # Для выбора дня
    elif mode == "day":
        start_date = datetime.fromisocalendar(year, week, 1)
        for day in range(7):
            current_date = start_date + timedelta(days=day)
            kb.add(InlineKeyboardButton(
                text=current_date.strftime("%d.%m"),
                callback_data=f"day_{current_date.strftime('%Y-%m-%d')}"
            ))
    
    return kb

# def get_calendar_keyborad(year: int, week: int):
    # kb = InlineKeyboardMarkup(row_width=7)
    # start_date = datetime.fromisocalendar(year, week, 1)
    # for day in range(7):
        # current_date = start_date + timedelta(days=day)
        # kb.insert(InlineKeyboardButton(
            # text=current_date.strftime("%d.%m"),
            # callback_data=f"day_{current_date.strftime('%Y-%m-%d')}"
        # ))
    # return kb
