from pathlib import Path
import hashlib
from walid_ai.config import TEXT_EXTENSIONS,MAX_FILE_BYTES
def safe_path(root,rel):
 root=Path(root).resolve();p=(root/rel).resolve()
 if p!=root and root not in p.parents:raise ValueError("المسار خارج مجلد العمل")
 return p
def files(root):return sorted(p for p in Path(root).rglob("*") if p.is_file() and p.suffix.lower() in TEXT_EXTENSIONS and p.stat().st_size<=MAX_FILE_BYTES)
def read(p):return Path(p).read_text(encoding="utf-8",errors="replace")
def create_file(root,rel,text):
 p=safe_path(root,rel)
 if p.exists():raise FileExistsError("الملف موجود مسبقاً")
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding="utf-8");return p
def create_dir(root,rel):p=safe_path(root,rel);p.mkdir(parents=True,exist_ok=True);return p
def md5(p):return hashlib.md5(Path(p).read_bytes()).hexdigest()
