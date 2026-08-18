import sqlite3
from pathlib import Path
class DatabaseManager:
 def __init__(self,path:Path):
  self.path=path; path.parent.mkdir(parents=True,exist_ok=True)
  with sqlite3.connect(path) as c:
   c.executescript("""CREATE TABLE IF NOT EXISTS conversations(id INTEGER PRIMARY KEY,role TEXT,content TEXT,created DATETIME DEFAULT CURRENT_TIMESTAMP);CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY,absolute TEXT,size INTEGER,hash TEXT,preview TEXT,updated DATETIME DEFAULT CURRENT_TIMESTAMP);CREATE TABLE IF NOT EXISTS operations(id INTEGER PRIMARY KEY,operation TEXT,target TEXT,details TEXT,status TEXT,created DATETIME DEFAULT CURRENT_TIMESTAMP);CREATE TABLE IF NOT EXISTS memory(key TEXT PRIMARY KEY,value TEXT,category TEXT);""")
 def add_message(self,role,content):
  with sqlite3.connect(self.path) as c:c.execute("INSERT INTO conversations(role,content) VALUES(?,?)",(role,content))
 def history(self,limit=12):
  with sqlite3.connect(self.path) as c:r=c.execute("SELECT role,content FROM conversations ORDER BY id DESC LIMIT ?",(limit,)).fetchall()
  return [{"role":a,"content":b} for a,b in reversed(r)]
 def log(self,op,target="",details="",status="success"):
  with sqlite3.connect(self.path) as c:c.execute("INSERT INTO operations(operation,target,details,status) VALUES(?,?,?,?)",(op,target,details,status))
 def upsert(self,data):
  with sqlite3.connect(self.path) as c:c.execute("INSERT OR REPLACE INTO files(path,absolute,size,hash,preview) VALUES(?,?,?,?,?)",tuple(data))
