from __future__ import annotations

import requests


class SourceManager:
    """Fetches web and academic references after explicit permission."""

    def web_search(self, query: str, limit: int = 8) -> list[dict]:
        response = requests.get(
            "https://api.openalex.org/works",
            params={"search": query, "per-page": limit},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        return [
            {
                "title": item.get("title", ""),
                "year": item.get("publication_year"),
                "url": item.get("primary_location", {}).get("landing_page_url", ""),
                "doi": item.get("doi", ""),
                "source": "OpenAlex",
            }
            for item in data.get("results", [])
        ]

    def academic_search(self, query: str, limit: int = 8) -> list[dict]:
        response = requests.get(
            "https://api.openalex.org/works",
            params={"search": query, "per-page": limit, "sort": "relevance_score:desc"},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        return [
            {
                "title": item.get("title", ""),
                "year": item.get("publication_year"),
                "url": item.get("doi") or item.get("primary_location", {}).get("landing_page_url", ""),
                "citations": item.get("cited_by_count", 0),
                "source": "OpenAlex Academic",
            }
            for item in data.get("results", [])
        ]