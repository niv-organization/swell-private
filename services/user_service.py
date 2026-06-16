import bcrypt
import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)


class UserService:
    def __init__(self, db_connection):
        self.db = db_connection

    def authenticate(self, username: str, password: str) -> Optional[Dict]:
        query = "SELECT * FROM users WHERE username = %s"
        cursor = self.db.cursor()
        try:
            cursor.execute(query, (username,))
            user = cursor.fetchone()

            if user and bcrypt.checkpw(password.encode(), user[2].encode()):
                return {"user_id": user[0], "username": user[1], "role": user[3]}
            return None
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            return None
        finally:
            cursor.close()

    def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        query = "SELECT * FROM users WHERE id = %s"
        cursor = self.db.cursor()
        try:
            cursor.execute(query, (user_id,))
            user = cursor.fetchone()

            if user:
                return {"user_id": user[0], "username": user[1], "role": user[3]}
            return None
        except Exception as e:
            logger.error(f"Failed to fetch user {user_id}: {e}")
            return None
        finally:
            cursor.close()

    def update_email(self, user_id: int, new_email: str) -> bool:
        query = "UPDATE users SET email = %s WHERE id = %s"
        cursor = self.db.cursor()
        try:
            cursor.execute(query, (new_email, user_id))
            self.db.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to update email for user {user_id}: {e}")
            self.db.rollback()
            return False
        finally:
            cursor.close()
