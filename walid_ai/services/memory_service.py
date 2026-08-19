"""High-level memory retrieval, deduplication, and vetted-knowledge storage."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from walid_ai.memory.database import DatabaseManager


@dataclass(frozen=True)
class MemoryContext:
    knowledge: list[dict[str, Any]]
    similar_turns: list[dict[str, str]]

    def as_prompt_block(self, max_chars: int = 6000) -> str:
        sections: list[str] = []

        if self.knowledge:
            lines = ['## معرفة محلية مسترجعة']
            for item in self.knowledge:
                source = f" | المصدر: {item['source_url']}" if item.get('source_url') else ''
                excerpt = item['content'][:1100]
                lines.append(
                    f"- **{item['title']}** ({item['category']}){source}\n{excerpt}"
                )
            sections.append('\n'.join(lines))

        if self.similar_turns:
            lines = ['## إجابات سابقة مشابهة']
            for item in self.similar_turns:
                lines.append(
                    f"- سؤال سابق: {item['question'][:500]}\n"
                    f"  جواب سابق: {item['answer'][:900]}"
                )
            lines.append('لا تكرر النص السابق؛ أضف معلومات جديدة أو اشرح ما تغير.')
            sections.append('\n'.join(lines))

        return '\n\n'.join(sections)[:max_chars]


class MemoryService:
    """Retrieval-augmented local memory without training the base model."""

    STOPWORDS = {
        'في', 'من', 'على', 'الى', 'إلى', 'عن', 'مع', 'هذا', 'هذه', 'ذلك', 'تلك',
        'ما', 'ماذا', 'هل', 'كيف', 'لماذا', 'اريد', 'أريد', 'قم', 'لي', 'ان', 'أن',
        'the', 'and', 'for', 'with', 'from', 'about', 'what', 'how', 'please',
    }

    def __init__(self, db: DatabaseManager):
        self.db = db

    def build_context(self, user_query: str, history_limit: int = 80) -> MemoryContext:
        knowledge = self.db.search_knowledge(user_query, limit=6)
        similar_turns = self._