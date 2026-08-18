"""Static code analysis helpers."""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from walid_ai.tools.filesystem import files, read

SUPPORTED_EXTENSIONS = {".py", ".js", ".ts", ".java", ".cpp"}


class CodeAnalyzer:
    @staticmethod
    def analyze(path: str | Path) -> dict[str, Any]:
        path = Path(path)
        result: dict[str, Any] = {
            "file": path.name,
            "path": str(path),
            "language": path.suffix.lower(),
            "lines": 0,
            "imports": [],
            "functions": [],
            "classes": [],
        }

        try:
            text = read(path)
        except Exception as exc:
            result["error"] = f"read_error: {exc}"
            return result

        result["lines"] = len(text.splitlines())

        if path.suffix.lower() == ".py":
            try:
                tree = ast.parse(text)
                result["imports"] = [
                    alias.name
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Import)
                    for alias in node.names
                ]
                result["functions"] = [
                    node.name
                    for node in ast.walk(tree)
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                ]
                result["classes"] = [
                    node.name
                    for node in ast.walk(tree)
                    if isinstance(node, ast.ClassDef)
                ]
            except SyntaxError as exc:
                result["error"] = f"syntax_error at line {exc.lineno}: {exc.msg}"

        return result

    @staticmethod
    def project(root: str | Path) -> list[dict[str, Any]]:
        return [
            CodeAnalyzer.analyze(path)
            for path in files(root)
            if path.suffix.lower() in SUPPORTED_EXTENSIONS
        ]
