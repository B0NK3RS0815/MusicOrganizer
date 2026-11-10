"""Hintergrund-Threads, damit die Oberfläche bei großen Archiven flüssig bleibt."""
import threading
import traceback

from PySide6.QtCore import QThread, Signal

from mog.core import scanner


class ScanThread(QThread):
    status = Signal(str)
    progress = Signal(int, int)
    batch = Signal(list)
    done = Signal(object)

    def __init__(self, sources, db_path, force=False, skip_hidden=True, parent=None):
        super().__init__(parent)
        self.sources = list(sources)
        self.db_path = db_path
        self.force = force
        self.skip_hidden = skip_hidden
        self.cancel_event = threading.Event()

    def cancel(self):
        self.cancel_event.set()

    def run(self):
        try:
            res = scanner.scan(self.sources, self.db_path,
                               progress=self.progress.emit, batch=self.batch.emit,
                               status=self.status.emit, cancel=self.cancel_event,
                               force=self.force, skip_hidden=self.skip_hidden)
        except Exception as e:  # pragma: no cover
            res = scanner.ScanResult()
            res.errors.append(("", f"{type(e).__name__}: {e}"))
        self.done.emit(res)


class TaskThread(QThread):
    """Führt fn(progress, cancel) im Hintergrund aus.

    progress(done, total, text="") darf aus fn aufgerufen werden.
    """
    progress = Signal(int, int, str)
    item_done = Signal(object)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn
        self.cancel_event = threading.Event()

    def cancel(self):
        self.cancel_event.set()

    def _progress(self, done, total, text=""):
        self.progress.emit(int(done), int(total), str(text))

    def run(self):
        try:
            res = self.fn(self._progress, self.cancel_event, self.item_done.emit)
            self.done.emit(res)
        except Exception as e:
            traceback.print_exc()
            self.failed.emit(f"{type(e).__name__}: {e}")
