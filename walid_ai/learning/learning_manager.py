from __future__ import annotations

import json
from datetime import datetime


class LearningManager:
    def __init__(self, db):
        self.db = db

    def save_approved_knowledge(
        self,
        topic: str,
        summary: str,
        sources: list[dict],
        project: str = "global",
    ):
        payload = {
            "topic": topic,
            "summary": summary,
            "sources": sources,
            "approved_at": datetime.now().isoformat(),
            "project": project,
        }
        self.db.set_memory(
            f"knowledge:{project}:{topic}",
            json.dumps(payload, ensure_ascii=False),
            category="approved_knowledge",
        )

    def retrieve(self, query: str, project: str = "global") -> list[dict]:
        memories = self.db.get_all_memory()
        result = []
        for item in memories:
            if item.get("category") != "approved_knowledge":
                continue
            if project not in item.get("key", ""):
                continue
            if query.lower() in item.get("value", "").lower():
                try:
                    result.append(json.loads(item["value"]))
                except json.JSONDecodeError:
                    pass
        return result