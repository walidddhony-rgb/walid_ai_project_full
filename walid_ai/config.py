from pathlib import Path
import os
APP_NAME="Walid AI"
MODEL=os.getenv("WALID_AI_MODEL","qwen2.5:7b")
OLLAMA_URL=os.getenv("WALID_AI_OLLAMA_URL","http://127.0.0.1:11434/api/chat")
DATA_DIR=Path(os.getenv("WALID_AI_DATA_DIR",Path.home()/".walid_ai"))
DB_PATH=DATA_DIR/"walid_ai.db"
MAX_FILE_BYTES=1_000_000
TEXT_EXTENSIONS={".py",".js",".ts",".jsx",".tsx",".html",".css",".scss",".sql",".json",".yaml",".yml",".toml",".md",".txt",".csv",".xml",".ini",".ps1",".sh",".java",".c",".cpp",".h",".hpp",".php",".go",".rs"}
CODE_EXTENSIONS={".py",".js",".ts",".jsx",".tsx",".html",".css",".scss",".sql",".java",".c",".cpp",".h",".hpp",".php",".go",".rs"}
SYSTEM_PROMPT="أنت Walid AI، مساعد محلي عربي. أجب بدقة، اذكر مصادر الملفات، ولا تدّع تنفيذ عملية لم تحدث."
