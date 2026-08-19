"""Academic and web research service."""
from __future__ import annotations

from typing import Any

from walid_ai.security.permissions import PermissionManager

try:
    import requests
except ImportError:
    requests = None


class ResearchService:
    """Retrieves research results after permission validation."""

    def __init__(self, permission_manager: PermissionManager):
        self.permissions = permission_manager

    def research(
        self,
        query: str,
        mode: str = "academic",
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        if requests is None:
            raise RuntimeError("ثبّت requests أولاً")

        if mode not in {"web", "academic", "both"}:
            raise ValueError("وضع البحث غير صالح")

        if mode in {"academic", "both"}:
            if not self.permissions.allowed("search_academic", "*"):
                raise PermissionError("لم تمنح صلاحية البحث الأكاديمي")

        if mode in {"web", "both"}:
            if not self.permissions.allowed("search_web", "*"):
                raise PermissionError("لم تمنح صلاحية البحث في الويب")

        response = requests.get(
            "https://api.openalex.org/works",
            params={
                "search": query,
                "per-page": min(max(limit, 1), 25),
                "sort": "relevance_score:desc",
            },
            timeout=30,
        )
        response.raise_for_status()

        results: list[dict[str, Any]] = []

        for item in response.json().get("results", []):
            primary_location = item.get("primary_location") or {}

            results.append({
                "title": item.get("title", ""),
                "year": item.get("publication_year"),
                "url": (
                    item.get("doi")
                    or primary_location.get("landing_page_url", "")
                ),
                "citations": item.get("cited_by_count", 0),
                "source": "OpenAlex",
            })

        return results