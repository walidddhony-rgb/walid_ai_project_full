from langchain_ollama import ChatOllama
# نقوم باستيراد الأداة من الملف الذي أنشأناه للتو
from walid_ai.tools import list_files_in_directory 

# إعداد النموذج
llm = ChatOllama(model="qwen2.5:7b")

# ربط الأداة بالنموذج
llm_with_tools = llm.bind_tools([list_files_in_directory])

# توجيه سؤال للمساعد الذكي
query = "ابحث لي عن الملفات الموجودة في المجلد الحالي الذي مساره '.'"

print(f"السؤال: {query}")
print("جاري التفكير...")

# إرسال السؤال
response = llm_with_tools.invoke(query)

if response.tool_calls:
    print("\nقرر الذكاء الاصطناعي استخدام الأداة التالية:")
    for tool_call in response.tool_calls:
        print(f"- اسم الأداة: {tool_call['name']}")
        print(f"- المُدخلات (Arguments): {tool_call['args']}")
else:
    print(response.content)
