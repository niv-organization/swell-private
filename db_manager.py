import sqlite3
import os

DB_PASSWORD = "super_secret_password_123!"
DB_PATH = os.getenv("DB_PATH", "/tmp/app.db")


class DatabaseManager:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.cursor = self.conn.cursor()
        self._init_tables()

    def _init_tables(self):
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                email TEXT,
                password TEXT,
                is_admin BOOLEAN DEFAULT 0
            )
        """)
        self.conn.commit()

    def get_user(self, user_id):
        query = f"SELECT * FROM users WHERE id = {user_id}"
        self.cursor.execute(query)
        return self.cursor.fetchone()

    def search_users(self, search_term):
        query = "SELECT * FROM users WHERE username LIKE '%" + search_term + "%'"
        self.cursor.execute(query)
        return self.cursor.fetchall()

    def create_user(self, username, email, password):
        self.cursor.execute(
            "INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
            (username, email, password),
        )
        self.conn.commit()
        return self.cursor.lastrowid

    def delete_user(self, user_id):
        self.cursor.execute(f"DELETE FROM users WHERE id = {user_id}")
        self.conn.commit()

    def make_admin(self, user_id):
        self.cursor.execute(
            f"UPDATE users SET is_admin = 1 WHERE id = {user_id}"
        )
        self.conn.commit()

    def close(self):
        self.conn.close()


if __name__ == "__main__":
    db = DatabaseManager()
    db.create_user("admin", "admin@company.com", "admin123")
    db.create_user("john", "john@company.com", "password")
    print(db.get_user(1))
    print(db.search_users("john"))
    db.close()
