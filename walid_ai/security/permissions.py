"""Permission persistence and workspace scope validation."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path


class PermissionManager:
    """Stores user grants and validates permission scope."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_schema(self) -> None:
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
                    revoked INTEGER NOT NULL DEFAULT 0
                )
                """
            )

    def grant(
        self,
        permission: str,
        scope: str = "*",
        mode: str = "once",
        hours: int = 1,
    ) -> None:
        if mode not in {"once", "session", "persistent"}:
            raise ValueError(f"Unsupported permission mode: {mode}")

        now = datetime.now()
        expires_at = None

        if mode == "once":
            expires_at = now + timedelta(minutes=10)
        elif mode == "session":
            expires_at = now + timedelta(hours=hours)

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
                    expires_at.isoformat() if expires_at else None,
                ),
            )

    def allowed(self, permission: str, scope: str = "*") -> bool:
        now = datetime.now().isoformat()

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT scope, expires_at
                FROM permissions
                WHERE permission = ?
                  AND revoked = 0
                ORDER BY id DESC
                """,
                (permission,),
            ).fetchall()

        for saved_scope, expires_at in rows:
            if expires_at and expires_at < now:
                continue

            if saved_scope == "*":
                return True

            if scope.startswith(saved_scope):
                return True

        return False

    def revoke(self, permission: str, scope: str = "*") -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE permissions
                SET revoked = 1
                WHERE permission = ?
                  AND scope = ?
                  AND revoked = 0
                """,
                (permission, scope),
            )

    def revoke_all(self) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE permissions SET revoked = 1")
