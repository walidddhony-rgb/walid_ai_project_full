"""Thin coordinator between the UI and application services."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from walid_ai.services.app_services import AppServices


class AgentController:
    """Delegates business operations to AppServices."""

    def __init__(
        self,
        db=None,
        root: str | Path | None = None,
    ):
        self.services = AppServices(db=db, root=root)

    @property
    def db(self):
        return self.services.db

    @property
    def root(self) -> Path | None:
        return self.services.root

    @property
    def permissions(self):
        return self.services.permissions

    @property
    def state(self):
        return self.services.workflow.state

    @property
    def pending_plan(self):
        return self.services.workflow.pending_plan

    def set_root(self, root: str | Path | None) -> None:
        self.services.set_root(root)

    def plan(self, goal: str, source_mode: str = "local"):
        return self.services.workflow.plan(goal, source_mode)

    def grant(
        self,
        permission: str,
        scope: str = "*",
        mode: str = "once",
    ) -> bool:
        return self.services.workflow.grant(permission, scope, mode)

    def can_read(self) -> bool:
        return self.services.workflow.can_read()

    def read_file(
        self,
        relative_path: str,
        limit: int = 16000,
    ) -> str:
        return self.services.workflow.read_file(relative_path, limit)

    def project_snapshot(self) -> dict[str, Any]:
        return self.services.workflow.project_snapshot()

    def validate_python(self, relative_path: str) -> dict[str, Any]:
        return self.services.workflow.validate_python(relative_path)

    def research(
        self,
        query: str,
        mode: str = "academic",
    ) -> list[dict[str, Any]]:
        workflow = self.services.workflow
        workflow.state = workflow.state.RESEARCHING

        try:
            results = self.services.research.research(query, mode)
            workflow.state = workflow.state.REVIEWING
            return results
        except Exception:
            workflow.state = workflow.state.FAILED
            raise

    def apply_patch(
        self,
        relative_path: str,
        new_content: str,
    ) -> dict[str, Any]:
        workflow = self.services.workflow
        workflow.state = workflow.state.APPLYING

        try:
            result = self.services.patch.apply_patch(
                relative_path,
                new_content,
            )
            workflow.state = workflow.state.COMPLETED
            return result
        except Exception:
            workflow.state = workflow.state.FAILED
            raise

    def describe(self) -> dict[str, Any]:
        return self.services.workflow.describe()
