from __future__ import annotations

import ast
import json
import shutil
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:
    requests = None


class AgentState(str, Enum):
    IDLE = "idle"
    PLANNING = "planning"
    WAITING_APPROVAL = "waiting_approval"
    RESEARCHING = "researching"
    REVIEWING = "reviewing"
    APPLYING = "applying"
    TESTING = "testing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentPlan:
    goal: str
    source_mode: str
    steps: list[str]
    permissions: list[str]
    risks: list[str]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def as_text(self) -> str:
        lines = [
            "## خطة التنفيذ المقترحة",
            "",
            f"**الهدف:** {self.goal}",
            f"**مصدر المعرفة:** {self.source_mode}",
            "",
            "**الخطوات:**",
        ]
        lines.extend(f"{i}. {step}" for i, step in enumerate(self.steps, 1))
        lines.extend(["", "**الصلاحيات المطلوبة:**"])
        lines.extend(f"- {permission}" for permission in self.permissions)
        lines.extend(["", "**المخاطر والضوابط:**"])
        lines.extend(f"- {risk}" for risk in self.risks)
        lines.extend(["", "اكتب: **أوافق على الخطة** للمتابعة."])
        return "\n".join(lines)


class PermissionManager:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
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

    def grant(self, permission: str, scope: str, mode: str = "once", hours: int = 1) -> None:
        now = datetime.now()
        expiry = now + timedelta(hours=hours) if mode == "session" else None
        with sqlite3.connect(self.db_path) as conn:
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
                    expiry.isoformat() if expiry else None,
                ),
            )

    def allowed(self, permission: str, scope: str) -> bool:
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT permission, scope, expires_at
                FROM permissions
                WHERE permission = ? AND revoked = 0
                ORDER BY id DESC
                """,
                (permission,),
            ).fetchall()
        for saved_permission, saved_scope, expiry in rows:
            if saved_scope != "*" and not scope.startswith(saved_scope):
                continue
            if expiry and expiry < now:
                continue
            return True
        return False

    def revoke_all(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE permissions SET revoked = 1")


class AgentController:
    """Central coordinator for planning, permissions, research, validation, and patches."""

    def __init__(self, db=None, root: Path | None = None, db_path: Path | None = None):
        self.db = db
        self.root = Path(root).resolve() if root else None
        self.state = AgentState.IDLE
        self.pending_plan: AgentPlan | None = None
        if db_path is None and db is not None:
            db_path = getattr(db, "db_path", None) or getattr(db, "path", None)
        if db_path is None:
            db_path = Path.home() / ".walid_ai" / "walid_ai.db"
        self.permissions = PermissionManager(Path(db_path))

    def set_root(self, root: Path | str | None) -> None:
        self.root = Path(root).resolve() if root else None

    def plan(self, goal: str, source_mode: str = "local") -> AgentPlan:
        self.state = AgentState.PLANNING
        permissions: list[str] = []
        if self.root:
            permissions.append("read_local")
        if source_mode in {"web", "both"}:
            permissions.append("search_web")
        if source_mode in {"academic", "both"}:
            permissions.append("search_academic")
        development_words = (
            "أضف", "إضافة", "عدّل", "عدل", "حسّن", "حسن", "طوّر", "طور",
            "أنشئ", "اكتب", "تعديل", "تطوير",
        )
        if any(word in goal for word in development_words):
            permissions.extend(["modify_files", "execute_tests"])
        steps = [
            "تحليل الهدف وتحديد الملفات المرتبطة",
            "جمع السياق المسموح به فقط",
        ]
        if source_mode in {"web", "both"}:
            steps.append("البحث في مصادر الويب")
        if source_mode in {"academic", "both"}:
            steps.append("البحث في المصادر الأكاديمية")
        steps.extend([
            "إعداد حل أو patch قابل للمراجعة",
            "فحص الصياغة والاختبارات المتاحة",
            "عرض النتيجة وطلب موافقة التطبيق",
        ])
        self.pending_plan = AgentPlan(
            goal=goal,
            source_mode=source_mode,
            steps=steps,
            permissions=permissions,
            risks=[
                "قد يحتاج التعديل إلى مراجعة المستخدم",
                "لن يتم حذف الملفات نهائياً",
                "سيتم إنشاء نسخة احتياطية قبل التعديل",
            ],
        )
        self.state = AgentState.WAITING_APPROVAL
        return self.pending_plan

    def grant(self, permission: str, scope: str = "*", mode: str = "once") -> bool:
        self.permissions.grant(permission, scope, mode)
        return self.permissions.allowed(permission, scope)

    def can_read(self) -> bool:
        return bool(
            self.root
            and self.permissions.allowed("read_local", str(self.root))
        )

    def _safe_path(self, relative_path: str) -> Path:
        if not self.root:
            raise RuntimeError("لم يتم اختيار مساحة عمل")
        path = (self.root / relative_path).resolve()
        if path != self.root and self.root not in path.parents:
            raise ValueError("المسار خارج مساحة العمل")
        return path

    def read_file(self, relative_path: str, limit: int = 16000) -> str:
        if not self.can_read():
            raise PermissionError("لم تمنح صلاحية قراءة مساحة العمل")
        path = self._safe_path(relative_path)
        if not path.is_file():
            raise FileNotFoundError(relative_path)
        return path.read_text(encoding="utf-8", errors="replace")[:limit]

    def project_snapshot(self) -> dict[str, Any]:
        if not self.can_read():
            raise PermissionError("لم تمنح صلاحية قراءة مساحة العمل")
        result: dict[str, Any] = {
            "root": str(self.root),
            "files": [],
            "extensions": {},
            "total_lines": 0,
            "python_functions": 0,
            "python_classes": 0,
            "syntax_errors": [],
        }
        assert self.root is not None
        for path in sorted(self.root.rglob("*")):
            if not path.is_file() or path.stat().st_size > 1_000_000:
                continue
            if path.suffix.lower() not in {
                ".py", ".js", ".ts", ".html", ".css", ".sql", ".json", ".md", ".txt"
            }:
                continue
            relative = str(path.relative_to(self.root))
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
                lines = len(text.splitlines())
                result["files"].append({"path": relative, "lines": lines})
                ext = path.suffix.lower() or "unknown"
                result["extensions"][ext] = result["extensions"].get(ext, 0) + 1
                result["total_lines"] += lines
                if ext == ".py":
                    try:
                        tree = ast.parse(text)
                        result["python_functions"] += sum(
                            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                            for node in ast.walk(tree)
                        )
                        result["python_classes"] += sum(
                            isinstance(node, ast.ClassDef) for node in ast.walk(tree)
                        )
                    except SyntaxError as exc:
                        result["syntax_errors"].append(
                            {"path": relative, "error": exc.msg, "line": exc.lineno}
                        )
            except OSError:
                continue
        return result

    def research(self, query: str, mode: str = "academic") -> list[dict[str, Any]]:
        if requests is None:
            raise RuntimeError("ثبّت requests أولاً")
        if mode in {"academic", "both"} and not self.permissions.allowed("search_academic", "*"):
            raise PermissionError("لم تمنح صلاحية البحث الأكاديمي")
        if mode in {"web", "both"} and not self.permissions.allowed("search_web", "*"):
            raise PermissionError("لم تمنح صلاحية البحث في الويب")
        self.state = AgentState.RESEARCHING
        response = requests.get(
            "https://api.openalex.org/works",
            params={"search": query, "per-page": 8, "sort": "relevance_score:desc"},
            timeout=30,
        )
        response.raise_for_status()
        results = []
        for item in response.json().get("results", []):
            results.append({
                "title": item.get("title", ""),
                "year": item.get("publication_year"),
                "url": item.get("doi") or item.get("primary_location", {}).get("landing_page_url", ""),
                "citations": item.get("cited_by_count", 0),
                "source": "OpenAlex",
            })
        self.state = AgentState.REVIEWING
        return results

    def validate_python(self, relative_path: str) -> dict[str, Any]:
        if not self.can_read():
            raise PermissionError("لم تمنح صلاحية قراءة مساحة العمل")
        path = self._safe_path(relative_path)
        try:
            ast.parse(path.read_text(encoding="utf-8"))
            return {"ok": True, "path": relative_path, "error": ""}
        except SyntaxError as exc:
            return {
                "ok": False,
                "path": relative_path,
                "error": f"{exc.msg} — السطر {exc.lineno}",
            }

    def apply_patch(self, relative_path: str, new_content: str) -> dict[str, Any]:
        if not self.root:
            raise RuntimeError("لم يتم اختيار مساحة عمل")
        if not self.permissions.allowed("modify_files", str(self.root)):
            raise PermissionError("لم تمنح صلاحية تعديل الملفات")
        path = self._safe_path(relative_path)
        backup_dir = self.root / ".walid_ai_backups" / datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = None
        if path.exists():
            backup = backup_dir / path.name
            shutil.copy2(path, backup)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new_content, encoding="utf-8")
        self.state = AgentState.COMPLETED
        if self.db and hasattr(self.db, "log_operation"):
            self.db.log_operation("apply_patch", str(path), f"backup={backup_dir}")
        elif self.db and hasattr(self.db, "log"):
            self.db.log("apply_patch", str(path), f"backup={backup_dir}")
        return {"path": str(path), "backup": str(backup) if backup else None}

    def describe(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "plan": self.pending_plan.as_dict() if self.pending_plan else None,
            "root": str(self.root) if self.root else None,
        }
