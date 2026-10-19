"""Qt desktop shell. Model calls run off the UI thread through Qt signals."""
import json
import sys
import html
from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal, Qt, QRectF
from PyQt5.QtGui import QPixmap, QPainter, QColor, QPen
from PyQt5.QtWidgets import (QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton, QLineEdit,
    QSpinBox, QSplitter, QTabWidget, QTextEdit, QTextBrowser, QScrollArea, QVBoxLayout, QWidget, QListWidget)

from .agent import Agent
from .config import Settings, WORKSPACES, data_directory, load_environment, profile_name
from .presentation import render_markdown
from .documents import extract_text
from .store import Store


def chart_pixmap(spec):
    """Draw validated chart data locally; no plotting service or model-generated code."""
    from .integrations import validate_chart
    validate_chart(spec)
    values, labels = spec['values'], spec['labels']
    height = max(340, len(values) * 32 + 70)
    pixmap = QPixmap(800, height)
    pixmap.fill(QColor('#f6f5ef'))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    colors = ['#416f55', '#9eaa50', '#5f8f99', '#be8351', '#8c6c9d', '#d4b45b']
    painter.setPen(QColor('#193b32'))
    painter.drawText(20, 24, spec.get('unit') or 'Value')
    low, high = min(0, *values), max(0, *values)
    span = high - low or 1
    if spec['type'] == 'pie':
        start, total = 0, sum(values)
        for i, (label, value) in enumerate(zip(labels, values)):
            angle = round(value / total * 5760)
            painter.setBrush(QColor(colors[i % len(colors)]))
            painter.setPen(Qt.NoPen)
            painter.drawPie(QRectF(30, 50, 240, 240), start, angle)
            start += angle
            painter.setPen(QColor('#193b32'))
            painter.drawText(300, 60 + i * 28, f'{label[:36]}: {value:g} ({value / total:.1%})')
    elif spec['type'] == 'bar':
        zero = 200 + (0 - low) / span * 470
        for i, (label, value) in enumerate(zip(labels, values)):
            x, y = 200 + (value - low) / span * 470, 45 + i * 32
            painter.setPen(QColor('#193b32'))
            painter.drawText(15, y + 17, label[:26])
            painter.fillRect(QRectF(min(zero, x), y, max(1, abs(x - zero)), 22), QColor(colors[i % len(colors)]))
            painter.drawText(690, y + 17, f'{value:g}')
    else:
        points = [(70 + i / max(1, len(values) - 1) * 650, 260 - (value - low) / span * 210) for i, value in enumerate(values)]
        painter.setPen(QPen(QColor(colors[0]), 3))
        for i, (x, y) in enumerate(points):
            if i:
                painter.drawLine(round(points[i - 1][0]), round(points[i - 1][1]), round(x), round(y))
            painter.setBrush(QColor(colors[0]))
            painter.drawEllipse(QRectF(x - 4, y - 4, 8, 8))
            painter.setPen(QColor('#193b32'))
            painter.drawText(round(x - 12), round(y - 10), f'{values[i]:g}')
            if len(labels) <= 12 or i % max(1, len(labels) // 8) == 0:
                painter.drawText(round(x - 15), 285, labels[i][:12])
            painter.setPen(QPen(QColor(colors[0]), 3))
    painter.end()
    return pixmap


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
        self.transcript = QTextBrowser()
        self.transcript.setOpenExternalLinks(True)
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
        export.clicked.connect(lambda: self.save_text("\n\n".join("## " + m['role'].title() + "\n\n" + m['content'] for m in self.transcript_turns)))
        actions.addWidget(export)
        chat_layout.addLayout(actions)
        tabs.addTab(chat, "Conversation")
        self.evidence = QTextEdit()
        self.evidence.setReadOnly(True)
        tabs.addTab(self.evidence, "Sources & tool activity")
        self.visuals = QVBoxLayout()
        media = QWidget()
        media.setLayout(self.visuals)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(media)
        tabs.addTab(scroll, "Charts & images")
        drafts_page = QWidget()
        draft_layout = QVBoxLayout(drafts_page)
        self.draft_list = QListWidget()
        self.draft_list.currentRowChanged.connect(self.show_draft)
        draft_layout.addWidget(self.draft_list)
        self.draft_text = QTextEdit()
        self.draft_text.setReadOnly(True)
        draft_layout.addWidget(self.draft_text)
        export_draft = QPushButton("Export selected draft")
        export_draft.clicked.connect(lambda: self.save_text(self.draft_data[self.draft_list.currentRow()]["content"] if self.draft_list.currentRow() >= 0 else ""))
        draft_layout.addWidget(export_draft)
        tabs.addTab(drafts_page, "Drafts")
        settings_page = QWidget()
        form = QFormLayout(settings_page)
        self.model = QLineEdit()
        form.addRow("Model ID", self.model)
        self.display_name = QLineEdit()
        self.display_name.setPlaceholderText("Use Username from .env when blank")
        form.addRow("Your name", self.display_name)
        self.personalize = QCheckBox("Use and remember my name")
        self.allow_web = QCheckBox("Allow public web searches")
        self.allow_images = QCheckBox("Allow image generation")
        for control in (self.personalize, self.allow_web, self.allow_images):
            form.addRow(control)
        self.image_model = QLineEdit()
        form.addRow("Image model", self.image_model)
        self.voice_language = QComboBox()
        self.voice_language.addItems(["en-IN", "en-US", "hi-IN", "ar-SA"])
        form.addRow("Voice language", self.voice_language)
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
        self.instructions.setMaximumHeight(120)
        self.instructions.setPlaceholderText("Optional preferences for this workspace")
        form.addRow("Instructions", self.instructions)
        reset = QPushButton("Reset to defaults")
        reset.clicked.connect(lambda: self.populate(Settings()))
        form.addRow(reset)
        form.addRow(QLabel("Keys stay in .env. Images need HuggingFaceAPIKey.\nVoice and local app controls: python legacy_main.py. Browser voice is available in the web version."))
        settings_scroll = QScrollArea()
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setWidget(settings_page)
        tabs.addTab(settings_scroll, "Profile & settings")
        splitter.addWidget(tabs)
        splitter.setSizes([250, 850])
        layout.addWidget(splitter)
        self.setCentralWidget(root)
        self.populate(Settings.parse(store.settings(self.session)))
        self.refresh()

    def populate(self, settings):
        self.workspace.setCurrentText(settings.workspace)
        self.model.setText(settings.model)
        self.display_name.setText(settings.display_name)
        self.personalize.setChecked(settings.personalize)
        self.allow_web.setChecked(settings.allow_web)
        self.allow_images.setChecked(settings.allow_images)
        self.image_model.setText(settings.image_model)
        self.voice_language.setCurrentText(settings.voice_language)
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
            instructions=self.instructions.toPlainText(), display_name=self.display_name.text().strip(),
            personalize=self.personalize.isChecked(), allow_web=self.allow_web.isChecked(), allow_images=self.allow_images.isChecked(),
            image_model=self.image_model.text().strip(), voice_language=self.voice_language.currentText())).to_dict()

    def refresh(self):
        name = profile_name(Settings.parse(self.store.settings(self.session)))
        self.setWindowTitle("Sage · " + (name or "AI workspace"))
        history = self.store.history(self.session, rich=True)
        self.transcript_turns = list(history)
        css = "<style>body{line-height:1.6}th,td{padding:9px;border:1px solid #557065}th{background:#254c41}pre{background:#192c29}a{color:#a8d4b0}</style>"
        self.transcript.setHtml(css + "<hr>".join(
            "<h4>" + ("YOU" if m['role'] == 'user' else 'SAGE') + "</h4>" +
            ("<p>" + html.escape(m['content']).replace("\n", "<br>") + "</p>" if m['role'] == 'user' else render_markdown(m['content']))
            + "".join('<p><a href="' + html.escape(action['url'], quote=True) + '">' + html.escape(action['title']) + '</a></p>' for action in m.get('metadata', {}).get('actions', []))
            for m in history))
        self.transcript.moveCursor(self.transcript.textCursor().End)
        latest = next((m['metadata'] for m in reversed(history) if m['role'] == 'assistant'), {})
        self.evidence.setPlainText(json.dumps(latest, ensure_ascii=False, indent=2))
        self.show_assets()
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
        self.transcript.append("<h4>YOU</h4><p>" + html.escape(question).replace("\n", "<br>") + "</p>")
        self.transcript_turns.append({'role':'user', 'content':question})
        self.input.clear()
        self.send.setEnabled(False)
        self.status.setText("Working…")
        self.worker = Task(lambda: self.agent.respond(self.session, question, settings), self)
        self.worker.succeeded.connect(self.answered)
        self.worker.failed.connect(self.failed)
        self.worker.finished.connect(lambda: self.send.setEnabled(True))
        self.worker.start()

    def answered(self, response):
        if self.remember.isChecked():
            self.refresh()
        else:
            self.transcript_turns.append({'role':'assistant', 'content':response['answer']})
            self.transcript.append("<h4>SAGE</h4>" + render_markdown(response["answer"]))
            self.evidence.setPlainText(json.dumps(response, ensure_ascii=False, indent=2))
            self.show_assets()
            self.draft_data = self.store.drafts(self.session)
            self.draft_list.clear()
            self.draft_list.addItems([d["title"] for d in self.draft_data])
        self.display_name.setText(Settings.parse(self.store.settings(self.session)).display_name)
        self.status.setText("Ready · " + response["mode"])

    def failed(self, message):
        self.status.setText("Request failed; you can retry")
        self.transcript.append("<p>" + html.escape(message) + "</p>")

    def show_draft(self, index):
        self.draft_text.setHtml(render_markdown(self.draft_data[index]["content"]) if index >= 0 else "")

    def show_assets(self):
        while self.visuals.count():
            item = self.visuals.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        assets = self.store.assets(self.session)
        if not assets:
            self.visuals.addWidget(QLabel("Ask Sage for a bar, line, or pie chart using your data, or generate an image."))
        for asset in assets:
            title = QLabel(asset["title"])
            title.setTextFormat(Qt.PlainText)
            title.setWordWrap(True)
            self.visuals.addWidget(title)
            pixmap = QPixmap()
            if asset["kind"] == "image":
                pixmap.loadFromData(self.store.asset(self.session, asset["id"])["payload"], "PNG")
            else:
                pixmap = chart_pixmap(asset["spec"])
            if not pixmap.isNull():
                image = QLabel()
                image.setPixmap(pixmap.scaledToWidth(760, Qt.SmoothTransformation))
                self.visuals.addWidget(image)
            export = QPushButton("Export PNG")
            export.clicked.connect(lambda checked=False, image=pixmap: self.save_image(image))
            self.visuals.addWidget(export)
            if asset["kind"] == "chart":
                spec = asset["spec"]
                data = QTextBrowser()
                data.setMaximumHeight(190)
                data.setHtml(render_markdown("| Label | " + spec.get("unit", "Value") + " |\n|---|---|\n" + "\n".join(
                    "| " + label.replace("|", "\\|") + " | " + str(value) + " |" for label, value in zip(spec['labels'], spec['values']))))
                self.visuals.addWidget(data)
        self.visuals.addStretch()

    def save_image(self, pixmap):
        path, _ = QFileDialog.getSaveFileName(self, "Export visual", "sage-visual.png", "PNG (*.png)")
        if path and not pixmap.save(path, "PNG"):
            QMessageBox.warning(self, "Export failed", "Could not save this image.")

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
