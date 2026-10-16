"""Qt desktop shell. Model calls run off the UI thread through Qt signals."""
import json
import sys
from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import (QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton, QLineEdit,
    QSpinBox, QSplitter, QTabWidget, QTextEdit, QVBoxLayout, QWidget, QListWidget)

from .agent import Agent
from .config import Settings, WORKSPACES, data_directory, load_environment
from .documents import extract_text
from .store import Store


class Task(QThread):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, function, parent):
        super().__init__(parent)
        self.function = function

    def run(self):
        try:
            self.succeeded.emit(self.function())
        except Exception as exc:
            self.failed.emit(str(exc))


class Window(QMainWindow):
    def __init__(self, store):
        super().__init__()
        self.store = store
        marker = data_directory() / "desktop-session.txt"
        self.session = store.session(marker.read_text().strip() if marker.exists() else None)
        marker.write_text(self.session)
        self.agent = Agent(store)
        self.worker = None
        self.setWindowTitle("Sage · AI workspace")
        self.resize(1180, 800)
        self.setStyleSheet("""
            QWidget {background:#101c1b;color:#e5eeeb;font-size:14px;}
            QTextEdit,QLineEdit,QListWidget,QComboBox,QSpinBox,QDoubleSpinBox {background:#192c29;border:1px solid #35514b;border-radius:6px;padding:8px;}
            QPushButton {background:#254c41;border:1px solid #426858;border-radius:7px;padding:10px;}
            QPushButton:hover {background:#346450;} QPushButton:disabled {color:#789086;}
            QTabBar::tab {padding:12px;background:#192c29;} QTabBar::tab:selected {background:#355b4d;}
        """)
        root = QWidget()
        layout = QVBoxLayout(root)
        title = QLabel("SAGE   /   Your ideas, connected")
        title.setStyleSheet("font-size:25px;font-weight:600;padding:12px;")
        layout.addWidget(title)
        self.status = QLabel("Connected model ready" if self.agent.provider.available else "Local search ready · configure SAGE_API_KEY for AI")
        layout.addWidget(self.status)
        splitter = QSplitter()
        left = QWidget()
        panel = QVBoxLayout(left)
        panel.addWidget(QLabel("Workspace"))
        self.workspace = QComboBox()
        self.workspace.addItems(list(WORKSPACES))
        panel.addWidget(self.workspace)
        panel.addWidget(QLabel("Your documents"))
        self.documents = QListWidget()
        panel.addWidget(self.documents)
        for label, callback in [("+ Add document", self.upload), ("Remove selected", self.remove_document), ("Clear conversation", self.clear)]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            panel.addWidget(button)
        splitter.addWidget(left)
        tabs = QTabWidget()
        chat = QWidget()
        chat_layout = QVBoxLayout(chat)
        self.transcript = QTextEdit()
        self.transcript.setReadOnly(True)
        chat_layout.addWidget(self.transcript)
        self.input = QTextEdit()
        self.input.setMaximumHeight(100)
        self.input.setPlaceholderText("Ask a question, compare documents, or draft something…")
        chat_layout.addWidget(self.input)
        actions = QHBoxLayout()
        self.send = QPushButton("Send →")
        self.send.clicked.connect(self.ask)
        actions.addWidget(self.send)
        export = QPushButton("Export conversation")
        export.clicked.connect(lambda: self.save_text(self.transcript.toPlainText()))
        actions.addWidget(export)
        chat_layout.addLayout(actions)
        tabs.addTab(chat, "Conversation")
        self.evidence = QTextEdit()
        self.evidence.setReadOnly(True)
        tabs.addTab(self.evidence, "Sources & tool activity")
        drafts_page = QWidget()
        draft_layout = QVBoxLayout(drafts_page)
        self.draft_list = QListWidget()
        self.draft_list.currentRowChanged.connect(self.show_draft)
        draft_layout.addWidget(self.draft_list)
        self.draft_text = QTextEdit()
        self.draft_text.setReadOnly(True)
        draft_layout.addWidget(self.draft_text)
        export_draft = QPushButton("Export selected draft")
        export_draft.clicked.connect(lambda: self.save_text(self.draft_text.toPlainText()))
        draft_layout.addWidget(export_draft)
        tabs.addTab(drafts_page, "Drafts")
        settings_page = QWidget()
        form = QFormLayout(settings_page)
        self.model = QLineEdit()
        form.addRow("Model ID", self.model)
        self.temperature = QDoubleSpinBox()
        self.temperature.setRange(0, 1)
        self.temperature.setSingleStep(0.1)
        form.addRow("Creativity", self.temperature)
        self.max_tokens = QSpinBox()
        self.max_tokens.setRange(128, 4096)
        form.addRow("Response token limit", self.max_tokens)
        self.steps = QSpinBox()
        self.steps.setRange(1, 6)
        form.addRow("Maximum model rounds", self.steps)
        self.k = QSpinBox()
        self.k.setRange(1, 8)
        form.addRow("Source passages", self.k)
        self.remember = QCheckBox("Save and use conversation history")
        form.addRow(self.remember)
        self.allow_drafts = QCheckBox("Allow AI to save reviewable drafts")
        form.addRow(self.allow_drafts)
        self.instructions = QTextEdit()
        self.instructions.setPlaceholderText("Optional preferences for this workspace")
        form.addRow("Instructions", self.instructions)
        reset = QPushButton("Reset to defaults")
        reset.clicked.connect(lambda: self.populate(Settings()))
        form.addRow(reset)
        form.addRow(QLabel("Keys stay in .env. Relevant document passages go to your configured model.\nLegacy voice, image, and app controls: python legacy_main.py."))
        tabs.addTab(settings_page, "Advanced settings")
        splitter.addWidget(tabs)
        splitter.setSizes([250, 850])
        layout.addWidget(splitter)
        self.setCentralWidget(root)
        self.populate(Settings.parse(store.settings(self.session)))
        self.refresh()

    def populate(self, settings):
        self.workspace.setCurrentText(settings.workspace)
        self.model.setText(settings.model)
        self.temperature.setValue(settings.temperature)
        self.max_tokens.setValue(settings.max_tokens)
        self.steps.setValue(settings.max_steps)
        self.k.setValue(settings.retrieval_k)
        self.remember.setChecked(settings.remember)
        self.allow_drafts.setChecked(settings.allow_drafts)
        self.instructions.setPlainText(settings.instructions)

    def settings(self):
        return Settings.parse(dict(workspace=self.workspace.currentText(), model=self.model.text().strip(),
            temperature=self.temperature.value(), max_tokens=self.max_tokens.value(), max_steps=self.steps.value(),
            retrieval_k=self.k.value(), remember=self.remember.isChecked(), allow_drafts=self.allow_drafts.isChecked(),
            instructions=self.instructions.toPlainText())).to_dict()

    def refresh(self):
        self.transcript.setPlainText("\n\n".join(f"{m['role'].upper()}\n{m['content']}" for m in self.store.history(self.session)))
        self.doc_data = self.store.documents(self.session)
        self.documents.clear()
        self.documents.addItems([d["name"] for d in self.doc_data])
        self.draft_data = self.store.drafts(self.session)
        self.draft_list.clear()
        self.draft_list.addItems([d["title"] for d in self.draft_data])

    def upload(self):
        path, _ = QFileDialog.getOpenFileName(self, "Add document", "", "Documents (*.txt *.md *.pdf *.csv *.json *.py)")
        if path:
            try:
                file = Path(path)
                if file.stat().st_size > 5_000_000:
                    raise ValueError("File limit is 5 MB")
                self.store.add_document(self.session, file.name, extract_text(file.name, file.read_bytes()))
                self.refresh()
            except Exception as exc:
                QMessageBox.warning(self, "Import failed", str(exc))

    def remove_document(self):
        index = self.documents.currentRow()
        if index >= 0:
            self.store.remove_document(self.session, self.doc_data[index]["id"])
            self.refresh()

    def clear(self):
        if not self.worker or not self.worker.isRunning():
            self.store.clear_history(self.session)
            self.refresh()

    def ask(self):
        question = self.input.toPlainText().strip()
        if not question or self.worker and self.worker.isRunning():
            return
        try:
            settings = self.settings()
            self.store.save_settings(self.session, settings)
        except ValueError as exc:
            QMessageBox.warning(self, "Settings", str(exc))
            return
        self.transcript.append("\nYOU\n" + question)
        self.input.clear()
        self.send.setEnabled(False)
        self.status.setText("Working…")
        self.worker = Task(lambda: self.agent.respond(self.session, question, settings), self)
        self.worker.succeeded.connect(self.answered)
        self.worker.failed.connect(self.failed)
        self.worker.finished.connect(lambda: self.send.setEnabled(True))
        self.worker.start()

    def answered(self, response):
        self.transcript.append("\nSAGE\n" + response["answer"])
        self.evidence.setPlainText(json.dumps({"sources": response["sources"], "steps": response["steps"]}, ensure_ascii=False, indent=2))
        self.draft_data = self.store.drafts(self.session)
        self.draft_list.clear()
        self.draft_list.addItems([d["title"] for d in self.draft_data])
        self.status.setText("Ready · " + response["mode"])

    def failed(self, message):
        self.status.setText("Request failed; you can retry")
        self.transcript.append("\n" + message)

    def show_draft(self, index):
        self.draft_text.setPlainText(self.draft_data[index]["content"] if index >= 0 else "")

    def save_text(self, content):
        path, _ = QFileDialog.getSaveFileName(self, "Export", "sage-export.md", "Markdown (*.md);;Text (*.txt)")
        if path:
            try:
                Path(path).write_text(content, encoding="utf-8")
            except OSError as exc:
                QMessageBox.warning(self, "Export failed", str(exc))

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "Sage is working", "Wait for the current request to finish before closing.")
            event.ignore()
        else:
            try:
                self.store.save_settings(self.session, self.settings())
            except ValueError:
                pass
            event.accept()


def main():
    load_environment()
    app = QApplication(sys.argv)
    window = Window(Store(data_directory() / "sage.db"))
    window.show()
    sys.exit(app.exec_())
