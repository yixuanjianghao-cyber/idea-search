"""Download official GitHub release assets; safely unpack portable Windows apps."""
import hashlib
import os
import re
import stat
import time
import zipfile
from pathlib import Path, PureWindowsPath
from PySide6.QtCore import QObject, Signal, QSaveFile, QIODevice, QUrl, QThreadPool
from shiboken6 import isValid
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply


def safe_extract(archive, destination):
    root = Path(destination).resolve()
    with zipfile.ZipFile(archive) as bundle:
        entries = bundle.infolist()
        if len(entries) > 15000 or sum(i.file_size for i in entries) > 3 * 1024**3:
            raise ValueError('压缩包内容超出自动解压限制，请按项目说明安装。')
        for entry in entries:
            name = entry.filename.replace('\\', '/')
            target = (root / name).resolve()
            if ':' in name or PureWindowsPath(name).drive or name.startswith('/') or root not in target.parents and target != root:
                raise ValueError('压缩包中存在越界路径，已停止解压。')
            if stat.S_ISLNK(entry.external_attr >> 16): raise ValueError('压缩包中存在符号链接，已停止解压。')
        root.mkdir(parents=True, exist_ok=False)
        bundle.extractall(root)
    return root


def choose_program(root, repo_name):
    programs = [p for p in Path(root).rglob('*.exe') if not re.search(r'unins|uninstall|crash|updat|helper', p.name, re.I)]
    if len(programs) == 1: return programs[0]
    name = re.sub(r'[^a-z0-9]', '', repo_name.lower())
    matches = [p for p in programs if name and name in re.sub(r'[^a-z0-9]', '', p.stem.lower())]
    return matches[0] if len(matches) == 1 else None


class ReleaseDownload(QObject):
    progress = Signal(int, int)
    status = Signal(str)
    ready = Signal(str)
    failed = Signal(str)

    def __init__(self, asset, full_name, root, parent=None):
        super().__init__(parent)
        self.asset, self.full_name, self.root = asset, full_name, Path(root)
        self.nam = QNetworkAccessManager(self)
        self.reply = None; self.file = None; self.bytes_read = 0
        self.cancelled = False; self.hash = hashlib.sha256()

    def start(self):
        url, name = self.asset.get('url', ''), self.asset.get('name', '')
        if not re.fullmatch(r'[\w.-]+/[\w.-]+', self.full_name) or not url.startswith('https://github.com/' + self.full_name + '/releases/download/'):
            self.failed.emit('安装包地址不是这个仓库的 GitHub Release。'); return
        if not re.search(r'\.(exe|msi|zip)$', name, re.I) or Path(name).name != name or '\\' in name:
            self.failed.emit('尚不支持这个安装包格式。'); return
        folder = self.root / self.full_name.replace('/', '_') / ('release-' + hashlib.sha256(url.encode()).hexdigest()[:10])
        folder.mkdir(parents=True, exist_ok=True)
        self.path = folder / re.sub(r'[<>:"|?*]', '_', name)
        self.file = QSaveFile(str(self.path))
        if not self.file.open(QIODevice.WriteOnly): self.failed.emit('无法创建安装包文件。'); return
        request = QNetworkRequest(QUrl(url)); request.setTransferTimeout(120000)
        request.setAttribute(QNetworkRequest.RedirectPolicyAttribute, QNetworkRequest.NoLessSafeRedirectPolicy)
        self.reply = self.nam.get(request)
        self.reply.readyRead.connect(self.read)
        self.reply.downloadProgress.connect(lambda got,total: self.progress.emit(got,total))
        self.reply.finished.connect(self.finish)
        self.status.emit('正在从 GitHub Releases 下载安装包…')

    def read(self):
        if not self.reply or self.cancelled: return
        data = bytes(self.reply.readAll()); self.bytes_read += len(data)
        if self.bytes_read > 2 * 1024**3 or self.file.write(data) < 0:
            self.cancelled = True; self.reply.abort(); self.file.cancelWriting()
            self.failed.emit('下载超出限制或磁盘空间不足。'); return
        self.hash.update(data)

    def finish(self):
        if self.cancelled: return
        self.read()
        if self.cancelled: return
        try:
            if self.reply.error() != QNetworkReply.NetworkError.NoError: raise ValueError('下载失败，请检查网络或稍后重试。')
            digest = self.asset.get('digest') or ''
            if digest.startswith('sha256:') and self.hash.hexdigest().lower() != digest[7:].lower():
                raise ValueError('下载文件的校验值与 GitHub Release 不一致。')
            if not self.file.commit(): raise ValueError('安装包保存失败。')
            suffix = self.path.suffix.lower()
            if suffix == '.exe' and self.path.open('rb').read(2) != b'MZ': raise ValueError('返回内容不是 Windows 可执行文件。')
            if suffix == '.zip':
                self.status.emit('下载完成，正在解压…')
                QThreadPool.globalInstance().start(self.unpack)
            else: self.ready.emit(str(self.path))
        except Exception as exc:
            if self.file: self.file.cancelWriting()
            self.failed.emit(str(exc))
        finally:
            if self.reply: self.reply.deleteLater(); self.reply = None

    def unpack(self):
        try:
            destination = self.path.parent / ('unpacked-' + str(time.time_ns()))
            root = safe_extract(self.path, destination)
            result = str(choose_program(root, self.full_name.split('/')[-1]) or root)
            if isValid(self) and not self.cancelled: self.ready.emit(result)
        except Exception as exc:
            if isValid(self) and not self.cancelled: self.failed.emit(str(exc))

    def stop(self):
        self.cancelled = True
        if self.reply: self.reply.blockSignals(True); self.reply.abort(); self.reply.deleteLater(); self.reply = None
        if self.file: self.file.cancelWriting()
