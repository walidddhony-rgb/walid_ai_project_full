import ast
from pathlib import Path
from walid_ai.tools.filesystem import files,read
class CodeAnalyzer:
 @staticmethod
 def analyze(p):
  p=Path(p);text=read(p);r={"file":p.name,"language":p.suffix,"lines":len(text.splitlines())}
  if p.suffix==".py":
   try:t=ast.parse(text)
   except SyntaxError:r["error"]="خطأ صياغة Python";return r
   r["imports"]=[x.names[0].name for x in ast.walk(t) if isinstance(x,ast.Import) and x.names];r["functions"]=[x.name for x in ast.walk(t) if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef))];r["classes"]=[x.name for x in ast.walk(t) if isinstance(x,ast.ClassDef)]
  return r
 @staticmethod
 def project(root):return [CodeAnalyzer.analyze(p) for p in files(root) if p.suffix in {".py",".js",".ts",".java",".cpp"}]
