import importlib.util
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


@unittest.skipUnless(importlib.util.find_spec("PyQt5"), "Install requirements-desktop.txt for Qt checks")
class DesktopTests(unittest.TestCase):
    def test_window_and_background_request(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtWidgets import QApplication
        from sage.desktop import Window, chart_pixmap
        from sage.store import Store
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as directory:
            with patch.dict(os.environ, {"SAGE_DATA_DIR": directory}):
                window = Window(Store(Path(directory) / "db.sqlite"))
                window.display_name.setText('Test Reader')
                window.allow_web.setChecked(False)
                self.assertFalse(window.settings()['allow_web'])
                for kind in ('bar', 'line', 'pie'):
                    self.assertFalse(chart_pixmap(dict(title='Budget', type=kind, labels=['A', 'B'], values=[10, 20])).isNull())
                window.agent.provider = type("Offline", (), {"available": False})()
                window.show()
                window.input.setPlainText("Hello")
                window.ask()
                deadline = time.monotonic() + 10
                while not window.send.isEnabled() and time.monotonic() < deadline:
                    app.processEvents()
                    time.sleep(0.01)
                self.assertTrue(window.send.isEnabled())
                self.assertIn("Local document search", window.transcript.toPlainText())
                window.worker.wait(1000)
                window.close()


if __name__ == "__main__":
    unittest.main()
