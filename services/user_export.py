import csv
import io
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class UserRecord:
    user_id: str
    email: str
    name: str
    created_at: datetime
    last_login: Optional[datetime] = None
    is_active: bool = True


class UserExportService:
    """Service for exporting user data to CSV format."""

    EXPORT_FIELDS = ["user_id", "email", "name", "created_at", "is_active"]

    def __init__(self, db_connection):
        self.db = db_connection
        self._export_count = 0

    def export_users_to_csv(self, filters: Dict = None) -> str:
        users = self._fetch_users(filters)

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=self.EXPORT_FIELDS)
        writer.writeheader()

        for user in users:
            row = {
                "user_id": user.user_id,
                "email": user.email,
                "name": user.name,
                "created_at": user.created_at.isoformat(),
                "is_active": user.is_active,
            }
            writer.writerow(row)

        self._export_count += 1
        logger.info(f"Exported {len(users)} users (export #{self._export_count})")

        return output.getvalue()

    def _fetch_users(self, filters: Dict = None) -> List[UserRecord]:
        query = "SELECT user_id, email, name, created_at, last_login, is_active FROM users"
        params = []

        if filters:
            conditions = []
            if "is_active" in filters:
                conditions.append("is_active = %s")
                params.append(filters["is_active"])
            if "created_after" in filters:
                conditions.append("created_at > %s")
                params.append(filters["created_after"])

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

        cursor = self.db.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()

        return [
            UserRecord(
                user_id=row[0],
                email=row[1],
                name=row[2],
                created_at=row[3],
                last_login=row[4],
                is_active=row[5],
            )
            for row in rows
        ]

    def get_export_count(self) -> int:
        return self._export_count
