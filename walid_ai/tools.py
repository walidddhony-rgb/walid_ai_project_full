from langchain_core.tools import tool
import os

@tool
def list_files_in_directory(directory_path: str) -> str:
    """هذه الأداة تقوم بعرض جميع أسماء الملفات والمجلدات الموجودة في مسار معين."""
    try:
        files = os.listdir(directory_path)
        return f"الملفات والمجلدات الموجودة في المسار '{directory_path}' هي: {', '.join(files)}"
    except Exception as e:
        return f"حدث خطأ أثناء قراءة المجلد: {str(e)}"
