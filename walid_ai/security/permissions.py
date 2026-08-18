from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path


class PermissionManager:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_schema()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self):
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS permissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    permission TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT 'once',
                    granted_at TEXT NOT NULL,
                    expires_at TEXT,
                    revoked INTEGER DEFAULT 0
                )
                """
            )

    def grant(self, permission: str, scope: str, mode: str = "once", hours: int = 1):
        now = datetime.now()
        expires = now + timedelta(hours=hours) if mode == "session" else None
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO permissions
                    (permission, scope, mode, granted_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    permission,
                    scope,
                    mode,
                    now.isoformat(),
                    expires.isoformat() if expires else None,
                ),
            )

    def allowed(self, permission: str, scope: str) -> bool:
        now = datetime.now().isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM permissions
                WHERE permission = ? AND revoked = 0
                ORDER BY id DESC
                """,
                (permission,),
            ).fetchall()
        for row in rows:
            if row["scope"] != "*" and not scope.startswith(row["scope"]):
                continue
            if row["expires_at"] and row["expires_at"] < now:
                continue
            return True
        return False

    def revoke_all(self, permission: str | None = None):
        with self._connect() as conn:
            if permission:
                conn.execute(
                    "UPDATE permissions SET revoked=1 WHERE permission=?",
                    (permission,),
                )
            else:
                conn.execute("UPDATE permissions SET revoked=1")