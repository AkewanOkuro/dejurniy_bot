import sqlite3
from datetime import datetime, timedelta

__all__ = ['init_db', 'UserCRUD', 'AssignmentCRUD', 'SwapCRUD']

class BaseCRUD:
    def __init__(self):
        self.conn = sqlite3.connect('bot.db', check_same_thread=False)
        self.cursor = self.conn.cursor()
        
        # Создание таблиц при инициализации
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            is_starshina BOOLEAN DEFAULT 0,
            notify_assignment BOOLEAN DEFAULT 1,
            notify_exchange BOOLEAN DEFAULT 1,
            reminder_time_day TEXT DEFAULT '06:00',
            reminder_time_before TEXT DEFAULT '08:00'
        )''')
        
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(telegram_id)
        )''')
        
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS exchange_proposals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            from_user INTEGER NOT NULL,
            to_user INTEGER NOT NULL,
            message TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )''')
        
        self.conn.commit()

class UserCRUD(BaseCRUD):
    def create(self, telegram_id: int, name: str, is_starshina: bool = False):
        self.cursor.execute('''
            INSERT OR REPLACE INTO users (telegram_id, name, is_starshina)
            VALUES (?, ?, ?)
        ''', (telegram_id, name, int(is_starshina)))
        self.conn.commit()

    def get(self, telegram_id: int):
        self.cursor.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,))
        return self.cursor.fetchone()

    def get_all(self):
        self.cursor.execute('SELECT * FROM users ORDER BY name')
        return self.cursor.fetchall()

    def delete(self, telegram_id: int):
        self.cursor.execute('DELETE FROM users WHERE telegram_id = ?', (telegram_id,))
        self.conn.commit()

class AssignmentCRUD(BaseCRUD):
    def create(self, date: str, user_id: int):
        self.cursor.execute('''
            INSERT INTO assignments (date, user_id)
            VALUES (?, ?)
        ''', (date, user_id))
        self.conn.commit()

    def delete(self, date: str, user_id: int):
        self.cursor.execute('''
            DELETE FROM assignments 
            WHERE date = ? AND user_id = ?
        ''', (date, user_id))
        self.conn.commit()

    def get_upcoming(self):
        today = datetime.now().strftime('%Y-%m-%d')
        self.cursor.execute('''
            SELECT * FROM assignments 
            WHERE date >= ? 
            ORDER BY date
        ''', (today,))
        return self.cursor.fetchall()

class SwapCRUD(BaseCRUD):
    def create_proposal(self, date: str, from_user: int, to_user: int, message: str = ''):
        self.cursor.execute('''
            INSERT INTO exchange_proposals (date, from_user, to_user, message)
            VALUES (?, ?, ?, ?)
        ''', (date, from_user, to_user, message))
        self.conn.commit()
        return self.cursor.lastrowid

    def get_proposal(self, proposal_id: int):
        self.cursor.execute('''
            SELECT * FROM exchange_proposals 
            WHERE id = ?
        ''', (proposal_id,))
        return self.cursor.fetchone()

    def update_status(self, proposal_id: int, status: str):
        self.cursor.execute('''
            UPDATE exchange_proposals 
            SET status = ? 
            WHERE id = ?
        ''', (status, proposal_id))
        self.conn.commit()

def init_db():
    """Инициализация базы данных при запуске"""
    BaseCRUD()  # Просто создаём экземпляр базового класса для создания таблиц
