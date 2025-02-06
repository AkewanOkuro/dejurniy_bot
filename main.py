import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, executor
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# ВАЖНО: Вставьте сюда токен вашего бота
API_TOKEN = '7863992557:AAH1Dz6Iy4foxSWseCOP29IR4wpq9y0OhQs'

# ВАЖНО: Вставьте сюда пароль старшины (односторонний вход для доступа к функционалу)
STARSHINA_PASSWORD = 'starshina'

# Настройка логирования
logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# Подключаемся к базе данных SQLite (файл bot.db будет создан в рабочей папке)
conn = sqlite3.connect('bot.db')
cursor = conn.cursor()

# Создадим таблицы для хранения пользователей, дежурств, истории, предложений обмена и статистики.
def init_db():
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                        telegram_id INTEGER PRIMARY KEY,
                        name TEXT,
                        is_starshina INTEGER DEFAULT 0,
                        notify_assignment INTEGER DEFAULT 1,
                        notify_exchange INTEGER DEFAULT 1,
                        reminder_time_day TEXT DEFAULT '06:00',
                        reminder_time_before TEXT DEFAULT '08:00'
                      )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS assignments (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date TEXT,  -- в формате YYYY-MM-DD
                        user_id INTEGER,
                        assigned_at TEXT,
                        FOREIGN KEY(user_id) REFERENCES users(telegram_id)
                      )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS assignment_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date TEXT,
                        user_id INTEGER,
                        changed_at TEXT
                      )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS exchange_proposals (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        assignment_date TEXT,
                        from_user INTEGER,
                        to_user INTEGER,
                        message TEXT,
                        status TEXT DEFAULT 'pending',  -- pending, accepted, declined, canceled
                        created_at TEXT
                      )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS changestat (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        from_user INTEGER,
                        to_user INTEGER,
                        date TEXT,
                        changed_at TEXT
                      )''')
    conn.commit()

init_db()

# --- Клавиатуры --- #

# Стартовая клавиатура: выбор роли
start_kb = ReplyKeyboardMarkup(resize_keyboard=True)
start_kb.add(KeyboardButton("Я старшина"), KeyboardButton("Я не старшина"))

# Клавиатура "Назад" для возврата в предыдущее меню
back_kb = ReplyKeyboardMarkup(resize_keyboard=True)
back_kb.add(KeyboardButton("Назад"))

# --- Вспомогательные функции для работы с БД --- #
def user_exists(telegram_id: int) -> bool:
    cursor.execute("SELECT telegram_id FROM users WHERE telegram_id = ?", (telegram_id,))
    return cursor.fetchone() is not None

def add_user(telegram_id: int, name: str):
    cursor.execute("INSERT OR REPLACE INTO users (telegram_id, name) VALUES (?, ?)", (telegram_id, name))
    conn.commit()

def update_user_name(telegram_id: int, new_name: str):
    cursor.execute("UPDATE users SET name = ? WHERE telegram_id = ?", (new_name, telegram_id))
    conn.commit()

def delete_user(telegram_id: int):
    cursor.execute("DELETE FROM users WHERE telegram_id = ?", (telegram_id,))
    # Удаляем будущие дежурства данного пользователя
    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("DELETE FROM assignments WHERE user_id = ? AND date >= ?", (telegram_id, today))
    conn.commit()

def set_user_role(telegram_id: int, is_starshina: bool):
    cursor.execute("UPDATE users SET is_starshina = ? WHERE telegram_id = ?", (1 if is_starshina else 0, telegram_id))
    conn.commit()

def get_all_users() -> list:
    cursor.execute("SELECT telegram_id, name FROM users ORDER BY name")
    return cursor.fetchall()

def get_users_for_exchange() -> list:
    # Возвращаем пользователей, у которых разрешён обмен (notify_exchange = 1)
    cursor.execute("SELECT telegram_id, name FROM users WHERE notify_exchange = 1")
    return cursor.fetchall()

def add_assignment(date: str, user_id: int):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT INTO assignments (date, user_id, assigned_at) VALUES (?, ?, ?)", (date, user_id, now))
    # Сохраняем запись в истории
    cursor.execute("INSERT INTO assignment_history (date, user_id, changed_at) VALUES (?, ?, ?)", (date, user_id, now))
    conn.commit()

def delete_assignment(date: str, user_id: int):
    cursor.execute("DELETE FROM assignments WHERE date = ? AND user_id = ?", (date, user_id))
    conn.commit()

def get_upcoming_assignments() -> list:
    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("SELECT a.date, u.name FROM assignments a JOIN users u ON a.user_id = u.telegram_id WHERE date >= ? ORDER BY date", (today,))
    return cursor.fetchall()

def add_exchange_proposal(assignment_date: str, from_user: int, to_user: int, message: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT INTO exchange_proposals (assignment_date, from_user, to_user, message, created_at) VALUES (?, ?, ?, ?, ?)",
                   (assignment_date, from_user, to_user, message, now))
    conn.commit()
    return cursor.lastrowid

def update_exchange_proposal_status(proposal_id: int, status: str):
    cursor.execute("UPDATE exchange_proposals SET status = ? WHERE id = ?", (status, proposal_id))
    conn.commit()

def add_changestat(from_user: int, to_user: int, date: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT INTO changestat (from_user, to_user, date, changed_at) VALUES (?, ?, ?, ?)",
                   (from_user, to_user, date, now))
    conn.commit()

def clear_history(before_date: str):
    cursor.execute("DELETE FROM assignment_history WHERE date < ?", (before_date,))
    conn.commit()

# --- Обработчики команд --- #

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    """
    Стартовая команда, показывает выбор ролей.
    """
    await message.answer("Выберите вашу роль:", reply_markup=start_kb)

# --- Обработка выбора роли --- #
@dp.message_handler(lambda message: message.text in ["Я старшина", "Я не старшина"])
async def role_choice(message: types.Message):
    if message.text == "Я старшина":
        # Запрос пароля
        await message.answer("Введите пароль старшины:", reply_markup=back_kb)
        # Сохраняем состояние пользователя для ожидания пароля
        dp.current_state(user=message.from_user.id).update_data(expect_starshina_password=True)
    else:
        # Если пользователь не зарегистрирован, переходим к регистрации
        if not user_exists(message.from_user.id):
            await message.answer("Введите ваше имя для регистрации:", reply_markup=back_kb)
            dp.current_state(user=message.from_user.id).update_data(expect_registration_name=True)
        else:
            # Если уже зарегистрирован, переходим в меню обычного пользователя
            await show_user_menu(message)

# --- Обработка текстовых сообщений (регистрация, ввод пароля и т.д.) --- #
@dp.message_handler()
async def text_handler(message: types.Message, state: types.SimpleNamespace = None):
    # Получаем состояние пользователя
    data = await dp.current_state(user=message.from_user.id).get_data()
    # Если нажали "Назад", возвращаем в стартовое меню
    if message.text == "Назад":
        await cmd_start(message)
        return

    # Обработка ввода пароля старшины
    if data.get('expect_starshina_password'):
        if message.text == STARSHINA_PASSWORD:
            # Устанавливаем роль старшины для пользователя
            add_user(message.from_user.id, message.from_user.full_name)
            set_user_role(message.from_user.id, True)
            await message.answer("Пароль верный! Добро пожаловать в меню старшины.", reply_markup=starshina_menu())
        else:
            await message.answer("Неверный пароль. Попробуйте ещё раз или нажмите 'Назад'.")
        # Сброс состояния ожидания пароля
        await dp.current_state(user=message.from_user.id).update_data(expect_starshina_password=False)
        return

    # Обработка регистрации обычного пользователя
    if data.get('expect_registration_name'):
        # Сохраняем введённое имя и регистрируем пользователя
        add_user(message.from_user.id, message.text)
        set_user_role(message.from_user.id, False)
        # Уведомляем старшину о новой регистрации
        await notify_starshina(f"Новый пользователь зарегистрировался: {message.text} (ID: {message.from_user.id})")
        await message.answer(f"Вы зарегистрированы как {message.text}.", reply_markup=user_menu())
        await dp.current_state(user=message.from_user.id).update_data(expect_registration_name=False)
        return

    # Прочие текстовые сообщения можно обрабатывать здесь
    await message.answer("Не понимаю команду. Нажмите 'Назад' для возврата в главное меню.")

# --- Функции для показа меню --- #
def starshina_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("Люди"))
    kb.add(KeyboardButton("Календарь"))
    kb.add(KeyboardButton("Расписание дежурств"))
    kb.add(KeyboardButton("Назад"))
    return kb

def user_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("Посмотреть график дежурств"))
    kb.add(KeyboardButton("Настройки аккаунта"))
    kb.add(KeyboardButton("Настройки уведомлений"))
    kb.add(KeyboardButton("Назад"))
    return kb

async def show_user_menu(message: types.Message):
    await message.answer("Ваше меню:", reply_markup=user_menu())

# --- Уведомление старшине (отправка сообщений на специальный ID) --- #
# В этом примере старшина может быть несколькими, поэтому отправляем всем, у кого is_starshina = 1
async def notify_starshina(text: str):
    cursor.execute("SELECT telegram_id FROM users WHERE is_starshina = 1")
    starshinas = cursor.fetchall()
    for s in starshinas:
        try:
            await bot.send_message(s[0], text)
        except Exception as e:
            logging.error(f"Ошибка при уведомлении старшины {s[0]}: {e}")

# --- Старшина: обработка меню "Люди" --- #
@dp.message_handler(lambda message: message.text == "Люди")
async def starshina_people(message: types.Message):
    users = get_all_users()
    if not users:
        await message.answer("Нет зарегистрированных пользователей.", reply_markup=starshina_menu())
        return
    kb = InlineKeyboardMarkup(row_width=1)
    for uid, name in users:
        # Каждая кнопка передаёт данные: action=edit&uid=...
        kb.add(InlineKeyboardButton(name, callback_data=f"edit_user:{uid}"))
    kb.add(InlineKeyboardButton("Назад", callback_data="back_starshina"))
    await message.answer("Список пользователей:", reply_markup=kb)

# Обработка нажатия на пользователя в списке старшины
@dp.callback_query_handler(lambda c: c.data and c.data.startswith("edit_user:"))
async def process_edit_user(callback_query: types.CallbackQuery):
    uid = int(callback_query.data.split(":")[1])
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("Редактировать имя", callback_data=f"rename_user:{uid}"),
           InlineKeyboardButton("Удалить", callback_data=f"delete_user:{uid}"))
    kb.add(InlineKeyboardButton("Назад", callback_data="back_people"))
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id, "Выберите действие:", reply_markup=kb)

# Обработка кнопок редактирования/удаления пользователя
@dp.callback_query_handler(lambda c: c.data and c.data.startswith("rename_user:"))
async def process_rename_user(callback_query: types.CallbackQuery):
    uid = int(callback_query.data.split(":")[1])
    # Сохраняем состояние для ожидания нового имени
    dp.current_state(user=callback_query.from_user.id).update_data(rename_uid=uid)
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id, "Введите новое имя для пользователя (или нажмите 'Назад'):")

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("delete_user:"))
async def process_delete_user(callback_query: types.CallbackQuery):
    uid = int(callback_query.data.split(":")[1])
    # Удаляем пользователя
    cursor.execute("SELECT name FROM users WHERE telegram_id = ?", (uid,))
    row = cursor.fetchone()
    name = row[0] if row else "Пользователь"
    delete_user(uid)
    await notify_starshina(f"Пользователь {name} (ID: {uid}) удалён.")
    await bot.answer_callback_query(callback_query.id, f"{name} удалён.")
    await bot.send_message(callback_query.from_user.id, f"Пользователь {name} удалён.", reply_markup=starshina_menu())

# Обработка ввода нового имени для пользователя (после нажатия "Редактировать имя")
@dp.message_handler(lambda message: dp.current_state(user=message.from_user.id).get_data().get('rename_uid') is not None)
async def process_new_name(message: types.Message):
    data = await dp.current_state(user=message.from_user.id).get_data()
    uid = data.get('rename_uid')
    old_name = ""
    cursor.execute("SELECT name FROM users WHERE telegram_id = ?", (uid,))
    row = cursor.fetchone()
    if row:
        old_name = row[0]
    update_user_name(uid, message.text)
    await notify_starshina(f"Пользователь изменил имя: {old_name} → {message.text}")
    await message.answer("Имя обновлено.", reply_markup=starshina_menu())
    await dp.current_state(user=message.from_user.id).update_data(rename_uid=None)

# --- Старшина: обработка меню "Календарь" --- #
@dp.message_handler(lambda message: message.text == "Календарь")
async def starshina_calendar(message: types.Message):
    # Здесь реализуем выбор года, месяца/недели и дня.
    # Для упрощения приведён пример: предлагаем ввести дату в формате YYYY-MM-DD.
    await message.answer("Введите дату дежурства (формат YYYY-MM-DD):", reply_markup=back_kb)
    dp.current_state(user=message.from_user.id).update_data(expect_assignment_date=True)

@dp.message_handler(lambda message: dp.current_state(user=message.from_user.id).get_data().get('expect_assignment_date'))
async def process_assignment_date(message: types.Message):
    # Проверка корректности даты не делается для простоты, предполагаем правильный ввод.
    assignment_date = message.text
    # Сохраним дату в состоянии для дальнейшего выбора пользователя
    await dp.current_state(user=message.from_user.id).update_data(assignment_date=assignment_date, expect_assignment_date=False)
    # Выбираем пользователя для дежурства
    users = get_all_users()
    kb = InlineKeyboardMarkup(row_width=1)
    for uid, name in users:
        kb.add(InlineKeyboardButton(name, callback_data=f"assign_user:{uid}"))
    kb.add(InlineKeyboardButton("Назад", callback_data="back_calendar"))
    await message.answer("Выберите пользователя для дежурства:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("assign_user:"))
async def process_assignment(callback_query: types.CallbackQuery):
    uid = int(callback_query.data.split(":")[1])
    # Получаем выбранную дату из состояния
    data = await dp.current_state(user=callback_query.from_user.id).get_data()
    assignment_date = data.get('assignment_date')
    add_assignment(assignment_date, uid)
    await notify_starshina(f"На {assignment_date} назначен пользователь ID {uid}.")
    await bot.answer_callback_query(callback_query.id, "Дежурство назначено.")
    await bot.send_message(callback_query.from_user.id, "Дежурство назначено.", reply_markup=starshina_menu())

# --- Старшина: обработка меню "Расписание дежурств" --- #
@dp.message_handler(lambda message: message.text == "Расписание дежурств")
async def starshina_schedule(message: types.Message):
    assignments = get_upcoming_assignments()
    if not assignments:
        await message.answer("Нет предстоящих дежурств.", reply_markup=starshina_menu())
        return
    text = "Предстоящие дежурства:\n"
    for date, name in assignments:
        text += f"{date}: {name}\n"
    # Здесь можно сделать кнопки для отмены или переназначения по каждой записи.
    # Для упрощения отправляем текст и просим связаться со старшиной для редактирования.
    await message.answer(text, reply_markup=starshina_menu())

# --- Обычный пользователь: "Посмотреть график дежурств" --- #
@dp.message_handler(lambda message: message.text == "Посмотреть график дежурств")
async def user_view_schedule(message: types.Message):
    assignments = get_upcoming_assignments()
    if not assignments:
        await message.answer("График пуст.", reply_markup=user_menu())
        return
    text = "График дежурств:\n"
    for date, name in assignments:
        text += f"{date}: {name}\n"
    await message.answer(text, reply_markup=user_menu())

# --- Обычный пользователь: "Настройки аккаунта" --- #
@dp.message_handler(lambda message: message.text == "Настройки аккаунта")
async def user_account_settings(message: types.Message):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("Изменить имя"))
    kb.add(KeyboardButton("Удалить аккаунт"))
    kb.add(KeyboardButton("Назад"))
    await message.answer("Настройки аккаунта:", reply_markup=kb)

@dp.message_handler(lambda message: message.text == "Изменить имя")
async def user_change_name(message: types.Message):
    dp.current_state(user=message.from_user.id).update_data(expect_change_name=True)
    await message.answer("Введите новое имя (или 'Назад' для отмены):", reply_markup=back_kb)

@dp.message_handler(lambda message: dp.current_state(user=message.from_user.id).get_data().get('expect_change_name'))
async def process_change_name(message: types.Message):
    if message.text == "Назад":
        await show_user_menu(message)
        return
    old_data = await dp.current_state(user=message.from_user.id).get_data()
    # Получаем старое имя для уведомления старшины
    cursor.execute("SELECT name FROM users WHERE telegram_id = ?", (message.from_user.id,))
    row = cursor.fetchone()
    old_name = row[0] if row else ""
    update_user_name(message.from_user.id, message.text)
    await notify_starshina(f"Пользователь изменил имя: {old_name} → {message.text}")
    await message.answer("Имя изменено.", reply_markup=user_menu())
    await dp.current_state(user=message.from_user.id).update_data(expect_change_name=False)

@dp.message_handler(lambda message: message.text == "Удалить аккаунт")
async def user_delete_account(message: types.Message):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("Да, удалить", callback_data="confirm_delete_account"),
           InlineKeyboardButton("Отмена", callback_data="cancel_delete_account"))
    await message.answer("Вы уверены, что хотите удалить аккаунт?", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data in ["confirm_delete_account", "cancel_delete_account"])
async def process_delete_account(callback_query: types.CallbackQuery):
    if callback_query.data == "confirm_delete_account":
        delete_user(callback_query.from_user.id)
        await notify_starshina(f"Пользователь ID {callback_query.from_user.id} удалил свой аккаунт.")
        await bot.answer_callback_query(callback_query.id, "Аккаунт удалён.")
        await bot.send_message(callback_query.from_user.id, "Ваш аккаунт удалён.", reply_markup=start_kb)
    else:
        await bot.answer_callback_query(callback_query.id, "Удаление отменен
