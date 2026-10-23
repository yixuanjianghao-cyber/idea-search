"""Generate our native app icon without third-party artwork."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage, QPainter, QPen, QColor
from PySide6.QtCore import Qt

app = QApplication([])
image = QImage(256, 256, QImage.Format_ARGB32)
image.fill(Qt.transparent)
p = QPainter(image)
p.setRenderHint(QPainter.Antialiasing)
p.setPen(Qt.NoPen)
p.setBrush(QColor('#102033'))
p.drawRoundedRect(4, 4, 248, 248, 54, 54)
p.setPen(QPen(QColor('#56d98b'), 19, Qt.SolidLine, Qt.RoundCap))
p.setBrush(Qt.NoBrush)
p.drawEllipse(59, 53, 108, 108)
p.drawLine(151, 148, 200, 198)
p.setPen(QPen(QColor('#d8fbe7'), 10, Qt.SolidLine, Qt.RoundCap))
p.drawLine(85, 107, 102, 124)
p.drawLine(102, 124, 137, 89)
p.end()
root = Path(__file__).resolve().parent.parent / 'assets'
root.mkdir(exist_ok=True)
if not image.save(str(root / 'app.ico')): raise RuntimeError('ICO encoding unavailable')
image.save(str(root / 'app.png'))
