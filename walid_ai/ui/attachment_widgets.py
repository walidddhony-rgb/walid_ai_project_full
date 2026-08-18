from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class AutoGrowTextEdit(QTextEdit):
    height_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(False)
        self.setMinimumHeight(46)
        self.setMaximumHeight(180)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setPlaceholderText("اكتب رسالتك...")
        self.textChanged.connect(self.adjust_height)
        self.adjust_height()

    def adjust_height(self) -> None:
        document_height = self.document().size().height()
        height = max(46, min(int(document_height + 24), 180))
        self.setFixedHeight(height)
        self.height_changed.emit(height)


class AttachmentPanel(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.paths: list[Path] = []
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.file_list = QListWidget()
        self.file_list.setMaximumHeight(100)
        self.file_list.setVisible(False)
        self.layout.addWidget(self.file_list)

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
        remove_button = QPushButton("×")
        remove_button.setToolTip(f"إزالة {path.name}")
        remove_button.clicked.connect(lambda: self.remove(path))
        self.file_list.addItem(item)
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