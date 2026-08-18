"""SQLite database layer for Walid AI."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class DatabaseManager:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS files (
                    path TEXT PRIMARY KEY,
                    absolute TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    hash TEXT NOT NULL,
                    preview TEXT,
                    updated DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS operations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    operation TEXT NOT NULL,
                    target TEXT,
                    details TEXT,
                    status TEXT DEFAULT 'success',
                    created DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS memory (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    category TEXT DEFAULT 'general'
                );
                """
            )

    def add_message(self, role: str, content: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO conversations(role, content) VALUES(?, ?)",
                (role, content),
            )

    def history(self, limit: int = 12) -> list[dict[str, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT role, content FROM conversations ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()

        return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]

    def clear_history(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM conversations")

    def log(self, op: str, target: str = "", details: str = "", status: str = "success") -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO operations(operation, target, details, status)
                VALUES(?, ?, ?, ?)
                """,
                (op, target, details, status),
            )

    def upsert(self, data: tuple[str, str, int, str, str]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO files(path, absolute, size, hash, preview, updated)
                VALUES(?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(path) DO UPDATE SET
                    absolute=excluded.absolute,
                    size=excluded.size,
                    hash=excluded.hash,
                    preview=excluded.preview,
                    updated=CURRENT_TIMESTAMP
                """,
                data,
            )

    def get_file(self, rel_path: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM files WHERE path = ?",
                (rel_path,),
            ).fetchone()

        return dict(row) if row else None

    def set_memory(self, key: str, value: str, category: str = "general") -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO memory(key, value, category)
                VALUES(?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value=excluded.value,
                    category=excluded.category
                """,
                (key, value, category),
            )

    def get_all_memory(self) -> list[dict[str, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT key, value, category FROM memory ORDER BY key"
            ).fetchall()

        return [dict(row) for row in rows]
