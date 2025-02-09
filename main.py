import os
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.utils import executor
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import BOT_TOKEN, ADMIN_PASSWORD
from database import init_db, UserCRUD, AssignmentCRUD, SwapCRUD
from keyboards import get_main_keyboard, get_back_keyboard, get_calendar_keyboard
from states import CalendarFSM, SwapFSM
from utils import validate_starshina, schedule_reminders
from scheduler import scheduler

# Настройка логгера
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# Инициализация БД
init_db()

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    """Обработчик команды /start"""
    user_crud = UserCRUD()  # Создаём экземпляр
    user = user_crud.get(message.from_user.id)  #  Вызываем метод у экземпляра
    
    if user:
        kb = get_main_keyboard(user.is_starshina)
        await message.answer("Главное меню:", reply_markup=kb)
    else:
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add("Я старшина", "Я не старшина")
        await message.answer("Выберите роль:", reply_markup=kb)

@dp.message_handler(lambda message: message.text in ["Я старшина", "Я не старшина"])
async def process_role(message: types.Message):
    """Обработка выбора роли"""
    if message.text == "Я старшина":
        await message.answer("Введите пароль старшины:", reply_markup=get_back_keyboard())
        await CalendarFSM.waiting_password.set()
    else:
        if not UserCRUD.exists(message.from_user.id):
            await message.answer("Введите ваше имя для регистрации:")
            await CalendarFSM.registration.set()
        else:
            await show_user_menu(message)

@dp.message_handler(state=CalendarFSM.waiting_password)
async def process_password(message: types.Message, state: FSMContext):
    """Проверка пароля старшины"""
    if message.text == ADMIN_PASSWORD:
        UserCRUD.set_starshina(message.from_user.id, True)
        await message.answer("Доступ разрешён!", reply_markup=get_main_keyboard(True))
    else:
        await message.answer("Неверный пароль!")
    await state.finish()

# ... продолжение следует ...

@dp.message_handler(state=CalendarFSM.registration)
async def process_registration(message: types.Message, state: FSMContext):
    """Обработка регистрации обычного пользователя"""
    if message.text == "Назад":
        await cmd_start(message)
        return
    
    UserCRUD.create(
        telegram_id=message.from_user.id,
        name=message.text,
        is_starshina=False
    )
    await message.answer(f"Добро пожаловать, {message.text}!", reply_markup=get_main_keyboard(False))
    await state.finish()

@dp.message_handler(lambda message: message.text == "Календарь")
@validate_starshina
async def show_calendar_menu(message: types.Message):
    """Меню календаря для старшины"""
    await CalendarFSM.choosing_year.set()
    await message.answer("Выберите год:", reply_markup=get_calendar_keyboard("year"))

@dp.callback_query_handler(lambda c: c.data.startswith("year_"), state=CalendarFSM.choosing_year)
async def process_year(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработка выбора года"""
    year = int(callback_query.data.split("_")[1])
    async with state.proxy() as data:
        data["year"] = year
    await CalendarFSM.next()
    await bot.send_message(
        callback_query.from_user.id,
        "Выберите неделю:",
        reply_markup=get_calendar_keyboard("week", year=year)
    )

@dp.callback_query_handler(lambda c: c.data.startswith("week_"), state=CalendarFSM.choosing_week)
async def process_week(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработка выбора недели"""
    week = int(callback_query.data.split("_")[1])
    async with state.proxy() as data:
        data["week"] = week
    await CalendarFSM.next()
    await bot.send_message(
        callback_query.from_user.id,
        "Выберите день:",
        reply_markup=get_calendar_keyboard("day", year=data["year"], week=week)
    )

@dp.callback_query_handler(lambda c: c.data.startswith("day_"), state=CalendarFSM.choosing_day)
async def process_day(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработка выбора дня"""
    date_str = callback_query.data.split("_")[1]
    async with state.proxy() as data:
        data["date"] = date_str
    users = UserCRUD.get_all()
    kb = types.InlineKeyboardMarkup()
    for user in users:
        kb.add(types.InlineKeyboardButton(
            user.name, 
            callback_data=f"assign_{user.telegram_id}"
        ))
    await bot.send_message(
        callback_query.from_user.id,
        f"Выберите дежурного на {date_str}:",
        reply_markup=kb
    )
    await CalendarFSM.next()

@dp.callback_query_handler(lambda c: c.data.startswith("assign_"), state=CalendarFSM.assigning_user)
async def assign_duty(callback_query: types.CallbackQuery, state: FSMContext):
    """Назначение дежурства"""
    user_id = int(callback_query.data.split("_")[1])
    async with state.proxy() as data:
        date_str = data["date"]
    
    AssignmentCRUD.create(date=date_str, user_id=user_id)
    await bot.send_message(
        callback_query.from_user.id,
        "Дежурство успешно назначено!",
        reply_markup=get_main_keyboard(True)
    )
    
    # Отправка уведомления пользователю
    await send_assignment_notification(user_id, date_str)
    await state.finish()

# ... продолжение следует ...

async def send_assignment_notification(user_id: int, date: str):
    """Отправка уведомления о назначении"""
    user = UserCRUD.get(user_id)
    if user.notify_assignment:
        kb = types.InlineKeyboardMarkup()
        kb.add(
            types.InlineKeyboardButton("✅ Принял", callback_data=f"accept_{date}"),
            types.InlineKeyboardButton("🔄 Обмен", callback_data=f"swap_{date}")
        )
        await bot.send_message(
            user_id,
            f"Вас назначили дежурным на {date}",
            reply_markup=kb
        )
        schedule_reminders(user_id, date)

@dp.callback_query_handler(lambda c: c.data.startswith("accept_"))
async def accept_duty(callback_query: types.CallbackQuery):
    """Подтверждение дежурства"""
    date = callback_query.data.split("_")[1]
    await bot.send_message(
        callback_query.from_user.id,
        f"Вы подтвердили дежурство на {date}!"
    )
    # Уведомление старшины
    await notify_starshina(f"Пользователь {callback_query.from_user.full_name} принял дежурство на {date}")

@dp.callback_query_handler(lambda c: c.data.startswith("swap_"))
async def start_swap(callback_query: types.CallbackQuery, state: FSMContext):
    """Инициализация обмена дежурством"""
    date = callback_query.data.split("_")[1]
    async with state.proxy() as data:
        data["swap_date"] = date
    await SwapFSM.select_user.set()
    users = UserCRUD.get_swappable(callback_query.from_user.id)
    kb = types.InlineKeyboardMarkup()
    for user in users:
        kb.add(types.InlineKeyboardButton(
            user.name, 
            callback_data=f"swap_target_{user.telegram_id}"
        ))
    await bot.send_message(
        callback_query.from_user.id,
        "Выберите пользователя для обмена:",
        reply_markup=kb
    )

@dp.callback_query_handler(lambda c: c.data.startswith("swap_target_"), state=SwapFSM.select_user)
async def select_swap_target(callback_query: types.CallbackQuery, state: FSMContext):
    """Выбор цели для обмена"""
    target_id = int(callback_query.data.split("_")[2])
    async with state.proxy() as data:
        data["target_id"] = target_id
    await SwapFSM.next()
    await bot.send_message(
        callback_query.from_user.id,
        "Введите сообщение для предложения (или отправьте '-' чтобы пропустить):"
    )

@dp.message_handler(state=SwapFSM.enter_message)
async def process_swap_message(message: types.Message, state: FSMContext):
    """Обработка сообщения для обмена"""
    async with state.proxy() as data:
        data["message"] = message.text if message.text != "-" else ""
        swap_date = data["swap_date"]
        target_id = data["target_id"]
    
    proposal_id = SwapCRUD.create_proposal(
        date=swap_date,
        from_user=message.from_user.id,
        to_user=target_id,
        message=data["message"]
    )
    
    # Отправка предложения целевому пользователю
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("✅ Принять", callback_data=f"accept_proposal_{proposal_id}"),
        types.InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_proposal_{proposal_id}")
    )
    
    await bot.send_message(
        target_id,
        f"Вам предложили обмен дежурством на {swap_date}\nСообщение: {data['message']}",
        reply_markup=kb
    )
    
    await message.answer("Предложение отправлено!")
    await state.finish()

@dp.callback_query_handler(lambda c: c.data.startswith("accept_proposal_"))
async def accept_proposal(callback_query: types.CallbackQuery):
    """Принятие предложения обмена"""
    proposal_id = int(callback_query.data.split("_")[2])
    proposal = SwapCRUD.get_proposal(proposal_id)
    
    # Обновляем назначения
    AssignmentCRUD.update_user(proposal.date, proposal.to_user)
    SwapCRUD.update_status(proposal_id, "accepted")
    
    await bot.send_message(
        proposal.from_user,
        f"Пользователь {callback_query.from_user.full_name} принял ваш обмен на {proposal.date}!"
    )
    await bot.send_message(
        proposal.to_user,
        f"Вы теперь дежурите {proposal.date}!"
    )

@dp.message_handler(commands=['clearhistory'])
@validate_starshina
async def clear_history_command(message: types.Message):
    """Очистка истории дежурств"""
    AssignmentCRUD.clear_history()
    await message.answer("История дежурств очищена!")

if __name__ == "__main__":
    scheduler.start()
    executor.start_polling(dp, skip_updates=True)