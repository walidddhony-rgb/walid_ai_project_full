"""Safe file patch application with backups and permission checks."""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from walid_ai.security.permissions import PermissionManager


class PatchService:
    """Applies full-file replacements safely inside the active workspace."""

    def __init__(
        self,
        permission_manager: PermissionManager,
        db=None,
        root: Path | None = None,
    ):
        self.permissions = permission_manager
        self.db = db
        self.root = Path(root).resolve() if root else None

    def set_root(self, root: str | Path | None) -> None:
        self.root = Path(root).resolve() if root else None

    def _safe_path(self, relative_path: str) -> Path:
        if not self.root:
            raise RuntimeError("لم يتم اختيار مساحة عمل")

        path = (self.root / relative_path).resolve()

        if path != self.root and self.root not in path.parents:
            raise ValueError("المسار خارج مساحة العمل")

        return path

    def apply_patch(
        self,
        relative_path: str,
        new_content: str,
    ) -> dict[str, Any]:
        if not self.root:
            raise RuntimeError("لم يتم اختيار مساحة عمل")

        if not self.permissions.allowed(
            "modify_files",
            str(self.root),
        ):
            raise PermissionError("لم تمنح صلاحية تعديل الملفات")

        path = self._safe_path(relative_path)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = self.root / ".walid_ai_backups" / timestamp
        backup_dir.mkdir(parents=True, exist_ok=True)

        backup: Path | None = None

        if path.exists():
            backup = backup_dir / path.name
            shutil.copy2(path, backup)

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new_content, encoding="utf-8")

        details = f"backup={backup_dir}"

        if self.db and hasattr(self.db, "log_operation"):
            self.db.log_operation("apply_patch", str(path), details)
        elif self.db and hasattr(self.db, "log"):
            self.db.log("apply_patch", str(path), details)

        return {
            "path": str(path),
            "backup": str(backup) if backup else None,
        }