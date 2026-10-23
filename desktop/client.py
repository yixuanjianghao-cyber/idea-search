"""Event-driven SSE with immediate socket cancellation."""
from __future__ import annotations
import json
from PySide6.QtCore import QObject, Signal, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

class StreamWorker(QObject):
    event = Signal(dict)
    failed = Signal(str)
    finished_ok = Signal()

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.url = url
        self.manager = QNetworkAccessManager(self)
        self.reply = None
        self.buffer = b""
        self._running = False
        self._stop = False
        self._terminal = False

    def isRunning(self):
        return self._running

    def start(self):
        self._running = True
        req = QNetworkRequest(QUrl(self.url))
        req.setRawHeader(b"Accept", b"text/event-stream")
        req.setTransferTimeout(95000)
        self.reply = self.manager.get(req)
        self.reply.readyRead.connect(self._read)
        self.reply.finished.connect(self._finish)

    def stop(self):
        self._stop = True
        self._running = False
        if self.reply:
            self.reply.abort()

    def _read(self):
        if not self.reply or self._stop:
            return
        self.buffer += bytes(self.reply.readAll())
        self.buffer = self.buffer.replace(b"\r\n", b"\n")
        while b"\n\n" in self.buffer:
            block, self.buffer = self.buffer.split(b"\n\n", 1)
            lines = [line[5:].lstrip() for line in block.split(b"\n") if line.startswith(b"data:")]
            if not lines:
                continue
            try:
                payload = json.loads(b"\n".join(lines))
            except (ValueError, UnicodeDecodeError):
                continue
            if payload.get("type") in ("done", "error"):
                self._terminal = True
            self.event.emit(payload)

    def _finish(self):
        self._read()
        self._running = False
        if not self._stop and not self._terminal:
            self.failed.emit(self.reply.errorString() if self.reply and self.reply.error() != QNetworkReply.NetworkError.NoError else "连接结束，未收到完整结果")
        if self.reply:
            self.reply.deleteLater()
            self.reply = None
        self.finished_ok.emit()
