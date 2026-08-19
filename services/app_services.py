"""Application service container."""
from __future__ import annotations

from pathlib import Path

from walid_ai.config import DB_PATH
from walid_ai.learning.learning_manager import LearningManager
from walid_ai.memory.database import DatabaseManager
from walid_ai.security.permissions import PermissionManager
from walid_ai.services.agent_workflow_service import AgentWorkflowService
from walid_ai.services.patch_service import PatchService
from walid_ai.services.research_service import ResearchService


class AppServices:
    """Creates and shares application services using common dependencies."""

    def __init__(
        self,
        db: DatabaseManager | None = None,
        root: str | Path | None = None,
    ):
        self.db = db or DatabaseManager(DB_PATH)
        self.root = Path(root).resolve() if root else None

        db_path = getattr(self.db, "path", DB_PATH)

        self.permissions = PermissionManager(db_path)
        self.learning = LearningManager(self.db)

        self.workflow = AgentWorkflowService(
            permission_manager=self.permissions,
            root=self.root,
        )

        self.research = ResearchService(
            permission_manager=self.permissions,
        )

        self.patch = PatchService(
            permission_manager=self.permissions,
            db=self.db,
            root=self.root,
        )

    def set_root(self, root: str | Path | None) -> None:
        self.root = Path(root).resolve() if root else None
        self.workflow.set_root(self.root)
        self.patch.set_root(self.root)