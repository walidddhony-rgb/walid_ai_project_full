from __future__ import annotations

import json
import tempfile
import threading
import wave
from pathlib import Path
from urllib.parse import quote_plus

import requests
from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot, QTimer
from PySide6.QtGui import QFont, QTextOption
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from walid_ai.config import DB_PATH, MODEL, OLLAMA_URL, SYSTEM_PROMPT
from walid_ai.memory.database import DatabaseManager
from walid_ai.tools.filesystem import files, read
from walid_ai.tools.indexer import FileIndexer
from walid_ai.agent.controller import AgentController

try:
    import sounddevice as sd
    import numpy as np
except ImportError:
    sd = None
    np = None

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None

try:
    import pyttsx3
except ImportError:
    pyttsx3 = None


class AutoGrowTextEdit(QTextEdit):
    height_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(False)
        self.setMinimumHeight(46)
        self.setMaximumHeight(180)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setPlaceholderText("اكتب رسالتك أو استخدم الميكروفون... (Ctrl+Enter للإرسال)")
        self.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.textChanged.connect(self.adjust_height)
        self.adjust_height()

    def adjust_height(self) -> None:
        document_height = self.document().size().height()
        height = max(46, min(int(document_height + 24), 180))
        self.setFixedHeight(height)
        self.height_changed.emit(height)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                window = self.window()
                if hasattr(window, "send_message"):
                    window.send_message()
                return
        super().keyPressEvent(event)


class AttachmentPanel(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.paths: list[Path] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.file_list = QListWidget()
        self.file_list.setMaximumHeight(94)
        self.file_list.setVisible(False)
        layout.addWidget(self.file_list)

    def choose(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "إرفاق ملفات أو صور",
            "",
            (
                "كل الملفات (*);;"
                "الصور (*.png *.jpg *.jpeg *.bmp *.webp);;"
                "المستندات (*.pdf *.docx *.xlsx *.csv *.txt *.md);;"
                "الأكواد (*.py *.js *.ts *.html *.css *.sql)"
            ),
        )
        for raw_path in paths:
            path = Path(raw_path)
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if path not in self.paths and size <= 10 * 1024 * 1024:
                self.add_path(path)
        self.changed.emit()

    def add_path(self, path: Path) -> None:
        self.paths.append(path)
        item = QListWidgetItem(f"📎 {path.name}")
        self.file_list.addItem(item)
        remove_button = QPushButton("×")
        remove_button.clicked.connect(lambda: self.remove(path))
        self.file_list.setItemWidget(item, remove_button)
        self.file_list.setVisible(True)

    def remove(self, path: Path) -> None:
        if path in self.paths:
            self.paths.remove(path)
        for index in range(self.file_list.count() - 1, -1, -1):
            item = self.file_list.item(index)
            if item and item.text().endswith(path.name):
                self.file_list.takeItem(index)
        self.file_list.setVisible(bool(self.paths))
        self.changed.emit()

    def clear(self) -> None:
        self.paths.clear()
        self.file_list.clear()
        self.file_list.setVisible(False)
        self.changed.emit()

    def values(self) -> list[Path]:
        return list(self.paths)


class ChatWorker(QObject):
    token = Signal(str)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, messages: list[dict[str, str]]):
        super().__init__()
        self.messages = messages

    @Slot()
    def run(self) -> None:
        full: list[str] = []
        try:
            response = requests.post(
                OLLAMA_URL,
                json={
                    "model": MODEL,
                    "messages": self.messages,
                    "stream": True,
                    "options": {"temperature": 0.2, "num_ctx": 4096},
                },
                timeout=300,
                stream=True,
            )
            if response.status_code >= 400:
                try:
                    details = response.json()
                except ValueError:
                    details = response.text
                self.failed.emit(f"Ollama HTTP {response.status_code}: {details}")
                return
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue
                payload = json.loads(line)
                if payload.get("error"):
                    self.failed.emit(str(payload["error"]))
                    return
                piece = payload.get("message", {}).get("content", "")
                if piece:
                    full.append(piece)
                    self.token.emit(piece)
                if payload.get("done"):
                    break
            self.finished.emit("".join(full).strip())
        except requests.exceptions.ConnectionError:
            self.failed.emit("لا يمكن الاتصال بـ Ollama. شغّل: ollama serve")
        except requests.exceptions.Timeout:
            self.failed.emit("انتهت مهلة الاتصال بالنموذج المحلي.")
        except Exception as exc:
            self.failed.emit(f"خطأ أثناء الإجابة: {exc}")


class ResearchWorker(QObject):
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, query: str, academic: bool = False):
        super().__init__()
        self.query = query
        self.academic = academic

    @Slot()
    def run(self) -> None:
        try:
            params = {"search": self.query, "per-page": 8}
            if self.academic:
                params["sort"] = "relevance_score:desc"
            response = requests.get(
                "https://api.openalex.org/works",
                params=params,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])
            if not results:
                label = "أكاديمية" if self.academic else "ويب"
                self.finished.emit(f"لم توجد نتائج {label} لـ: {self.query}")
                return
            label = "أكاديمية" if self.academic else "ويب"
            lines = [f"## نتائج البحث {label}: {self.query}\n"]
            for item in results:
                title = item.get("title", "بدون عنوان")
                year = item.get("publication_year", "")
                doi = item.get("doi") or item.get("primary_location", {}).get("landing_page_url", "")
                citations = item.get("cited_by_count", 0)
                lines.append(f"### {title}")
                if year:
                    lines.append(f"**السنة:** {year}")
                if citations:
                    lines.append(f"**الاستشهادات:** {citations}")
                if doi:
                    lines.append(f"**الرابط:** {doi}")
                lines.append("")
            self.finished.emit("\n".join(lines))
        except Exception as exc:
            self.failed.emit(f"فشل البحث: {exc}")


class VoiceWorker(QObject):
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self._stop = False
        self._audio_data: list = []
        self._recording = False

    def request_stop(self) -> None:
        self._stop = True

    @Slot()
    def run(self) -> None:
        if sd is None or np is None or WhisperModel is None:
            self.failed.emit(
                "الصوت غير مثبت. نفّذ: "
                "python -m pip install faster-whisper sounddevice numpy"
            )
            return
        temporary_path = None
        try:
            sample_rate = 16000
            self._audio_data = []
            self._stop = False
            self._recording = True

            def callback(indata, frames, time_info, status):
                if self._stop:
                    raise sd.CallbackStop
                self._audio_data.append(indata.copy())

            stream = sd.InputStream(
                samplerate=sample_rate,
                channels=1,
                dtype="float32",
                callback=callback,
            )
            stream.start()
            while not self._stop:
                sd.sleep(100)
            stream.stop()
            stream.close()
            self._recording = False

            if not self._audio_data:
                self.finished.emit("")
                return
            audio = np.concatenate(self._audio_data, axis=0)
            if len(audio) < sample_rate * 0.3:
                self.finished.emit("")
                return
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                temporary_path = f.name
            with wave.open(temporary_path, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(sample_rate)
                pcm = np.clip(audio.flatten() * 32767, -32768, 32767).astype(np.int16)
                wav_file.writeframes(pcm.tobytes())
            model = WhisperModel("base", device="cpu", compute_type="int8")
            segments, _ = model.transcribe(
                temporary_path,
                language="ar",
                vad_filter=True,
            )
            self.finished.emit(" ".join(s.text for s in segments).strip())
        except Exception as exc:
            self.failed.emit(f"خطأ في الميكروفون أو التعرف الصوتي: {exc}")
        finally:
            if temporary_path:
                Path(temporary_path).unlink(missing_ok=True)


class SpeechEngine:
    def __init__(self):
        self.engine = None
        self.lock = threading.Lock()
        if pyttsx3 is not None:
            try:
                self.engine = pyttsx3.init()
                self.engine.setProperty("rate", 150)
            except Exception:
                self.engine = None

    @property
    def available(self) -> bool:
        return self.engine is not None

    def speak(self, text: str) -> None:
        if not self.engine:
            return

        def worker() -> None:
            with self.lock:
                try:
                    self.engine.say(text[:1200])
                    self.engine.runAndWait()
                except Exception:
                    pass

        threading.Thread(target=worker, daemon=True).start()


class ChatBubble(QWidget):
    copy_requested = Signal(str, str)

    def __init__(self, role: str, text: str = ""):
        super().__init__()
        self.role = role
        self.text = text
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 7, 12, 7)
        layout.setSpacing(3)

        header = QHBoxLayout()
        title = QLabel("أنت" if role == "user" else "Walid AI")
        title.setObjectName("bubbleTitle")
        header.addWidget(title)
        header.addStretch()
        copy_button = QPushButton("نسخ")
        copy_button.setObjectName("copyButton")
        copy_button.clicked.connect(
            lambda: self.copy_requested.emit(self.role, self.text)
        )
        header.addWidget(copy_button)
        layout.addLayout(header)

        self.browser = QTextBrowser()
        self.browser.setObjectName(
            "userBubble" if role == "user" else "assistantBubble"
        )
        self.browser.setMarkdown(text)
        self.browser.setReadOnly(True)
        self.browser.setOpenExternalLinks(True)
        self.browser.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.browser.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.browser.setLineWrapMode(QTextBrowser.LineWrapMode.WidgetWidth)
        self.browser.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        layout.addWidget(self.browser)
        self.update_height()

    def update_text(self, text: str) -> None:
        self.text = text
        self.browser.setMarkdown(text)
        self.update_height()

    def update_height(self) -> None:
        # الحصول على العرض المتاح للمتصفح
        viewport_width = self.browser.viewport().width()
        if viewport_width <= 0:
            viewport_width = 600
            
        # ضبط عرض النص ليلتف بشكل صحيح بناءً على المساحة المتاحة
        document = self.browser.document()
        document.setTextWidth(max(200, viewport_width - 20))
        
        # حساب الارتفاع المناسب
        height = max(30, min(int(document.size().height()) + 60, 430))
        
        # تحديد الارتفاع فقط وترك العرض ليتمدد بحرية
        self.browser.setFixedHeight(height)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.update_height()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db = DatabaseManager(DB_PATH)
        self.root: Path | None = None
        self.agent = AgentController(self.db) if AgentController else None
        self.thread: QThread | None = None
        self.worker: QObject | None = None
        self.busy = False
        self.streaming_text = ""
        self.streaming_bubble: ChatBubble | None = None
        self.speech = SpeechEngine()
        self.speak_enabled = False
        self.pending_plan = None
        self.is_recording = False
        self.voice_thread: QThread | None = None
        self.voice_worker: VoiceWorker | None = None

        self.setWindowTitle("Walid AI")
        self.resize(1400, 880)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setStyleSheet(STYLE)
        self.build_ui()
        self.add_message(
            "assistant",
            "مرحباً! أنا Walid AI Developer Agent.\n\n"
            "أستطيع تحليل وتطوير مشاريعك بأمان.\n\n"
            "اكتب طلبك أو استخدم الميكروفون.\n"
            "اضغط 🎤 لبدء التسجيل واضغط ⏹️ لإيقافه وإرساله.",
        )

    def build_ui(self) -> None:
        central = QWidget()
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self.build_sidebar())
        root_layout.addWidget(self.build_chat_area(), 1)
        self.setCentralWidget(central)

    def build_sidebar(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("sidebar")
        panel.setFixedWidth(315)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        brand = QLabel("✦ Walid AI")
        brand.setObjectName("brand")
        layout.addWidget(brand)

        buttons = [
            ("＋ محادثة جديدة", self.new_chat),
            ("📁 مساحة العمل", self.choose_folder),
            ("⟳ فهرسة الملفات", self.index_workspace),
            ("📋 نسخ المحادثة كاملة", self.copy_all_chat),
        ]
        for text, callback in buttons:
            button = QPushButton(text)
            button.clicked.connect(callback)
            layout.addWidget(button)

        web_btn = QPushButton("🌐 بحث الويب")
        web_btn.clicked.connect(lambda: self.start_research(False))
        layout.addWidget(web_btn)

        acad_btn = QPushButton("🎓 بحث أكاديمي")
        acad_btn.clicked.connect(lambda: self.start_research(True))
        layout.addWidget(acad_btn)

        self.speech_button = QPushButton("🔊 نطق الردود")
        self.speech_button.setCheckable(True)
        self.speech_button.setEnabled(self.speech.available)
        self.speech_button.toggled.connect(self.toggle_speech)
        layout.addWidget(self.speech_button)

        self.workspace_label = QLabel("لم يتم اختيار مساحة عمل")
        self.workspace_label.setObjectName("muted")
        self.workspace_label.setWordWrap(True)
        layout.addWidget(self.workspace_label)
        layout.addStretch()

        voice_state = "متاح" if sd and np and WhisperModel else "غير مثبت"
        info = QLabel(f"النموذج: {MODEL}\nالصوت: {voice_state}")
        info.setObjectName("muted")
        layout.addWidget(info)
        return panel

    def build_chat_area(self) -> QWidget:
        area = QWidget()
        layout = QVBoxLayout(area)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header.setObjectName("header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(26, 16, 26, 16)
        title = QLabel("محادثة جديدة")
        title.setObjectName("pageTitle")
        header_layout.addWidget(title)
        header_layout.addStretch()
        self.status_label = QLabel("● جاهز")
        self.status_label.setObjectName("status")
        header_layout.addWidget(self.status_label)
        layout.addWidget(header)

        self.messages = QListWidget()
        self.messages.setObjectName("messages")
        self.messages.setSpacing(6)
        self.messages.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.messages.setVerticalScrollMode(
            QListWidget.ScrollMode.ScrollPerPixel
        )
        self.messages.verticalScrollBar().setSingleStep(12)
        self.messages.setResizeMode(QListWidget.ResizeMode.Adjust)
        layout.addWidget(self.messages, 1)

        composer = QWidget()
        composer.setObjectName("composer")
        composer_layout = QVBoxLayout(composer)
        composer_layout.setContentsMargins(24, 10, 24, 18)
        composer_layout.setSpacing(6)

        self.attachments = AttachmentPanel()
        self.attachments.changed.connect(self.on_attachments_changed)
        composer_layout.addWidget(self.attachments)

        input_row = QHBoxLayout()
        input_row.setSpacing(6)

        self.plus_button = QPushButton("+")
        self.plus_button.setObjectName("plusButton")
        self.plus_button.setToolTip("إرفاق ملفات أو صور")
        self.plus_button.clicked.connect(self.attachments.choose)
        input_row.addWidget(self.plus_button)

        self.input = AutoGrowTextEdit()
        self.input.setObjectName("chatInput")
        input_row.addWidget(self.input, 1)

        self.voice_button = QPushButton("🎤")
        self.voice_button.setObjectName("voiceButton")
        self.voice_button.setToolTip("اضغط لبدء التسجيل، واضغط مرة أخرى للإيقاف والإرسال")
        self.voice_button.setCheckable(True)
        self.voice_button.clicked.connect(self.toggle_voice_recording)
        self.voice_button.setEnabled(
            sd is not None and np is not None and WhisperModel is not None
        )
        input_row.addWidget(self.voice_button)

        self.send_button = QPushButton("إرسال ➤")
        self.send_button.setObjectName("sendButton")
        self.send_button.clicked.connect(self.send_message)
        input_row.addWidget(self.send_button)
        composer_layout.addLayout(input_row)
        layout.addWidget(composer)
        return area

    def add_message(self, role: str, text: str = "") -> ChatBubble:
        bubble = ChatBubble(role, text)
        bubble.copy_requested.connect(self.copy_message)
        item = QListWidgetItem()
        item.setSizeHint(bubble.sizeHint())
        self.messages.addItem(item)
        self.messages.setItemWidget(item, bubble)
        self.messages.scrollToBottom()

        QTimer.singleShot(50, lambda: self._refresh_bubble(item, bubble))
        return bubble

    def _refresh_bubble(self, item: QListWidgetItem, bubble: ChatBubble) -> None:
        bubble.update_height()
        item.setSizeHint(bubble.sizeHint())

    def copy_message(self, _role: str, text: str) -> None:
        QApplication.clipboard().setText(text)
        self.status_label.setText("● تم النسخ")

    def copy_all_chat(self) -> None:
        messages = self.db.history(limit=10000)
        text = "\n\n".join(
            ("المستخدم" if item["role"] == "user" else "Walid AI")
            + ":\n"
            + item["content"]
            for item in messages
        )
        QApplication.clipboard().setText(text)
        self.status_label.setText("● تم نسخ المحادثة")

    def on_attachments_changed(self) -> None:
        count = len(self.attachments.values())
        self.status_label.setText(f"● {count} مرفق" if count else "● جاهز")

    def build_attachment_context(self, paths: list[Path]) -> list[dict]:
        text_extensions = {
            ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css",
            ".scss", ".sql", ".json", ".yaml", ".yml", ".md", ".txt", ".csv",
        }
        image_extensions = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
        context = []
        for path in paths:
            suffix = path.suffix.lower()
            if suffix in text_extensions:
                try:
                    context.append({
                        "file": path.name,
                        "type": "text_or_code",
                        "content": path.read_text(
                            encoding="utf-8", errors="replace"
                        )[:12000],
                    })
                except OSError as exc:
                    context.append({"file": path.name, "error": str(exc)})
            elif suffix in image_extensions:
                context.append({
                    "file": path.name,
                    "type": "image",
                    "note": "صورة مرفقة؛ يلزم نموذج بصري لتحليلها.",
                })
            else:
                context.append({
                    "file": path.name,
                    "type": "document_or_binary",
                    "note": "ملف غير نصي؛ يحتاج محللاً خاصاً بصيغته.",
                })
        return context

    def check_ollama(self) -> bool:
        try:
            response = requests.get(
                "http://127.0.0.1:11434/api/tags",
                timeout=5,
            )
            response.raise_for_status()
            models = response.json().get("models", [])
            names = [item.get("name", "") for item in models]
            if names and MODEL not in names and not any(
                name.startswith(MODEL.split(":")[0]) for name in names
            ):
                self.add_message(
                    "assistant",
                    f"النموذج `{MODEL}` غير مثبت. النماذج المتاحة: {names}",
                )
                return False
            return True
        except Exception:
            self.add_message(
                "assistant",
                "تعذر الوصول إلى Ollama. شغّل: `ollama serve`",
            )
            return False

    def send_message(self) -> None:
        text = self.input.toPlainText().strip()
        if not text or self.busy:
            return

        attached_paths = self.attachments.values()
        self.input.clear()
        self.input.adjust_height()
        self.add_message("user", text)
        self.db.add_message("user", text)

        if self.handle_agent_plan_request(text):
            self.attachments.clear()
            return

        if not self.check_ollama():
            self.attachments.clear()
            return

        self.set_busy(True)
        local_context = []
        if self.root:
            local_context = [
                {
                    "file": str(path.relative_to(self.root)),
                    "content": read(path)[:3000],
                }
                for path in files(self.root)[:8]
            ]

        payload = {
            "local_files": local_context,
            "attachments": self.build_attachment_context(attached_paths),
            "instructions": [
                "حلل الكود إذا كان السؤال برمجياً.",
                "اقترح Patch متوافقاً مع الملفات الحالية.",
                "لا تدّع تنفيذ تعديل لم يحدث.",
                "اطلب الموافقة قبل تعديل الملفات.",
            ],
        }
        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
                + "\nPROJECT_CONTEXT:\n"
                + json.dumps(payload, ensure_ascii=False),
            },
            *self.db.history(limit=8),
        ]

        self.streaming_text = ""
        self.streaming_bubble = self.add_message("assistant", "")
        self.thread = QThread()
        self.worker = ChatWorker(messages)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.token.connect(self.on_token)
        self.worker.finished.connect(self.on_answer_finished)
        self.worker.failed.connect(self.on_answer_failed)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()
        self.attachments.clear()

    def start_research(self, academic: bool) -> None:
        query = self.input.toPlainText().strip()
        if not query:
            label = "أكاديمي" if academic else "ويب"
            QMessageBox.information(
                self,
                "البحث",
                f"اكتب موضوع البحث {label} في مربع الرسالة أولاً.",
            )
            return
        if self.busy:
            return
        self.input.clear()
        self.input.adjust_height()
        label = "أكاديمي" if academic else "ويب"
        self.add_message("user", f"بحث {label}: {query}")
        self.set_busy(True)
        self.status_label.setText(f"● يبحث {label}...")

        self.thread = QThread()
        self.worker = ResearchWorker(query, academic)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_research_finished)
        self.worker.failed.connect(self.on_research_failed)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    @Slot(str)
    def on_research_finished(self, result: str) -> None:
        self.add_message("assistant", result)
        self.db.add_message("assistant", result)
        self.set_busy(False)

    @Slot(str)
    def on_research_failed(self, error: str) -> None:
        self.add_message("assistant", "⚠️ " + error)
        self.set_busy(False)

    def handle_agent_plan_request(self, text: str) -> bool:
        if not self.agent or not self.root:
            return False

        if text.strip() == "أوافق على الخطة" and self.pending_plan:
            permissions = ", ".join(self.pending_plan.permissions)
            self.add_message(
                "assistant",
                "تمت الموافقة على الخطة. الصلاحيات المطلوبة الآن:\n"
                f"`{permissions}`\n\n"
                "اكتب مثلاً: أوافق على قراءة مساحة العمل",
            )
            return True

        keywords = (
            "أضف", "إضافة", "عدّل", "عدل", "حسّن", "حسن", "طوّر", "طور",
            "قيّم", "قيم", "راجع", "حلل المشروع", "أرشف", "اكتب كود",
        )
        if not any(keyword in text for keyword in keywords):
            return False

        source_mode = "local"
        if "أكاديمي" in text or "أكاديمياً" in text:
            source_mode = "academic"
        elif "الويب" in text or "ويب" in text:
            source_mode = "web"
        elif "كليهما" in text or "كلاهما" in text:
            source_mode = "both"

        self.pending_plan = self.agent.plan(text, source_mode)
        self.add_message("assistant", self.pending_plan.as_text())
        return True

    def on_token(self, token: str) -> None:
        if not self.streaming_bubble:
            return
        self.streaming_text += token
        self.streaming_bubble.update_text(self.streaming_text)
        item = self.messages.item(self.messages.count() - 1)
        if item:
            item.setSizeHint(self.streaming_bubble.sizeHint())
        self.messages.scrollToBottom()

    def on_answer_finished(self, answer: str) -> None:
        if answer:
            self.db.add_message("assistant", answer)
            if getattr(self, "speak_enabled", False):
                self.speech.speak(answer)
        self.set_busy(False)

    def on_answer_failed(self, error: str) -> None:
        if self.streaming_bubble:
            self.streaming_bubble.update_text("⚠️ " + error)
        self.set_busy(False)

    def set_busy(self, busy: bool) -> None:
        self.busy = busy
        self.input.setEnabled(not busy)
        self.plus_button.setEnabled(not busy)
        self.send_button.setEnabled(not busy)
        can_voice = sd is not None and np is not None and WhisperModel is not None
        self.voice_button.setEnabled(not busy and can_voice and not self.is_recording)
        self.status_label.setText("● يفكر..." if busy else "● جاهز")

    def toggle_voice_recording(self, checked: bool) -> None:
        if checked:
            self.start_voice_recording()
        else:
            self.stop_voice_recording()

    def start_voice_recording(self) -> None:
        if self.busy:
            self.voice_button.setChecked(False)
            return
        self.is_recording = True
        self.voice_button.setText("⏹️")
        self.voice_button.setToolTip("اضغط لإيقاف التسجيل والإرسال")
        self.send_button.setEnabled(False)
        self.status_label.setText("● يسجل... اضغط ⏹️ للإيقاف")
        self.voice_thread = QThread()
        self.voice_worker = VoiceWorker()
        self.voice_worker.moveToThread(self.voice_thread)
        self.voice_thread.started.connect(self.voice_worker.run)
        self.voice_worker.finished.connect(self.on_voice_finished)
        self.voice_worker.failed.connect(self.on_voice_failed)
        self.voice_worker.finished.connect(self.voice_thread.quit)
        self.voice_worker.failed.connect(self.voice_thread.quit)
        self.voice_thread.finished.connect(self.voice_thread.deleteLater)
        self.voice_thread.start()

    def stop_voice_recording(self) -> None:
        if self.voice_worker:
            self.voice_worker.request_stop()
        self.status_label.setText("● جاري المعالجة الصوتية...")

    def on_voice_finished(self, text: str) -> None:
        self.is_recording = False
        self.voice_button.setText("🎤")
        self.voice_button.setChecked(False)
        self.voice_button.setToolTip("اضغط لبدء التسجيل، واضغط مرة أخرى للإيقاف والإرسال")
        self.send_button.setEnabled(True)
        self.status_label.setText("● جاهز")
        if text:
            self.input.setPlainText(text)
            self.input.adjust_height()
            self.set_busy(False)
            self.send_message()
        else:
            self.add_message("assistant", "لم أتعرف على كلام واضح.")
            self.set_busy(False)

    def on_voice_failed(self, error: str) -> None:
        self.is_recording = False
        self.voice_button.setText("🎤")
        self.voice_button.setChecked(False)
        self.send_button.setEnabled(True)
        self.status_label.setText("● جاهز")
        self.add_message("assistant", "⚠️ " + error)
        self.set_busy(False)

    def toggle_speech(self, enabled: bool) -> None:
        self.speak_enabled = enabled

    def choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "اختر مساحة العمل")
        if not folder:
            return
        self.root = Path(folder).resolve()
        if self.agent:
            self.agent.set_root(self.root)
        self.workspace_label.setText(str(self.root))
        self.add_message("assistant", f"تم اختيار مساحة العمل: `{self.root}`")

    def index_workspace(self) -> None:
        if not self.root:
            self.add_message("assistant", "اختر مساحة العمل أولاً.")
            return
        count = FileIndexer(self.db).index(self.root)
        self.add_message("assistant", f"تمت فهرسة **{count}** ملف بنجاح.")

    def new_chat(self) -> None:
        self.messages.clear()
        self.db.clear_history()
        self.add_message(
            "assistant",
            "بدأت محادثة جديدة. كيف أساعدك؟",
        )


STYLE = """
QWidget { font-family: "Segoe UI"; font-size: 14px; color: #e5e7eb; }
QMainWindow { background: #111827; }
#sidebar { background: #0b1220; border-left: 1px solid #1f2937; }
#brand { color: #f9fafb; font-size: 24px; font-weight: 700; padding: 8px 2px 18px; }
#header { background: #111827; border-bottom: 1px solid #1f2937; }
#pageTitle { color: #f9fafb; font-size: 20px; font-weight: 600; }
#status { color: #34d399; font-size: 13px; }
#messages { background: #111827; border: none; padding: 16px 2%; }
#messages::item { border: none; padding: 2px 0; }
#composer { background: #111827; border-top: 1px solid #1f2937; }
#chatInput { background: #1f2937; color: #f9fafb; border: 1px solid #4b5563; border-radius: 12px; padding: 10px 14px; }
#chatInput:focus { border: 1px solid #8b5cf6; }
QPushButton { background: #1f2937; color: #f3f4f6; border: 1px solid #374151; border-radius: 8px; padding: 10px 14px; }
QPushButton:hover { background: #374151; }
#plusButton { min-width: 42px; max-width: 42px; font-size: 22px; font-weight: 700; background: #374151; }
#voiceButton { min-width: 46px; max-width: 46px; font-size: 18px; background: #374151; }
#voiceButton:checked { background: #dc2626; }
#sendButton { background: #7c3aed; border: none; font-weight: 600; min-width: 100px; }
#sendButton:hover { background: #6d28d9; }
#copyButton { padding: 3px 8px; font-size: 11px; background: #374151; }
QListWidget { background: transparent; border: none; }
#bubbleTitle { color: #a78bfa; font-weight: 600; }
#userBubble { background: #312e81; color: #f9fafb; border: none; border-radius: 10px; padding: 8px; }
#assistantBubble { background: #1f2937; color: #f3f4f6; border: 1px solid #374151; border-radius: 10px; padding: 8px; }
#muted { color: #9ca3af; font-size: 12px; }
"""


def run() -> None:
    app = QApplication([])
    app.setFont(QFont("Segoe UI", 11))
    window = MainWindow()
    window.show()
    app.exec()


if __name__ == "__main__":
    run()
