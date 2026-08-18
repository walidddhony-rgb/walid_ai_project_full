from __future__ import annotations

import ast
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from walid_ai.config import CODE_EXTENSIONS, MAX_FILE_BYTES
from walid_ai.tools.filesystem import files, read, safe_path


class DeveloperAgent:
    """Tools for safe project review, patch preparation, and backups."""

    def __init__(self, db):
        self.db = db

    def project_snapshot(self, root: Path) -> dict[str, Any]:
        result = {
            "root": str(root),
            "files": [],
            "languages": {},
            "total_lines": 0,
            "python_functions": 0,
            "python_classes": 0,
            "errors": [],
        }
        for path in files(root):
            if path.suffix.lower() not in CODE_EXTENSIONS:
                continue
            try:
                text = read(path)
                item = {
                    "path": str(path.relative_to(root)),
                    "extension": path.suffix.lower(),
                    "lines": len(text.splitlines()),
                    "size": path.stat().st_size,
                }
                result["files"].append(item)
                ext = path.suffix.lower() or "unknown"
                result["languages"][ext] = result["languages"].get(ext, 0) + 1
                result["total_lines"] += item["lines"]
                if path.suffix.lower() == ".py":
                    try:
                        tree = ast.parse(text)
                        result["python_functions"] += sum(
                            isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                            for n in ast.walk(tree)
                        )
                        result["python_classes"] += sum(
                            isinstance(n, ast.ClassDef) for n in ast.walk(tree)
                        )
                    except SyntaxError as exc:
                        result["errors"].append(
                            {"path": item["path"], "error": f"SyntaxError: {exc.msg}"}
                        )
            except Exception as exc:
                result["errors"].append({"path": str(path), "error": str(exc)})
        return result

    def read_project_context(self, root: Path, requested_paths: list[str] | None = None) -> list[dict[str, str]]:
        context = []
        selected = requested_paths or [str(p.relative_to(root)) for p in files(root)[:30]]
        for relative in selected:
            try:
                path = safe_path(root, relative)
                if path.is_file() and path.stat().st_size <= MAX_FILE_BYTES:
                    context.append({
                        "path": relative,
                        "content": read(path)[:16000],
                    })
            except Exception:
                continue
        return context

    def prepare_patch(self, root: Path, relative_path: str, new_content: str) -> dict[str, Any]:
        path = safe_path(root, relative_path)
        old_content = read(path) if path.exists() else ""
        return {
            "path": relative_path,
            "exists": path.exists(),
            "old_content": old_content,
            "new_content": new_content,
            "changed": old_content != new_content,
        }

    def apply_patch(self, root: Path, relative_path: str, new_content: str) -> Path:
        path = safe_path(root, relative_path)
        backup_dir = root / ".walid_ai_backups" / datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir.mkdir(parents=True, exist_ok=True)
        if path.exists():
            backup_path = backup_dir / path.name
            shutil.copy2(path, backup_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new_content, encoding="utf-8")
        self.db.log("apply_patch", str(path), f"backup={backup_dir}")
        return path

    def format_snapshot(self, snapshot: dict[str, Any]) -> str:
        lines = [
            f"المشروع: {snapshot['root']}",
            f"عدد الملفات البرمجية: {len(snapshot['files'])}",
            f"إجمالي الأسطر: {snapshot['total_lines']}",
            f"دوال Python: {snapshot['python_functions']}",
            f"أصناف Python: {snapshot['python_classes']}",
            f"الامتدادات: {snapshot['languages']}",
        ]
        if snapshot["errors"]:
            lines.append("أخطاء الصياغة:")
            lines.extend(f"- {e['path']}: {e['error']}" for e in snapshot["errors"])
        lines.append("الملفات:")
        lines.extend(f"- {f['path']} ({f['lines']} سطر)" for f in snapshot["files"][:50])
        return "\n".join(lines)