"""Global configuration for Walid AI."""
from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "Walid AI"
APP_VERSION = "0.4.0"

MODEL = os.getenv("WALID_AI_MODEL", "qwen2.5:7b")
OLLAMA_URL = os.getenv("WALID_AI_OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
OLLAMA_TAGS_URL = os.getenv("WALID_AI_OLLAMA_TAGS", "http://127.0.0.1:11434/api/tags")

DATA_DIR = Path(os.getenv("WALID_AI_DATA_DIR", str(Path.home() / ".walid_ai")))
DB_PATH = DATA_DIR / "walid_ai.db"

MAX_FILE_BYTES = 1_000_000

TEXT_EXTENSIONS = frozenset({
    ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".scss",
    ".sql", ".json", ".yaml", ".yml", ".toml", ".md", ".txt",
    ".csv", ".xml", ".ini", ".ps1", ".sh", ".java", ".c", ".cpp",
    ".h", ".hpp", ".php", ".go", ".rs",
})

CODE_EXTENSIONS = frozenset({
    ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".scss",
    ".sql", ".java", ".c", ".cpp", ".h", ".hpp", ".php", ".go", ".rs",
})

IMAGE_EXTENSIONS = frozenset({
    ".png", ".jpg", ".jpeg", ".bmp", ".webp",
})

SYSTEM_PROMPT = (
    "أنت Walid AI، مساعد محلي عربي. "
    "أجب بدقة، اذكر مصادر الملفات، ولا تدّع تنفيذ عملية لم تحدث."
)

DATA_DIR.mkdir(parents=True, exist_ok=True)
