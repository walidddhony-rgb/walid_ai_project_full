"""Planning, local project analysis, and validation workflows."""
from __future__ import annotations

import ast
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from walid_ai.security.permissions import PermissionManager


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
        lines.extend(f"{index}. {step}" for index, step in enumerate(self.steps, 1))
        lines.extend(["", "**الصلاحيات المطلوبة:**"])
        lines.extend(f"- {permission}" for permission in self.permissions)
        lines.extend(["", "**المخاطر والضوابط:**"])
        lines.extend(f"- {risk}" for risk in self.risks)
        lines.extend(["", "اكتب: **أوافق على الخطة** للمتابعة."])
        return "\n".join(lines)


class AgentWorkflowService:
    """Manages project analysis and plan lifecycle."""

    ALLOWED_EXTENSIONS = {
        ".py", ".js", ".ts", ".html", ".css",
        ".sql", ".json", ".md", ".txt",
    }
    MAX_FILE_SIZE = 1_000_000

    def __init__(
        self,
        permission_manager: PermissionManager,
        root: Path | None = None,
    ):
        self.permissions = permission_manager
        self.root = Path(root).resolve() if root else None
        self.state = AgentState.IDLE
        self.pending_plan: AgentPlan | None = None

    def set_root(self, root: str | Path | None) -> None:
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
            "أضف", "إضافة", "عدّل", "عدل", "حسّن", "حسن",
            "طوّر", "طور", "أنشئ", "اكتب", "تعديل", "تطوير",
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

    def grant(
        self,
        permission: str,
        scope: str = "*",
        mode: str = "once",
    ) -> bool:
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

        return path.read_text(
            encoding="utf-8",
            errors="replace",
        )[:limit]

    def project_snapshot(self) -> dict[str, Any]:
        if not self.can_read():
            raise PermissionError("لم تمنح صلاحية قراءة مساحة العمل")

        assert self.root is not None

        result: dict[str, Any] = {
            "root": str(self.root),
            "files": [],
            "extensions": {},
            "total_lines": 0,
            "python_functions": 0,
            "python_classes": 0,
            "syntax_errors": [],
        }

        for path in sorted(self.root.rglob("*")):
            try:
                if not path.is_file():
                    continue

                if path.stat().st_size > self.MAX_FILE_SIZE:
                    continue

                extension = path.suffix.lower()
                if extension not in self.ALLOWED_EXTENSIONS:
                    continue

                text = path.read_text(encoding="utf-8", errors="replace")
                relative = str(path.relative_to(self.root))
                lines = len(text.splitlines())

                result["files"].append({
                    "path": relative,
                    "lines": lines,
                })
                result["extensions"][extension] = (
                    result["extensions"].get(extension, 0) + 1
                )
                result["total_lines"] += lines

                if extension == ".py":
                    self._analyze_python_file(relative, text, result)

            except OSError:
                continue

        return result

    def _analyze_python_file(
        self,
        relative_path: str,
        text: str,
        result: dict[str, Any],
    ) -> None:
        try:
            tree = ast.parse(text)

            result["python_functions"] += sum(
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                for node in ast.walk(tree)
            )
            result["python_classes"] += sum(
                isinstance(node, ast.ClassDef)
                for node in ast.walk(tree)
            )

        except SyntaxError as exc:
            result["syntax_errors"].append({
                "path": relative_path,
                "error": exc.msg,
                "line": exc.lineno,
            })

    def validate_python(self, relative_path: str) -> dict[str, Any]:
        if not self.can_read():
            raise PermissionError("لم تمنح صلاحية قراءة مساحة العمل")

        path = self._safe_path(relative_path)

        try:
            ast.parse(path.read_text(encoding="utf-8"))
            return {
                "ok": True,
                "path": relative_path,
                "error": "",
            }
        except SyntaxError as exc:
            return {
                "ok": False,
                "path": relative_path,
                "error": f"{exc.msg} — السطر {exc.lineno}",
            }

    def describe(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "plan": self.pending_plan.as_dict() if self.pending_plan else None,
            "root": str(self.root) if self.root else None,
        }