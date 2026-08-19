"""SQLite database manager with local FTS5 knowledge search."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class DatabaseManager:
    """Manages chat history, file index, logs, simple memory, and knowledge."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        statements = [
            (
                "CREATE TABLE IF NOT EXISTS conversations ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "role TEXT NOT NULL, "
                "content TEXT NOT NULL, "
                "created DATETIME DEFAULT CURRENT_TIMESTAMP)"
            ),
            (
                "CREATE TABLE IF NOT EXISTS files ("
                "path TEXT PRIMARY KEY, "
                "absolute TEXT NOT NULL, "
                "size INTEGER NOT NULL, "
                "hash TEXT NOT NULL, "
                "preview TEXT, "
                "updated DATETIME DEFAULT CURRENT_TIMESTAMP)"
            ),
            (
                "CREATE TABLE IF NOT EXISTS operations ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "operation TEXT NOT NULL, "
                "target TEXT, "
                "details TEXT, "
                "status TEXT DEFAULT 'success', "
                "created DATETIME DEFAULT CURRENT_TIMESTAMP)"
            ),
            (
                "CREATE TABLE IF NOT EXISTS memory ("
                "key TEXT PRIMARY KEY, "
                "value TEXT NOT NULL, "
                "category TEXT DEFAULT 'general', "
                "updated DATETIME DEFAULT CURRENT_TIMESTAMP)"
            ),
            (
                "CREATE TABLE IF NOT EXISTS knowledge ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "title TEXT NOT NULL, "
                "content TEXT NOT NULL, "
                "category TEXT NOT NULL DEFAULT 'general', "
                "source_url TEXT NOT NULL DEFAULT '', "
                "source_type TEXT NOT NULL DEFAULT 'conversation', "
                "fingerprint TEXT NOT NULL DEFAULT '', "
                "created DATETIME DEFAULT CURRENT_TIMESTAMP, "
                "updated DATETIME DEFAULT CURRENT_TIMESTAMP)"
            ),
            (
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "idx_knowledge_fingerprint "
                "ON knowledge(fingerprint) "
                "WHERE fingerprint <> ''"
            ),
            (
                "CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts "
                "USING fts5("
                "title, "
                "content, "
                "category, "
                "source_url, "
                "source_type, "
                "content='knowledge', "
                "content_rowid='id', "
                "tokenize='unicode61 remove_diacritics 2'"
                ")"
            ),
            (
                "CREATE TRIGGER IF NOT EXISTS knowledge_ai "
                "AFTER INSERT ON knowledge BEGIN "
                "INSERT INTO knowledge_fts("
                "rowid, title, content, category, source_url, source_type"
                ") VALUES ("
                "new.id, new.title, new.content, new.category, "
                "new.source_url, new.source_type"
                "); END"
            ),
            (
                "CREATE TRIGGER IF NOT EXISTS knowledge_ad "
                "AFTER DELETE ON knowledge BEGIN "
                "INSERT INTO knowledge_fts("
                "knowledge_fts, rowid, title, content, category, "
                "source_url, source_type"
                ") VALUES ("
                "'delete', old.id, old.title, old.content, old.category, "
                "old.source_url, old.source_type"
                "); END"
            ),
            (
                "CREATE TRIGGER IF NOT EXISTS knowledge_au "
                "AFTER UPDATE ON knowledge BEGIN "
                "INSERT INTO knowledge_fts("
                "knowledge_fts, rowid, title, content, category, "
                "source_url, source_type"
                ") VALUES ("
                "'delete', old.id, old.title, old.content, old.category, "
                "old.source_url, old.source_type"
                "); "
                "INSERT INTO knowledge_fts("
                "rowid, title, content, category, source_url, source_type"
                ") VALUES ("
                "new.id, new.title, new.content, new.category, "
                "new.source_url, new.source_type"
                "); END"
            ),
        ]

        with self._connect() as conn:
            for statement in statements:
                conn.execute(statement)

            knowledge_count = conn.execute(
                "SELECT COUNT(*) FROM knowledge"
            ).fetchone()[0]

            fts_count = conn.execute(
                "SELECT COUNT(*) FROM knowledge_fts"
            ).fetchone()[0]

            if knowledge_count != fts_count:
                conn.execute(
                    "INSERT INTO knowledge_fts(knowledge_fts) "
                    "VALUES('rebuild')"
                )

    def add_message(self, role: str, content: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO conversations(role, content) VALUES (?, ?)",
                (role, content),
            )

    def history(self, limit: int = 50) -> list[dict[str, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT role, content "
                "FROM conversations "
                "ORDER BY id DESC "
                "LIMIT ?",
                (max(1, limit),),
            ).fetchall()

        return [dict(row) for row in reversed(rows)]

    def clear_history(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM conversations")

    def log(
        self,
        operation: str,
        target: str = "",
        details: str = "",
        status: str = "success",
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO operations("
                "operation, target, details, status"
                ") VALUES (?, ?, ?, ?)",
                (operation, target, details, status),
            )

    def log_operation(
        self,
        operation: str,
        target: str = "",
        details: str = "",
    ) -> None:
        self.log(operation, target, details)

    def upsert(
        self,
        data: tuple[str, str, int, str, str],
    ) -> None:
        sql = (
            "INSERT INTO files("
            "path, absolute, size, hash, preview, updated"
            ") VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(path) DO UPDATE SET "
            "absolute=excluded.absolute, "
            "size=excluded.size, "
            "hash=excluded.hash, "
            "preview=excluded.preview, "
            "updated=CURRENT_TIMESTAMP"
        )

        with self._connect() as conn:
            conn.execute(sql, data)

    def get_file(self, rel_path: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM files WHERE path = ?",
                (rel_path,),
            ).fetchone()

        return dict(row) if row else None

    def set_memory(
        self,
        key: str,
        value: str,
        category: str = "general",
    ) -> None:
        sql = (
            "INSERT INTO memory(key, value, category, updated) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(key) DO UPDATE SET "
            "value=excluded.value, "
            "category=excluded.category, "
            "updated=CURRENT_TIMESTAMP"
        )

        with self._connect() as conn:
            conn.execute(sql, (key, value, category))

    def get_all_memory(self) -> list[dict[str, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT key, value, category "
                "FROM memory "
                "ORDER BY key"
            ).fetchall()

        return [dict(row) for row in rows]

    def save_knowledge(
        self,
        title: str,
        content: str,
        category: str = "general",
        source_url: str = "",
        source_type: str = "conversation",
        fingerprint: str = "",
    ) -> int:
        title = title.strip()[:500]
        content = content.strip()

        if not title or not content:
            raise ValueError("العنوان والمحتوى مطلوبان لحفظ المعرفة")

        with self._connect() as conn:
            if fingerprint:
                row = conn.execute(
                    "SELECT id FROM knowledge WHERE fingerprint = ?",
                    (fingerprint,),
                ).fetchone()

                if row:
                    conn.execute(
                        "UPDATE knowledge SET "
                        "title = ?, "
                        "content = ?, "
                        "category = ?, "
                        "source_url = ?, "
                        "source_type = ?, "
                        "updated = CURRENT_TIMESTAMP "
                        "WHERE id = ?",
                        (
                            title,
                            content,
                            category,
                            source_url,
                            source_type,
                            row["id"],
                        ),
                    )
                    return int(row["id"])

            cursor = conn.execute(
                "INSERT INTO knowledge("
                "title, content, category, source_url, source_type, fingerprint"
                ") VALUES (?, ?, ?, ?, ?, ?)",
                (
                    title,
                    content,
                    category,
                    source_url,
                    source_type,
                    fingerprint,
                ),
            )

            return int(cursor.lastrowid)

    def search_knowledge(
        self,
        query: str,
        limit: int = 6,
    ) -> list[dict[str, Any]]:
        words = [
            word
            for word in query.replace('"', " ").split()
            if len(word) > 1
        ]

        if not words:
            return []

        match_query = " OR ".join(
            f'"{word}"'
            for word in words[:12]
        )

        sql = (
            "SELECT "
            "k.id, "
            "k.title, "
            "k.content, "
            "k.category, "
            "k.source_url, "
            "k.source_type, "
            "k.created, "
            "bm25(knowledge_fts) AS score "
            "FROM knowledge_fts "
            "JOIN knowledge AS k "
            "ON k.id = knowledge_fts.rowid "
            "WHERE knowledge_fts MATCH ? "
            "ORDER BY score "
            "LIMIT ?"
        )

        with self._connect() as conn:
            rows = conn.execute(
                sql,
                (
                    match_query,
                    max(1, min(limit, 20)),
                ),
            ).fetchall()

        return [dict(row) for row in rows]
