"""Local Ollama connection settings; no cloud account or remote key required."""
import json
import os
import shutil
import subprocess
from PySide6.QtCore import QTimer, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QComboBox, QPushButton, QHBoxLayout, QLineEdit, QCheckBox
from ai_config import load_api_key, save_api_key, api_error

OLLAMA = 'http://127.0.0.1:11434'
PREFERRED = ['huihui_ai/qwen3-abliterated:4b', 'huihui_ai/qwen3-abliterated:1.7b', 'huihui_ai/qwen3-abliterated:8b', 'qwen2.5:0.5b']


def select_model(names, selected=''):
    return selected if selected in names else next((m for m in PREFERRED if m in names), names[0] if names else None)


class AISettings(QDialog):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store, self.reply = store, None
        self.setWindowTitle('AI 设置 · 与 GitHub Token 分开配置'); self.setMinimumWidth(530)
        layout = QVBoxLayout(self)
        description = QLabel('GitHub Token 用于搜索仓库；这里的 API Key 用于 AI 问答与中文简介。')
        description.setWordWrap(True); layout.addWidget(description)
        self.provider = QComboBox(); self.provider.addItem('本机 Ollama', 'ollama'); self.provider.addItem('DeepSeek API', 'deepseek')
        self.provider.setCurrentIndex(1 if store.get('ai_provider') == 'deepseek' else 0); layout.addWidget(self.provider)
        self.base = QLineEdit(store.get('ai_base_url') or 'https://api.deepseek.com'); self.base.setPlaceholderText('基础地址，例如 https://api.deepseek.com'); layout.addWidget(self.base)
        self.key = QLineEdit(); self.key.setEchoMode(QLineEdit.Password)
        self.key.setPlaceholderText('输入 DeepSeek API Key（sk-…）；留空保留已有密钥'); layout.addWidget(self.key)
        self.key_note = QLabel('已读取到 API Key，留空可继续使用。' if load_api_key() else '尚未配置 DeepSeek Key。'); layout.addWidget(self.key_note)
        cloud_controls = QHBoxLayout()
        get_key = QPushButton('获取 DeepSeek API Key'); get_key.clicked.connect(lambda: QDesktopServices.openUrl(QUrl('https://platform.deepseek.com/api_keys'))); cloud_controls.addWidget(get_key)
        clear_key = QPushButton('清除 AI Key'); clear_key.clicked.connect(self.clear_key); cloud_controls.addWidget(clear_key); layout.addLayout(cloud_controls)
        self.status = QLabel('正在检测连接…'); self.status.setWordWrap(True); layout.addWidget(self.status)
        self.models = QComboBox(); layout.addWidget(self.models)
        controls = QHBoxLayout()
        self.start_button = QPushButton('启动本机 AI'); self.start_button.clicked.connect(self.start_service); controls.addWidget(self.start_button)
        retry = QPushButton('测试连接 / 读取模型'); retry.clicked.connect(self.detect); controls.addWidget(retry)
        layout.addLayout(controls)
        note = QLabel('本机模型只在电脑上运行。选择 DeepSeek 后，问题与仓库公开资料会发到 DeepSeek；中文简述也会产生 API 用量。')
        note.setWordWrap(True); layout.addWidget(note)
        self.auto_intro = QCheckBox('自动为英文卡片生成 AI 中文简介'); self.auto_intro.setChecked(store.get('auto_introductions', True)); layout.addWidget(self.auto_intro)
        self.save_button = QPushButton('保存 AI 配置'); self.save_button.setObjectName('go'); self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.save); layout.addWidget(self.save_button)
        self.nam = QNetworkAccessManager(self)
        self.provider.currentIndexChanged.connect(self.provider_changed)
        self.provider_changed()

    def provider_changed(self):
        if self.reply is not None:
            previous=self.reply; self.reply=None; previous.abort()
        cloud = self.provider.currentData() == 'deepseek'
        self.base.setVisible(cloud); self.key.setVisible(cloud); self.key_note.setVisible(cloud)
        self.start_button.setVisible(not cloud); self.models.setEditable(cloud)
        self.models.clear()
        if cloud:
            self.models.addItem(self.store.get('ai_cloud_model') or 'deepseek-flash')
            self.status.setText('填入 DeepSeek Key 后点「测试连接」，再保存配置。'); self.save_button.setEnabled(True)
        else: self.detect()

    def detect(self):
        if self.reply: return
        cloud = self.provider.currentData() == 'deepseek'
        if cloud:
            from ai_config import cloud_config
            try: settings = cloud_config({'ai_provider':'deepseek','ai_base_url':self.base.text().strip()})
            except ValueError as exc: self.status.setText(str(exc)); return
            key = self.key.text().strip() or load_api_key()
            if not key: self.status.setText('请先填入 DeepSeek API Key。'); return
            request = QNetworkRequest(QUrl(settings['base_url'] + '/models'))
            request.setRawHeader(b'Authorization', ('Bearer ' + key).encode())
        else: request = QNetworkRequest(QUrl(OLLAMA + '/api/tags'))
        request.setTransferTimeout(12000 if cloud else 3000)
        reply = self.nam.get(request); self.reply = reply
        def finished():
            if self.reply is not reply:
                reply.deleteLater(); return
            try:
                data = json.loads(bytes(reply.readAll()))
                status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute) or 0
                if status >= 400: raise ValueError(api_error(status))
                names = [m['id'] for m in data.get('data', [])] if cloud else [m['name'] for m in data.get('models', [])]
                self.models.clear(); self.models.addItems(names)
                selected = (self.store.get('ai_cloud_model') if self.store.get('ai_cloud_model') in names else ('deepseek-flash' if 'deepseek-flash' in names else (names[0] if names else None))) if cloud else select_model(names, self.store.get('ai_model', ''))
                if selected: self.models.setCurrentText(selected)
                self.save_button.setEnabled(bool(selected)); self.start_button.setEnabled(not bool(selected))
                self.status.setText((f'DeepSeek 认证成功 · {len(names)} 个可用模型' if cloud else f'已连接 · {len(names)} 个已安装模型') if names else '连接成功，但没有读取到可用模型。')
            except Exception as exc:
                self.status.setText(str(exc) if cloud and isinstance(exc, ValueError) and not isinstance(exc, json.JSONDecodeError) else ('DeepSeek 连接失败，请检查网络和基础地址。' if cloud else '尚未连接本机 Ollama。已安装时可点击下方按钮启动。'))
                self.start_button.setEnabled(True)
            finally: self.reply = None; reply.deleteLater()
        reply.finished.connect(finished)

    def start_service(self):
        executable = shutil.which('ollama')
        if not executable:
            self.status.setText('未找到 Ollama。安装并运行后，点击「重新检测」。'); return
        try:
            subprocess.Popen([executable, 'serve'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            self.status.setText('正在启动本机服务，它会在后台运行…')
            QTimer.singleShot(900, self.detect)
        except OSError as exc: self.status.setText('启动失败：' + str(exc))

    def save(self):
        from ui import save_store
        provider = self.provider.currentData()
        if provider == 'deepseek':
            from ai_config import cloud_config
            try:
                cloud_config({'ai_provider':'deepseek','ai_base_url':self.base.text().strip()})
                key = self.key.text().strip()
                if key.startswith(('ghp_', 'github_pat_')): raise ValueError('这是 GitHub Token，请在 GitHub 设置中填写；这里需要 DeepSeek API Key。')
                if key: save_api_key(key)
                if not load_api_key(): raise ValueError('请先填写 DeepSeek API Key。')
            except Exception as exc: self.status.setText('保存失败：' + str(exc)); return
            self.store['ai_base_url'] = self.base.text().strip(); self.store['ai_cloud_model'] = self.models.currentText().strip()
        else: self.store['ai_model'] = self.models.currentText()
        self.store['ai_provider'] = provider
        self.store['auto_introductions'] = self.auto_intro.isChecked()
        save_store(self.store); self.accept()

    def clear_key(self):
        save_api_key(''); self.key.clear(); self.key_note.setText('文件中的 AI Key 已清除；系统环境变量仍有密钥。' if os.environ.get('DEEPSEEK_API_KEY') else 'AI Key 已清除。')

    def closeEvent(self, event):
        if self.reply:
            previous=self.reply; self.reply=None; previous.abort()
        super().closeEvent(event)
