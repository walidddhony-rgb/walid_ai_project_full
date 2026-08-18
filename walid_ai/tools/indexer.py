"""Project file indexer."""
from __future__ import annotations

from pathlib import Path

from walid_ai.tools.filesystem import files, md5, read


class FileIndexer:
    def __init__(self, db):
        self.db = db

    def index(self, root: Path) -> int:
        root = Path(root)
        count = 0

        for path in files(root):
            try:
                stat = path.stat()
                self.db.upsert(
                    (
                        str(path.relative_to(root)),
                        str(path),
                        stat.st_size,
                        md5(path),
                        read(path, limit=2000),
                    )
                )
                count += 1
            except Exception as exc:
                self.db.log("index_error", str(path), str(exc), status="failed")

        self.db.log("index", str(root), f"files={count}")
        return count
