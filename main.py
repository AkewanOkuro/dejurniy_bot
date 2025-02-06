import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, executor
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# ВАЖНО: Вставьте сюда токен вашего бота
API_TOKEN = 'YOUR_TELEGRAM_BOT_TOKEN'

# ВАЖНО: Вставьте сюда пароль старшины (односторонний вход для доступа к функционалу)
STARSHINA_PASSWORD = 'ВАШ_ПАРОЛЬ'

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
        await bot.answer_callback_query(callback_query.id, "Удаление отменено.")
        await bot.send_message(callback_query.from_user.id, "Действие отменено.", reply_markup=user_menu())

# --- Обычный пользователь: "Настройки уведомлений" --- #
@dp.message_handler(lambda message: message.text == "Настройки уведомлений")
async def user_notification_settings(message: types.Message):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("Уведомление о назначении: Вкл/Выкл"))
    kb.add(KeyboardButton("Уведомление о предложении поменяться: Вкл/Выкл"))
    kb.add(KeyboardButton("Настроить напоминание в день дежурства"))
    kb.add(KeyboardButton("Настроить напоминание за день до дежурства"))
    kb.add(KeyboardButton("Назад"))
    await message.answer("Настройки уведомлений:", reply_markup=kb)

@dp.message_handler(lambda message: message.text.startswith("Уведомление о назначении"))
async def toggle_assignment_notify(message: types.Message):
    # Получаем текущее значение
    cursor.execute("SELECT notify_assignment FROM users WHERE telegram_id = ?", (message.from_user.id,))
    row = cursor.fetchone()
    current = row[0] if row else 1
    new_value = 0 if current == 1 else 1
    cursor.execute("UPDATE users SET notify_assignment = ? WHERE telegram_id = ?", (new_value, message.from_user.id))
    conn.commit()
    status = "включены" if new_value == 1 else "отключены"
    await message.answer(f"Уведомления о назначении {status}.", reply_markup=user_menu())

@dp.message_handler(lambda message: message.text.startswith("Уведомление о предложении поменяться"))
async def toggle_exchange_notify(message: types.Message):
    cursor.execute("SELECT notify_exchange FROM users WHERE telegram_id = ?", (message.from_user.id,))
    row = cursor.fetchone()
    current = row[0] if row else 1
    new_value = 0 if current == 1 else 1
    cursor.execute("UPDATE users SET notify_exchange = ? WHERE telegram_id = ?", (new_value, message.from_user.id))
    conn.commit()
    status = "включены" if new_value == 1 else "отключены"
    await message.answer(f"Уведомления о предложении поменяться {status}.", reply_markup=user_menu())

@dp.message_handler(lambda message: message.text.startswith("Настроить напоминание"))
async def set_reminder_time(message: types.Message):
    # Здесь можно запросить время от пользователя.
    if "в день" in message.text:
        dp.current_state(user=message.from_user.id).update_data(reminder_type="day")
        await message.answer("Введите время в формате HH:MM для напоминания в день дежурства (дефолт 06:00):", reply_markup=back_kb)
    elif "за день" in message.text:
        dp.current_state(user=message.from_user.id).update_data(reminder_type="before")
        await message.answer("Введите время в формате HH:MM для напоминания за день до дежурства (дефолт 08:00):", reply_markup=back_kb)

@dp.message_handler(lambda message: dp.current_state(user=message.from_user.id).get_data().get('reminder_type'))
async def process_reminder_time(message: types.Message):
    data = await dp.current_state(user=message.from_user.id).get_data()
    rtype = data.get('reminder_type')
    # Простейшая валидация времени
    try:
        datetime.strptime(message.text, "%H:%M")
    except ValueError:
        await message.answer("Неверный формат времени. Используйте HH:MM.", reply_markup=back_kb)
        return
    if rtype == "day":
        cursor.execute("UPDATE users SET reminder_time_day = ? WHERE telegram_id = ?", (message.text, message.from_user.id))
    elif rtype == "before":
        cursor.execute("UPDATE users SET reminder_time_before = ? WHERE telegram_id = ?", (message.text, message.from_user.id))
    conn.commit()
    await message.answer("Время обновлено.", reply_markup=user_menu())
    await dp.current_state(user=message.from_user.id).update_data(reminder_type=None)

# --- Обработка уведомления о назначении дежурства для обычного пользователя --- #
# Предположим, когда старшина назначает дежурство, пользователю отправляется сообщение с inline-кнопками.
@dp.callback_query_handler(lambda c: c.data.startswith("assignment_notify:"))
async def process_assignment_notify(callback_query: types.CallbackQuery):
    # Формат callback_data: assignment_notify:<date>
    parts = callback_query.data.split(":")
    assignment_date = parts[1]
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("Принял", callback_data=f"accept_assignment:{assignment_date}"),
           InlineKeyboardButton("Предложить поменяться", callback_data=f"exchange_proposal:{assignment_date}"))
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id,
                           f"Вам назначено дежурство на {assignment_date}.\n"
                           "Выберите действие:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("accept_assignment:"))
async def process_accept_assignment(callback_query: types.CallbackQuery):
    assignment_date = callback_query.data.split(":")[1]
    # Здесь можно получить настройки напоминаний пользователя из БД
    cursor.execute("SELECT reminder_time_day, reminder_time_before FROM users WHERE telegram_id = ?",
                   (callback_query.from_user.id,))
    row = cursor.fetchone()
    if row:
        reminder_day, reminder_before = row
        text = f"Напоминания установлены:\nВ день дежурства: {reminder_day}\nЗа день до: {reminder_before}"
    else:
        text = "Напоминаний нет."
    await bot.answer_callback_query(callback_query.id, "Дежурство подтверждено.")
    await bot.send_message(callback_query.from_user.id, text)
    await notify_starshina(f"Пользователь ID {callback_query.from_user.id} принял дежурство на {assignment_date}.")

# Обработка предложения обмена
@dp.callback_query_handler(lambda c: c.data.startswith("exchange_proposal:"))
async def process_exchange_proposal_start(callback_query: types.CallbackQuery):
    assignment_date = callback_query.data.split(":")[1]
    # Сохраним дату и то, что это обмен, в состоянии пользователя
    await dp.current_state(user=callback_query.from_user.id).update_data(exchange_date=assignment_date)
    # Показываем список пользователей, доступных для обмена (те, у кого notify_exchange = 1 и не равен самому себе)
    users = get_users_for_exchange()
    kb = InlineKeyboardMarkup(row_width=1)
    for uid, name in users:
        if uid == callback_query.from_user.id:
            continue
        kb.add(InlineKeyboardButton(name, callback_data=f"choose_exchange:{uid}"))
    kb.add(InlineKeyboardButton("Отмена", callback_data="cancel_exchange"))
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id, "Выберите пользователя для обмена:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("choose_exchange:"))
async def process_exchange_choose(callback_query: types.CallbackQuery):
    to_user = int(callback_query.data.split(":")[1])
    # Сохраняем выбранного пользователя в состоянии
    await dp.current_state(user=callback_query.from_user.id).update_data(exchange_to=to_user)
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id, "Прикрепите текстовое сообщение для предложения обмена (можно оставить пустым):", reply_markup=back_kb)

@dp.message_handler(lambda message: dp.current_state(user=message.from_user.id).get_data().get('exchange_to') is not None)
async def process_exchange_message(message: types.Message):
    data = await dp.current_state(user=message.from_user.id).get_data()
    assignment_date = data.get('exchange_date')
    to_user = data.get('exchange_to')
    proposal_text = message.text if message.text != "Назад" else ""
    proposal_id = add_exchange_proposal(assignment_date, message.from_user.id, to_user, proposal_text)
    await message.answer("Ждём ответа...", reply_markup=user_menu())
    # Отправляем предложение выбранному пользователю
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("Принять", callback_data=f"accept_exchange:{proposal_id}"),
           InlineKeyboardButton("Отказать", callback_data=f"decline_exchange:{proposal_id}"))
    from_cursor = cursor.execute("SELECT name FROM users WHERE telegram_id = ?", (message.from_user.id,))
    from_name = from_cursor.fetchone()[0]
    text = f"Пользователь {from_name} предлагает поменяться дежурством на {assignment_date}."
    if proposal_text:
        text += f"\nСообщение: {proposal_text}"
    try:
        await bot.send_message(to_user, text, reply_markup=kb)
    except Exception as e:
        logging.error(f"Ошибка отправки предложения обмена: {e}")
    # Сброс состояния обмена
    await dp.current_state(user=message.from_user.id).update_data(exchange_date=None, exchange_to=None)

@dp.callback_query_handler(lambda c: c.data.startswith("cancel_exchange"))
async def process_cancel_exchange(callback_query: types.CallbackQuery):
    # Пользователь отменяет своё предложение обмена
    data = await dp.current_state(user=callback_query.from_user.id).get_data()
    assignment_date = data.get('exchange_date')
    await update_exchange_proposal_status(0, "canceled")
    await bot.answer_callback_query(callback_query.id, "Предложение отменено.")
    await bot.send_message(callback_query.from_user.id, f"Вы отменили предложение обмена для {assignment_date}.", reply_markup=user_menu())
    await dp.current_state(user=callback_query.from_user.id).update_data(exchange_date=None, exchange_to=None)

# Обработка принятия предложения обмена со стороны получателя
@dp.callback_query_handler(lambda c: c.data.startswith("accept_exchange:"))
async def process_accept_exchange(callback_query: types.CallbackQuery):
    proposal_id = int(callback_query.data.split(":")[1])
    # Обновляем статус предложения
    update_exchange_proposal_status(proposal_id, "accepted")
    # Получаем данные предложения
    cursor.execute("SELECT assignment_date, from_user, to_user FROM exchange_proposals WHERE id = ?", (proposal_id,))
    row = cursor.fetchone()
    if row:
        assignment_date, from_user, to_user = row
        # Обновляем запись в assignments: меняем дежурного
        delete_assignment(assignment_date, from_user)
        add_assignment(assignment_date, to_user)
        # Записываем в статистику
        add_changestat(from_user, to_user, assignment_date)
        await bot.answer_callback_query(callback_query.id, "Вы приняли обмен.")
        await bot.send_message(to_user, f"Обмен подтверждён. Вы теперь дежурите {assignment_date}.")
        await bot.send_message(from_user, f"Пользователь принял обмен. Вы не дежурите {assignment_date}.")
        await notify_starshina(f"Обмен дежурств: с {from_user} на {to_user} на дату {assignment_date}.")
    else:
        await bot.answer_callback_query(callback_query.id, "Ошибка обмена.")

# Обработка отказа от предложения обмена
@dp.callback_query_handler(lambda c: c.data.startswith("decline_exchange:"))
async def process_decline_exchange(callback_query: types.CallbackQuery):
    proposal_id = int(callback_query.data.split(":")[1])
    update_exchange_proposal_status(proposal_id, "declined")
    # Извлекаем from_user для уведомления
    cursor.execute("SELECT from_user, assignment_date FROM exchange_proposals WHERE id = ?", (proposal_id,))
    row = cursor.fetchone()
    if row:
        from_user, assignment_date = row
        await bot.send_message(from_user, f"Пользователь отказался от обмена для {assignment_date}.")
    await bot.answer_callback_query(callback_query.id, "Вы отказались от обмена.")

# --- Сервисные команды --- #
# /message — массовая рассылка (подтверждение перед отправкой)
@dp.message_handler(commands=['message'])
async def cmd_message(message: types.Message):
    # Для простоты допускаем, что эта команда доступна только пользователю с правами старшины
    cursor.execute("SELECT is_starshina FROM users WHERE telegram_id = ?", (message.from_user.id,))
    row = cursor.fetchone()
    if not row or row[0] != 1:
        await message.answer("Нет доступа.")
        return
    await message.answer("Введите сообщение для рассылки всем пользователям. Перед отправкой будет запрошено подтверждение.")
    dp.current_state(user=message.from_user.id).update_data(expect_broadcast=True)

@dp.message_handler(lambda message: dp.current_state(user=message.from_user.id).get_data().get('expect_broadcast'))
async def process_broadcast(message: types.Message):
    # Сохраняем сообщение и спрашиваем подтверждение
    dp.current_state(user=message.from_user.id).update_data(broadcast_text=message.text, expect_broadcast=False, confirm_broadcast=True)
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("Подтвердить", callback_data="confirm_broadcast"),
           InlineKeyboardButton("Отмена", callback_data="cancel_broadcast"))
    await message.answer(f"Отправить следующее сообщение всем пользователям?\n\n{message.text}", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data in ["confirm_broadcast", "cancel_broadcast"])
async def process_broadcast_confirm(callback_query: types.CallbackQuery):
    data = await dp.current_state(user=callback_query.from_user.id).get_data()
    if callback_query.data == "confirm_broadcast" and data.get("confirm_broadcast"):
        # Получаем список всех пользователей
        cursor.execute("SELECT telegram_id FROM users")
        users = cursor.fetchall()
        broadcast_text = data.get("broadcast_text")
        for u in users:
            try:
                await bot.send_message(u[0], broadcast_text)
            except Exception as e:
                logging.error(f"Ошибка при рассылке пользователю {u[0]}: {e}")
        await bot.answer_callback_query(callback_query.id, "Сообщение отправлено.")
    else:
        await bot.answer_callback_query(callback_query.id, "Рассылка отменена.")
    await dp.current_state(user=callback_query.from_user.id).update_data(confirm_broadcast=False, broadcast_text="")

# /changestat — вывод статистики обменов
@dp.message_handler(commands=['changestat'])
async def cmd_changestat(message: types.Message):
    cursor.execute("SELECT from_user, to_user, date, changed_at FROM changestat ORDER BY changed_at DESC")
    rows = cursor.fetchall()
    if not rows:
        await message.answer("Статистика пуста.")
        return
    text = "Статистика обменов:\n"
    for from_user, to_user, date, changed_at in rows:
        text += f"{changed_at}: {from_user} → {to_user} на {date}\n"
    await message.answer(text)

# /clearhistory — очистка истории дежурств до сегодняшнего дня (с подтверждением)
@dp.message_handler(commands=['clearhistory'])
async def cmd_clearhistory(message: types.Message):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("Подтвердить", callback_data="confirm_clearhistory"),
           InlineKeyboardButton("Отмена", callback_data="cancel_clearhistory"))
    await message.answer("Вы уверены, что хотите удалить историю дежурств до сегодняшнего дня?", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data in ["confirm_clearhistory", "cancel_clearhistory"])
async def process_clearhistory(callback_query: types.CallbackQuery):
    if callback_query.data == "confirm_clearhistory":
        today = datetime.now().strftime("%Y-%m-%d")
        clear_history(today)
        await bot.answer_callback_query(callback_query.id, "История очищена.")
    else:
        await bot.answer_callback_query(callback_query.id, "Действие отменено.")

# /testalarm — тестовое уведомление через 1 минуту
@dp.message_handler(commands=['testalarm'])
async def cmd_testalarm(message: types.Message):
    await message.answer("Тестовое уведомление будет отправлено через 1 минуту.")
    asyncio.create_task(send_test_alarm(message.from_user.id))

async def send_test_alarm(user_id: int):
    await asyncio.sleep(60)
    try:
        await bot.send_message(user_id, "Это тестовое уведомление.")
    except Exception as e:
        logging.error(f"Ошибка отправки тестового уведомления: {e}")

# /info — вывод информации о боте
@dp.message_handler(commands=['info'])
async def cmd_info(message: types.Message):
    # Текст можно менять, он сохраняется между запусками (в данном примере просто выводим статичный текст)
    info_text = "Версия бота: 1.0. Разработано для упрощения составления графика дежурств."
    await message.answer(info_text)

# --- Запуск бота --- #
if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
