"""Per-user single instance with activation of the existing window."""
import hashlib
import os
from pathlib import Path
from PySide6.QtCore import QLockFile, QIODevice
from PySide6.QtNetwork import QLocalServer, QLocalSocket


class SingleInstance:
    def __init__(self):
        root = Path(os.environ.get('GHF_DATA_DIR') or os.environ.get('LOCALAPPDATA') or Path.home()) / 'IdeaSearch'
        root.mkdir(parents=True, exist_ok=True)
        self.name = 'idea-search-' + hashlib.sha256(str(root).encode()).hexdigest()[:16]
        self.lock = QLockFile(str(root / 'app.lock'))
        self.server = None

    def acquire(self):
        if self.lock.tryLock(0):
            QLocalServer.removeServer(self.name)
            self.server = QLocalServer()
            return self.server.listen(self.name)
        sock = QLocalSocket()
        sock.connectToServer(self.name, QIODevice.WriteOnly)
        if sock.waitForConnected(1000):
            sock.write(b'activate')
            sock.waitForBytesWritten(500)
            sock.disconnectFromServer()
        return False

    def connect(self, window):
        def activate():
            while self.server.hasPendingConnections():
                socket = self.server.nextPendingConnection()
                socket.close()
                socket.deleteLater()
            window.showNormal()
            window.raise_()
            window.activateWindow()
        self.server.newConnection.connect(activate)

    def close(self):
        if self.server:
            self.server.close()
        self.lock.unlock()
