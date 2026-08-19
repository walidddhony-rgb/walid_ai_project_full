# Walid AI — FTS5 Memory Patch

## Added files

- `walid_ai/memory/database.py`: SQLite schema upgrade with `knowledge` and FTS5 index.
- `walid_ai/services/memory_service.py`: retrieval, deduplication, and vetted knowledge storage.
- `walid_ai/services/__init__.py`: exports `MemoryService` and `MemoryContext`.

## Safe integration

1. Replace `walid_ai/memory/database.py` with the provided version.
2. Add `walid_ai/services/memory_service.py` without deleting any existing service modules.
3. Do **not** overwrite an existing `walid_ai/services/__init__.py` blindly; merge the two export lines into it if it already exports other services.
4. Start the app once. The database schema migrates automatically; existing history is retained.

## Minimal integration in `main_window.py`

After creating `self.db`, add:

```python
from walid_ai.services.memory_service import MemoryService
self.memory_service = MemoryService(self.db)
```

Before building `messages` in `send_message()`, add:

```python
memory_context = self.memory_service.build_context(text)
memory_prompt = memory_context.as_prompt_block()
```

Then append `memory_prompt` to the system content only when it is non-empty:

```python
system_content = SYSTEM_PROMPT + "\nPROJECT_CONTEXT:\n" + json.dumps(payload, ensure_ascii=False)
if memory_prompt:
    system_content += "\n\n" + memory_prompt
messages = [{"role": "system", "content": system_content}, *self.db.history(limit=8)]
```

## Learning policy

Do not save every assistant reply. Save only reviewed research summaries, stable project decisions, verified answers, and resolved errors. Use `MemoryService.learn_research_result()` after reviewing a research result, or `learn_verified_answer()` only after source checks.
