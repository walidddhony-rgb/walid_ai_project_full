from walid_ai.tools.filesystem import files,read,md5
class FileIndexer:
 def __init__(self,db):self.db=db
 def index(self,root):
  n=0
  for p in files(root):
   s=p.stat();self.db.upsert((str(p.relative_to(root)),str(p),s.st_size,md5(p),read(p)[:2000]));n+=1
  self.db.log("index",str(root),f"files={n}");return n
