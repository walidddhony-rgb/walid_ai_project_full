"""Safe filesystem helpers for workspace operations."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Union

from walid_ai.config import MAX_FILE_BYTES, TEXT_EXTENSIONS

PathLike = Union[str, Path]


def safe_path(root: PathLike, rel: str) -> Path:
    root_path = Path(root).resolve()
    target = (root_path / rel).resolve()

    if target != root_path and root_path not in target.parents:
        raise ValueError(f"Path outside workspace: {rel}")

    return target


def files(root: PathLike) -> list[Path]:
    root_path = Path(root)
    if not root_path.exists() or not root_path.is_dir():
        return []

    result: list[Path] = []
    for path in root_path.rglob("*"):
        try:
            if (
                path.is_file()
                and path.suffix.lower() in TEXT_EXTENSIONS
                and path.stat().st_size <= MAX_FILE_BYTES
            ):
                result.append(path)
        except OSError:
            continue

    return sorted(result)


def read(path: PathLike, limit: int | None = None) -> str:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    return text if limit is None else text[:limit]


def create_file(root: PathLike, rel: str, text: str) -> Path:
    path = safe_path(root, rel)
    if path.exists():
        raise FileExistsError(f"File already exists: {rel}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def create_dir(root: PathLike, rel: str) -> Path:
    path = safe_path(root, rel)
    path.mkdir(parents=True, exist_ok=True)
    return path


def md5(path: PathLike) -> str:
    return hashlib.md5(Path(path).read_bytes()).hexdigest()
