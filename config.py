import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")  # Токен бота из .env
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "starshina")  # Пароль старшины
DB_NAME = "bot.db"  # Название файла базы данных
TIMEZONE = "Europe/Moscow"  # Часовой пояс для планировщика