import sqlite3
from datetime import datetime

class BaseCRUD:
    def __init__(self):
        self.conn = sqlite3.connect("bot.db")
        self.cursor = self.conn.cursor()

class UserCRUD(BaseCRUD):
    def create(self, telegram_id: int, name: str, is_starshina: bool = False):
        self.cursor.execute("""
            INSERT OR REPLACE INTO users 
            (telegram_id, name, is_starshina) 
            VALUES (?, ?, ?)
        """, (telegram_id, name, int(is_starshina)))
        self.conn.commit()

    def get(self, telegram_id: int) -> dict:
        self.cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        row = self.cursor.fetchone()
        return {
            "telegram_id": row[0],
            "name": row[1],
            "is_starshina": bool(row[2])
        } if row else None

# Остальные классы (AssignmentCRUD, SwapCRUD) реализуются аналогично