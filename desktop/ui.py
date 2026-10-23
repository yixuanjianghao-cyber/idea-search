"""主窗口：原生 Qt 界面，流式结果、可编辑检索式、历史与收藏。"""
from __future__ import annotations

import html
import json
import os
import re
import time
import urllib.parse
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, QSize, QStringListModel
from PySide6.QtGui import (
    QColor, QDesktopServices, QFont, QKeySequence, QPainter, QPainterPath,
    QPixmap, QShortcut, QAction,
)
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QCompleter, QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QProgressBar, QPushButton,
    QScrollArea, QSizePolicy, QSpinBox, QSplitter, QStackedWidget, QTabWidget, QVBoxLayout, QWidget,
)

from discovery_ui import DiscoveryMixin
from introductions import IntroductionMixin
from client import StreamWorker
from detail import DetailDialog
from engine import BASE, Engine, health, http_json

DATA = Path(os.environ.get("GHF_DATA_DIR") or Path.home()) / ".github-finder-desktop.json"


def load_store() -> dict:
    try:
        return json.loads(DATA.read_text("utf-8"))
    except Exception:
        return {"history": [], "favs": []}


def save_store(store: dict) -> None:
    try:
        DATA.parent.mkdir(parents=True, exist_ok=True)
        temp = DATA.with_suffix(".tmp")
        temp.write_text(json.dumps(store, ensure_ascii=False, indent=2), "utf-8")
        temp.replace(DATA)
    except Exception:
        pass


def num(n: int) -> str:
    if n >= 10000:
        return f"{n/1000:.0f}k"
    if n >= 1000:
        return f"{n/1000:.1f}k"
    return str(n)


def ago(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        ts = time.mktime(time.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S"))
    except Exception:
        return "—"
    d = (time.time() - ts) / 86400
    if d < 1:
        return "今天"
    if d < 30:
        return f"{int(d)} 天前"
    if d < 365:
        return f"{int(d/30)} 个月前"
    return f"{int(d/365)} 年前"


def rounded(pix: QPixmap, size: int = 40, radius: int = 9) -> QPixmap:
    pix = pix.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    out = QPixmap(size, size)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0, 0, size, size, radius, radius)
    p.setClipPath(path)
    p.drawPixmap(0, 0, pix)
    p.end()
    return out


def placeholder(text: str, size: int = 40) -> QPixmap:
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor("#1b2532"))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(0, 0, size, size, 9, 9)
    p.setPen(QColor("#5d6b7a"))
    f = QFont("Segoe UI", 14, QFont.Bold)
    p.setFont(f)
    p.drawText(pix.rect(), Qt.AlignCenter, (text or "?")[:1].upper())
    p.end()
    return pix


def hl(text: str, terms: list[str]) -> str:
    """命中的词在描述里高亮。"""
    s = html.escape(text or "")
    for term in sorted([t for t in terms if len(t) >= 3], key=len, reverse=True)[:6]:
        try:
            s = re.sub(re.escape(term), lambda m: f'<b style="color:#7ee787;">{m.group(0)}</b>', s, flags=re.I)
        except Exception:
            continue
    return s


class ClickableCard(QFrame):
    """双击 = 打开解读窗口。"""

    def __init__(self, on_double, parent=None):
        super().__init__(parent)
        self._on_double = on_double
        self.setObjectName("card")
        self.setCursor(Qt.ArrowCursor)

    def mouseDoubleClickEvent(self, event):  # noqa: N802
        if self._on_double:
            self._on_double()
        super().mouseDoubleClickEvent(event)


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("GitHub 设置 · 用于搜索和仓库解读")
        self.setMinimumWidth(460)
        vl = QVBoxLayout(self)
        vl.setContentsMargins(20, 20, 20, 20)
        vl.setSpacing(10)

        title = QLabel("GitHub Token")
        title.setObjectName("panelTitle")
        vl.addWidget(title)

        self.info = QLabel("写进 ~/.github-finder.json，保存后立刻生效。")
        self.info.setObjectName("dim")
        self.info.setWordWrap(True)
        vl.addWidget(self.info)

        self.edit = QLineEdit()
        self.edit.setPlaceholderText("ghp_… 或 github_pat_…")
        self.edit.setEchoMode(QLineEdit.Password)
        vl.addWidget(self.edit)
        guide = QLabel('这里只填 GitHub 生成的只读 Token，不需要写权限。公开仓库也可不填，但配额较低。\nDeepSeek 的 sk-… Key 请填到主界面的「AI 设置」。')
        guide.setWordWrap(True); vl.addWidget(guide)
        help_row = QHBoxLayout()
        get_token = QPushButton('获取 GitHub Token'); get_token.clicked.connect(lambda: QDesktopServices.openUrl(QUrl('https://github.com/settings/personal-access-tokens/new'))); help_row.addWidget(get_token)
        self.test_button = QPushButton('测试 GitHub 连接'); self.test_button.clicked.connect(self.test_connection); help_row.addWidget(self.test_button)
        vl.addLayout(help_row)
        self.nam = QNetworkAccessManager(self); self.test_reply = None

        row = QHBoxLayout()
        self.btn_clear = QPushButton("清空")
        self.btn_clear.setObjectName("ghost")
        self.btn_clear.clicked.connect(lambda: self._save(""))
        self.btn_save = QPushButton("保存")
        self.btn_save.setObjectName("go")
        self.btn_save.clicked.connect(lambda: self._save(self.edit.text().strip()))
        row.addWidget(self.btn_clear)
        row.addStretch(1)
        row.addWidget(self.btn_save)
        vl.addLayout(row)
        self.refresh()

    def refresh(self):
        try:
            cfg = http_json("/api/config")
            masked = cfg.get("token") or ""
            self.info.setText(
                (f"当前已配置：{masked}（输入新的覆盖）" if cfg.get("hasToken") else "当前未配置 token，搜索 10 次/分。")
                + f"\n配置文件：{cfg.get('path','')}"
            )
        except Exception as e:
            self.info.setText(f"读不到配置：{e}")

    def _save(self, token: str):
        if token.startswith('sk-'):
            self.info.setText('这是 AI API Key，请到「AI 设置 → DeepSeek」中填写。'); return
        try:
            http_json("/api/config", {"token": token})
            self.accept()
        except Exception as e:
            self.info.setText(f"保存失败：{e}")

    def test_connection(self):
        if self.test_reply: return
        self.test_button.setEnabled(False); self.info.setText('正在测试 GitHub 连接…')
        request = QNetworkRequest(QUrl(BASE + '/api/check-github-token'))
        request.setHeader(QNetworkRequest.ContentTypeHeader, 'application/json'); request.setTransferTimeout(15000)
        reply = self.nam.post(request, json.dumps({'token':self.edit.text().strip(),'useSaved':not bool(self.edit.text().strip())}).encode()); self.test_reply = reply
        def completed():
            try:
                data = json.loads(bytes(reply.readAll()))
                self.info.setText(data.get('error') or ('GitHub 已连接 · ' + ('Token 有效' if data.get('authenticated') else '未登录模式') + f" · 核心配额剩余 {data.get('remaining', '未知')}"))
            except Exception: self.info.setText('未能连接 GitHub，请检查网络和代理。')
            finally: self.test_reply = None; reply.deleteLater(); self.test_button.setEnabled(True)
        reply.finished.connect(completed)


class MainWindow(DiscoveryMixin, IntroductionMixin, QMainWindow):
    def __init__(self, engine: Engine):
        super().__init__()
        self.engine = engine
        self.setWindowTitle(f"想法搜索 {QApplication.applicationVersion()} · GitHub")
        screen = QApplication.primaryScreen().availableGeometry()
        self.setMinimumSize(min(1180, screen.width()), min(760, screen.height()))
        self.resize(min(1480, screen.width()), min(960, screen.height()))

        self.items: dict[str, dict] = {}
        self.native: list[dict] = []
        self.plan: dict | None = None
        self.worker: StreamWorker | None = None
        self.store = load_store()
        self.init_discovery()
        self.custom_queries: list[str] | None = None
        self.buckets_done = 0
        self.buckets_total = 0
        self.last_done = False
        self.started_at = 0.0

        self.nam = QNetworkAccessManager(self)
        self.init_introductions()
        self.avatar_labels: dict[str, QLabel] = {}
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(120)
        self._render_timer.timeout.connect(self.render_current_view)

        self._build()
        self._bind_keys()
        self.refresh_health()
        self.refresh_lists()
        last = self.store.get("last") or ""
        if last:
            self.search.setText(last)

    # ── 界面 ────────────────────────────────────────────────
    def _build(self):
        central = QWidget()
        self.pages = QStackedWidget()
        self.search_page = central
        self.detail_page = None
        self.pages.addWidget(central)
        shell = QWidget()
        shell.setObjectName("appShell")
        shell_layout = QHBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)
        shell_layout.addWidget(self.make_navigation())
        shell_layout.addWidget(self.pages, 1)
        self.setCentralWidget(shell)
        root = QVBoxLayout(central)
        root.setContentsMargins(26, 22, 22, 14)
        root.setSpacing(14)

        # 顶栏
        head = QHBoxLayout()
        title = QLabel('发现值得动手的开源项目')
        title.setObjectName("title")
        title.setTextFormat(Qt.RichText)
        head.addWidget(title)
        head.addStretch(1)
        self.quota = QLabel("配额 …")
        self.quota.setObjectName("badge")
        head.addWidget(self.quota)
        self.btn_json = QPushButton("复制 JSON")
        self.btn_json.setObjectName("ghost")
        self.btn_json.setEnabled(False)
        self.btn_json.clicked.connect(self.copy_json)
        head.addWidget(self.btn_json)
        self.btn_first = QPushButton("打开第一条")
        self.btn_first.setObjectName("ghost")
        self.btn_first.setEnabled(False)
        self.btn_first.clicked.connect(self.open_first)
        head.addWidget(self.btn_first)
        self.btn_settings = QPushButton("设置")
        self.btn_settings.setObjectName("ghost")
        self.btn_settings.clicked.connect(self.open_settings)
        head.addWidget(self.btn_settings)
        ai_settings = QPushButton('AI 设置'); ai_settings.setObjectName('ghost')
        ai_settings.clicked.connect(self.open_ai_settings); head.addWidget(ai_settings)
        root.addLayout(head)

        # 搜索行
        srow = QHBoxLayout()
        srow.setSpacing(10)
        self.search = QLineEdit()
        self.search.setObjectName("search")
        self.search.setPlaceholderText("说你要什么：轻量的 python 库，把网页转成 markdown")
        self.search.returnPressed.connect(self.do_search)

        # 输入联想：词典里的概念，打两个字母就提示
        self._sug_model = QStringListModel([])
        self._completer = QCompleter(self._sug_model, self)
        self._completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._completer.setFilterMode(Qt.MatchContains)
        self.search.setCompleter(self._completer)
        self._sug_timer = QTimer(self)
        self._sug_timer.setSingleShot(True)
        self._sug_timer.setInterval(220)
        self._sug_timer.timeout.connect(self._fetch_suggest)
        self.search.textEdited.connect(lambda _: self._sug_timer.start())
        srow.addWidget(self.search, 1)
        self.btn_go = QPushButton("搜索")
        self.btn_go.setObjectName("go")
        self.btn_go.clicked.connect(self.search_or_cancel)
        srow.addWidget(self.btn_go)
        root.addLayout(srow)

        # 过滤行
        frow = QHBoxLayout()
        frow.setSpacing(8)
        self.cb_lang = QComboBox()
        self.cb_lang.addItems(["自动", "Python", "JavaScript", "TypeScript", "Go", "Rust", "C", "C++",
                               "C#", "Java", "Kotlin", "Swift", "PHP", "Shell", "Lua", "Dart"])
        self.sp_stars = QSpinBox()
        self.sp_stars.setRange(0, 1_000_000)
        self.sp_stars.setValue(0)
        self.cb_updated = QComboBox()
        self.cb_updated.addItems(["不限", "1 个月内", "半年内", "一年内", "三年内"])
        self.cb_sort = QComboBox()
        self.cb_sort.addItems(["相关度", "星标", "最近更新", "上升期"])
        self.chk_archived = QCheckBox("含归档")
        self.chk_license = QCheckBox("仅带许可证")
        self.sp_limit = QSpinBox()
        self.sp_limit.setRange(5, 100)
        self.sp_limit.setValue(30)

        for w in (QLabel("语言"), self.cb_lang, QLabel("最低 star"), self.sp_stars,
                  QLabel("更新"), self.cb_updated, QLabel("排序"), self.cb_sort,
                  self.chk_archived, self.chk_license, QLabel("条数"), self.sp_limit):
            if isinstance(w, QLabel):
                w.setObjectName("dim")
            frow.addWidget(w)
        frow.addStretch(1)
        self.filter_panel = QWidget()
        self.filter_panel.setLayout(frow)
        self.filter_panel.setVisible(False)
        toolbar = QHBoxLayout()
        self.btn_filters = QPushButton("筛选与排序")
        self.btn_filters.setCheckable(True)
        self.btn_filters.toggled.connect(lambda checked: self.filter_panel.setVisible(checked and self.view_mode == 'results'))
        toolbar.addWidget(self.btn_filters)
        self.btn_plan = QPushButton("查看检索计划")
        self.btn_plan.setCheckable(True)
        self.btn_plan.toggled.connect(lambda checked: self.plan_frame.setVisible(checked and bool(self.plan)))
        toolbar.addWidget(self.btn_plan)
        save_search = QPushButton("保存搜索方案")
        save_search.setObjectName("ghost")
        save_search.clicked.connect(self.save_query)
        toolbar.addWidget(save_search)
        toolbar.addStretch()
        toolbar.addWidget(QLabel("中文描述需求 · 多路检索 · 仓库解读"))
        self.search_toolbar = QWidget()
        self.search_toolbar.setLayout(toolbar)
        root.addWidget(self.search_toolbar)
        root.addWidget(self.filter_panel)

        self.cb_sort.currentIndexChanged.connect(lambda _: self._render_timer.start())
        for w in (self.chk_archived, self.chk_license):
            w.stateChanged.connect(lambda _: self._render_timer.start())
        self.cb_updated.currentIndexChanged.connect(lambda _: self._render_timer.start())
        self.sp_stars.valueChanged.connect(lambda _: self._render_timer.start())
        self.sp_limit.valueChanged.connect(lambda _: self._render_timer.start())
        self.cb_lang.currentIndexChanged.connect(self._on_lang_change)

        # 主体
        split = QSplitter(Qt.Horizontal)
        split.setHandleWidth(10)

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(10)

        self.plan_frame = QFrame()
        self.plan_frame.setObjectName("panel")
        self.plan_frame.setVisible(False)
        self.plan_layout = QVBoxLayout(self.plan_frame)
        self.plan_layout.setContentsMargins(14, 12, 14, 12)
        self.plan_layout.setSpacing(8)
        lv.addWidget(self.plan_frame)

        self.progress = QProgressBar()
        self.progress.setObjectName("thin")
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(False)
        lv.addWidget(self.progress)

        self.status = QLabel("")
        self.status.setObjectName("status")
        lv.addWidget(self.status)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.host = QWidget()
        self.host_layout = QVBoxLayout(self.host)
        self.host_layout.setContentsMargins(0, 0, 8, 0)
        self.host_layout.setSpacing(8)
        self.host_layout.addStretch(1)
        self.scroll.setWidget(self.host)
        lv.addWidget(self.scroll, 1)

        split.addWidget(left)

        # 右栏
        rail = QWidget()
        self.history_rail = rail
        rail.setFixedWidth(238)
        rv = QVBoxLayout(rail)
        rv.setContentsMargins(0, 0, 0, 0)
        rec_box = QFrame()
        rec_box.setObjectName("panel")
        self.rec_rail_layout = QVBoxLayout(rec_box)
        self.rec_rail_layout.setContentsMargins(12, 14, 12, 14)
        rv.addWidget(rec_box)
        self.update_recommendation_rail()
        self.tabs = QTabWidget()
        self.list_hist = QListWidget()
        self.list_fav = QListWidget()
        self.tabs.addTab(self.list_hist, "历史")
        self.tabs.addTab(self.list_fav, "收藏")
        rv.addWidget(self.tabs, 1)

        tips = QLabel("按 <b>/</b> 聚焦输入框 · <b>Ctrl+Enter</b> 立刻搜索<br>"
                      "勾掉的检索式不参与；每条都可以改后重跑")
        tips.setObjectName("dim")
        tips.setWordWrap(True)
        rv.addWidget(tips)
        split.addWidget(rail)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 0)
        root.addWidget(split, 1)

        self.list_hist.itemDoubleClicked.connect(self._hist_activate)
        self.list_fav.itemDoubleClicked.connect(self._fav_activate)

        self.render_current_view()

    def _bind_keys(self):
        for seq, fn in (
            ("/", self.search.setFocus),
            ("Ctrl+F", self.search.setFocus),
            ("Ctrl+Return", self.do_search),
            ("Escape", self.search.clear),
        ):
            sc = QShortcut(QKeySequence(seq), self)
            sc.activated.connect(fn)

    # ── 状态 ────────────────────────────────────────────────
    def refresh_health(self):
        try:
            h = health() or {}
            if h.get("ok") and not self.discovery_requested and not os.environ.get("GHF_DISABLE_DISCOVERY"):
                self.discovery_requested = True
                QTimer.singleShot(100, self.fetch_recommendations)
            q = h.get("quota") or {}
            fresh = q.get("fresh") or {}
            if h.get("token"):
                rem = fresh.get("remaining")
                self.quota.setText(f"已认证 {h.get('tokenMasked','')}" + (f" · 剩 {rem}" if rem is not None else ""))
                self.quota.setProperty("warn", "false")
            else:
                rem = fresh.get("remaining")
                self.quota.setText("未认证" + (f" · {q.get('resource', 'API')} 剩 {rem}/{fresh.get('limit', '?')}" if rem is not None else " · 配额有限"))
                self.quota.setProperty("warn", "true")
            self.quota.style().unpolish(self.quota)
            self.quota.style().polish(self.quota)
        except Exception:
            self.quota.setText("引擎未连接")

    def open_settings(self):
        SettingsDialog(self).exec()
        self.refresh_health()

    # ── 搜索 ────────────────────────────────────────────────
    def do_search(self):
        q = self.search.text().strip()
        if not q:
            self.search.setFocus()
            return
        self.back_to_search()
        self.view_mode = "results"
        self.history_rail.show()
        self.search_toolbar.show()
        self.filter_panel.setVisible(self.btn_filters.isChecked())
        self.status.show()
        for mode, button in self.nav_buttons.items(): button.setChecked(mode == "results")
        if self.worker and self.worker.isRunning():
            self.worker.stop()

        if q != getattr(self, "_last_query", None):
            self.custom_queries = None
        self._last_query = q
        if self.custom_queries == []:
            self.status.setText("请至少启用一条检索式。")
            return
        self.items.clear()
        self.native.clear()
        self.plan = None
        self.buckets_done = 0
        self.buckets_total = 0
        self.last_done = False
        self.started_at = time.time()
        self.clear_cards()
        self.progress.setVisible(True)
        self.progress.setValue(3)
        self.status.setText("编译检索式…")
        self.btn_go.setText("停止搜索")
        self.btn_json.setEnabled(False)
        self.btn_first.setEnabled(False)
        self._push_history(q)

        params = {"q": q, "limit": str(self.sp_limit.value()),
                  "sort": ("stars", "stars", "recent", "trending")[max(self.cb_sort.currentIndex(), 0)] if self.cb_sort.currentIndex() else "relevance",
                  "minStars": str(self.sp_stars.value()),
                  "updated": ("0", "30", "180", "365", "1095")[self.cb_updated.currentIndex()]}
        if self.cb_lang.currentIndex() > 0:
            params["lang"] = self.cb_lang.currentText()
        if self.chk_archived.isChecked():
            params["archived"] = "1"
        if self.chk_license.isChecked():
            params["license"] = "1"
        if self.custom_queries:
            params["extra"] = ";".join(self.custom_queries)
            params["maxQueries"] = str(len(self.custom_queries))

        url = BASE + "/api/stream?" + urllib.parse.urlencode(params)
        self.worker = StreamWorker(url, self)
        self.worker.event.connect(self.on_event)
        self.worker.failed.connect(self.on_fail)
        self.worker.start()

    def _on_lang_change(self, _):
        if self.search.text().strip():
            self.do_search()

    def on_fail(self, msg: str):
        self.btn_go.setEnabled(True)
        self.btn_go.setText("搜索")
        self.progress.setVisible(False)
        self.status.setText(f"连接失败：{msg}")
        if not self.items:
            self.show_empty("本地引擎没有响应。请重新启动应用后重试。")

    def on_event(self, ev: dict):
        t = ev.get("type")
        if t == "plan":
            self.plan = ev.get("plan") or {}
            self.buckets_total = len(self.plan.get("variants") or [])
            self.build_plan()
            self.status.setText(f"{self.buckets_total} 路并发检索中…")
            self.progress.setValue(8)
        elif t == "bucket":
            self.buckets_done += 1
            for it in ev.get("items") or []:
                cur = self.items.get(it["full_name"])
                if not cur or it.get("score", 0) > cur.get("score", 0):
                    self.items[it["full_name"]] = it
            total = max(self.buckets_total, 1)
            self.progress.setValue(int(8 + 90 * self.buckets_done / total))
            self.status.setText(
                f"{ev['progress']['done']}/{ev['progress']['of']} 路已回 · {len(self.items)} 条候选"
                f" · 「{ev.get('label','')}」{ev.get('count',0)} 条{'（缓存）' if ev.get('cached') else ''}"
            )
            self._render_timer.start()
        elif t == "bucketError":
            self.buckets_done += 1
            self.status.setText(f"{ev.get('label','')} 失败：{ev.get('message','')}")
        elif t == "done":
            self.buckets_done = self.buckets_total
            self.progress.setValue(100)
            results = ev.get("results") or []
            self.items = {r["full_name"]: r for r in results}
            self.native = ev.get("native") or []
            self.last_done = True
            self.btn_go.setEnabled(True)
            self.btn_go.setText("搜索")
            self.progress.setVisible(False)
            st = ev.get("stats") or {}
            self.status.setText(
                f"完成 · {st.get('candidates','-')} 条候选 → 去重 {st.get('afterDedupe','-')} → "
                f"过滤 {st.get('afterFilter','-')} · {time.time()-self.started_at:.1f}s"
            )
            warnings = ev.get("warnings") or []
            if warnings:
                self.status.setText(self.status.text() + " · " + "；".join(warnings))
            self.topic_override = ""
            self.discovery.observe(self.search.text().strip(), self.plan, results)
            self.recommendations = self.discovery.recommend()
            self.discovery_message = "已根据最近搜索更新 · 收藏会进一步调整推荐"
            self.persist_discovery()
            self.update_recommendation_rail()
            self.render_current_view()
            self.btn_json.setEnabled(bool(self.items))
            self.btn_first.setEnabled(bool(self.items))
            self.scroll.verticalScrollBar().setValue(0)
            self.refresh_health()
        elif t == "error":
            self.btn_go.setEnabled(True)
            self.btn_go.setText("搜索")
            self.progress.setVisible(False)
            self.status.setText(f"出错：{ev.get('message','')}")

    # ── 检索计划面板 ────────────────────────────────────────
    def build_plan(self):
        while self.plan_layout.count():
            item = self.plan_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
            elif item.layout():
                self._drop_layout(item.layout())

        if not self.plan:
            self.plan_frame.setVisible(False)
            return

        head = QHBoxLayout()
        t = QLabel("检索计划")
        t.setObjectName("panelTitle")
        head.addWidget(t)
        head.addStretch(1)
        prim = self.plan.get("primary") or "-"
        lang = self.plan.get("lang") or "不限"
        hint = QLabel(f"主词 {prim} · 语言 {lang}")
        hint.setObjectName("dim")
        head.addWidget(hint)
        self.plan_layout.addLayout(head)

        kws = " ".join(
            f'<span style="background:#{ "16301d" if k.get("role")=="primary" else "1a2532" };'
            f'color:#{ "7ee787" if k.get("role")=="primary" else "c9d1d9" };">&nbsp;{k["term"]}&nbsp;</span>'
            for k in (self.plan.get("keywords") or [])
        )
        kw = QLabel(kws)
        kw.setTextFormat(Qt.RichText)
        kw.setWordWrap(True)
        kw.setObjectName("kw")
        self.plan_layout.addWidget(kw)

        self.variant_rows = []
        for v in self.plan.get("variants") or []:
            row = QHBoxLayout()
            cb = QCheckBox()
            cb.setChecked(True)
            tag = QLabel(v.get("label", ""))
            tag.setObjectName("dim")
            tag.setFixedWidth(64)
            edit = QLineEdit(v.get("q", ""))
            edit.setProperty("original", v.get("q", ""))
            row.addWidget(cb)
            row.addWidget(tag)
            row.addWidget(edit, 1)
            self.plan_layout.addLayout(row)
            self.variant_rows.append((cb, edit))
            cb.stateChanged.connect(self._recompute_custom)
            edit.textChanged.connect(self._recompute_custom)

        self.plan_frame.setVisible(self.btn_plan.isChecked())

    def _drop_layout(self, lay):
        while lay.count():
            item = lay.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
            elif item.layout():
                self._drop_layout(item.layout())
        lay.deleteLater()

    def _recompute_custom(self):
        if not self.plan:
            return
        rows = getattr(self, "variant_rows", [])
        dirty, keep = False, []
        for cb, edit in rows:
            if not cb.isChecked():
                dirty = True
                continue
            if edit.text().strip() != edit.property("original"):
                dirty = True
            if edit.text().strip():
                keep.append(edit.text().strip())
        self.custom_queries = keep if dirty else None

    # ── 结果渲染 ────────────────────────────────────────────
    def clear_cards(self):
        while self.host_layout.count():
            item = self.host_layout.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
            elif item.layout():
                self._drop_layout(item.layout())

    def show_empty(self, text: str):
        self.clear_cards()
        lbl = QLabel(text)
        lbl.setObjectName("dim")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setMinimumHeight(160)
        self.host_layout.addWidget(lbl)
        self.host_layout.addStretch(1)

    def show_welcome(self):
        self.navigate("home")

    def _run_example(self, q: str):
        self.search.setText(q)
        self.do_search()

    def sort_items(self) -> list[dict]:
        arr = list(self.items.values())
        mode = self.cb_sort.currentIndex()
        if mode == 1:
            arr.sort(key=lambda r: r.get("stars", 0), reverse=True)
        elif mode == 2:
            arr.sort(key=lambda r: r.get("pushed_at") or "", reverse=True)
        elif mode == 3:
            def tr(r):
                try:
                    age = (time.time() - time.mktime(time.strptime(r["created_at"][:19], "%Y-%m-%dT%H:%M:%S"))) / 31536000
                except Exception:
                    age = 5.0
                return r.get("stars", 0) / max(age, 0.4)
            arr.sort(key=tr, reverse=True)
        else:
            arr.sort(key=lambda r: r.get("score", 0), reverse=True)
        return arr

    def visible(self) -> list[dict]:
        arr = self.sort_items()
        days = (0, 30, 180, 365, 1095)[self.cb_updated.currentIndex()]
        min_stars = self.sp_stars.value()
        out = []
        for r in arr:
            if r.get("stars", 0) < min_stars:
                continue
            if not self.chk_archived.isChecked() and r.get("archived"):
                continue
            if self.chk_license.isChecked() and not r.get("license"):
                continue
            if days:
                try:
                    ts = time.mktime(time.strptime((r.get("pushed_at") or "")[:19], "%Y-%m-%dT%H:%M:%S"))
                    if time.time() - ts > days * 86400:
                        continue
                except Exception:
                    pass
            out.append(r)
        return out[: self.sp_limit.value()]

    def render_results(self):
        self.avatar_labels.clear()
        self.clear_cards()
        rows = self.visible()
        if not rows:
            if self.last_done:
                self.show_empty("没搜到。换个说法，或者补一个具体技术词（python / cli / docker / android）。")
            return
        for r in rows:
            self.host_layout.addWidget(self.build_card(r))
        if self.native:
            self.host_layout.addWidget(self.build_native(self.native))
        self.host_layout.addStretch(1)
        self.queue_introductions(rows)

    def build_card(self, r: dict) -> QFrame:
        card = ClickableCard(lambda repo=r: self.open_detail(repo))
        card.setObjectName("card")
        outer = QHBoxLayout(card)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(12)

        ava = QLabel()
        ava.setFixedSize(40, 40)
        ava.setPixmap(placeholder(r.get("owner", "?")))
        outer.addWidget(ava, 0, Qt.AlignTop)
        url = r.get("avatar") or ""
        if url:
            self.avatar_labels[url] = ava
            reply = self.nam.get(QNetworkRequest(QUrl(url)))
            reply.finished.connect(lambda rep=reply, lbl=ava: self._avatar_done(rep, lbl))

        body = QVBoxLayout()
        body.setSpacing(4)

        owner = r.get("owner", "")
        name = (r.get("full_name") or "").split("/")[-1]
        title = QLabel(
            f'<a href="{r.get("html_url","")}" style="color:#58a6ff;text-decoration:none;font-weight:600;">'
            f'{owner}<span style="color:#5d6b7a;">/</span>{name}</a>'
        )
        title.setTextFormat(Qt.RichText)
        title.setOpenExternalLinks(True)
        title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        body.addWidget(title)

        why = r.get("why") or {}
        matched = why.get("matched") or []

        body.addWidget(self.make_intro_label(r))
        body.addWidget(self.original_description(r))

        hp = r.get("health", 0) or 0
        hp_txt, hp_col = ("信息较全", "#3fb950") if hp >= 0.7 else (("信息一般", "#d29922") if hp >= 0.4 else ("信息少", "#f0883e"))
        stars = num(r.get("stars", 0))
        meta = (
            f'<span style="color:#d29922;">★ {stars}</span>'
            f'<span style="color:#5d6b7a;"> · </span><span style="color:#8b98a5;">⑂ {num(r.get("forks",0))}</span>'
            f'<span style="color:#5d6b7a;"> · </span><span style="color:#8b98a5;">{r.get("lang") or "-"}</span>'
            f'<span style="color:#5d6b7a;"> · </span><span style="color:#8b98a5;">{ago(r.get("pushed_at"))}</span>'
            + (f'<span style="color:#5d6b7a;"> · </span><span style="color:#8b98a5;">{r.get("license")}</span>' if r.get("license") else "")
            + f'<span style="color:#5d6b7a;"> · </span><span style="color:{hp_col};">{hp_txt}</span>'
        )
        tags = []
        if r.get("archived"):
            tags.append(("归档", "#f85149"))
        try:
            pushed = time.mktime(time.strptime((r.get("pushed_at") or "")[:19], "%Y-%m-%dT%H:%M:%S"))
            if (time.time() - pushed) / 2592000 > 24:
                tags.append(("停更", "#d29922"))
        except Exception:
            pass
        blob = ((r.get("description") or "") + " " + " ".join(r.get("topics") or [])).lower()
        if "docker" in blob:
            tags.append(("提及 Docker", "#58a6ff"))
        if r.get("stars", 0) >= 1000 and r.get("license") and len(r.get("description") or "") > 40:
            tags.append(("有许可证", "#3fb950"))
        if tags:
            meta += " " + " ".join(f'<span style="color:{c};">· {t}</span>' for t, c in tags)

        m = QLabel(meta)
        m.setTextFormat(Qt.RichText)
        body.addWidget(m)

        topics = r.get("topics") or []
        if topics:
            trow = QLabel(" ".join(f'<span style="color:#7d8590;">#{html.escape(t)}</span>' for t in topics[:6]))
            trow.setTextFormat(Qt.RichText)
            trow.setStyleSheet("font-size:11px;")
            body.addWidget(trow)

        matched_txt = " ".join(matched)
        hit = QLabel(
            f'<span style="color:#5d6b7a;">命中</span> <span style="color:#3fb950;">{html.escape(matched_txt) or "-"}</span>'
            f'<span style="color:#5d6b7a;"> · 主词 {html.escape(str(why.get("primary","-")))} · 评分 {r.get("score","-")}</span>'
        )
        hit.setTextFormat(Qt.RichText)
        hit.setStyleSheet("font-size:11px;")
        body.addWidget(hit)
        if why.get("unverified"):
            pending = QLabel("待核验：" + "、".join(why["unverified"]))
            pending.setStyleSheet("color:#d29922;font-size:12px;")
            body.addWidget(pending)

        outer.addLayout(body, 1)

        side = QVBoxLayout()
        side.setSpacing(4)
        b_read = QPushButton("看懂它")
        b_read.setObjectName("ghost")
        b_read.setToolTip("白话说明 / 适不适合 / 怎么用 / 部署计划")
        b_read.clicked.connect(lambda _=False, repo=r: self.open_detail(repo))
        side.addWidget(b_read)
        starred = any(f.get("full_name") == r.get("full_name") for f in self.store.get("favs", []))
        b_star = QPushButton("★" if starred else "☆")
        b_star.setObjectName("star")
        b_star.setToolTip("收藏 / 取消收藏")
        b_star.clicked.connect(lambda _=False, repo=r: self.toggle_fav(repo))
        b_copy = QPushButton("复制")
        b_copy.setObjectName("ghost")
        b_copy.setMinimumWidth(56)
        b_copy.setToolTip("复制链接")
        b_copy.clicked.connect(lambda _=False, repo=r: self.copy_link(repo))
        side.addWidget(b_star)
        side.addWidget(b_copy)
        compare = QPushButton("已选对比" if r.get("full_name") in self.comparison else "加入对比")
        compare.setObjectName("ghost")
        compare.clicked.connect(lambda _=False, repo=r: self.toggle_compare(repo))
        side.addWidget(compare)
        side.addStretch(1)
        outer.addLayout(side)
        return card

    def build_native(self, rows: list[dict]) -> QFrame:
        box = QFrame()
        box.setObjectName("panel")
        vl = QVBoxLayout(box)
        vl.setContentsMargins(14, 12, 14, 12)
        vl.setSpacing(6)
        t = QLabel("中文生态 · 按星标（不参与打分）")
        t.setObjectName("panelTitle")
        vl.addWidget(t)
        for r in rows:
            line = QLabel(
                f'<a href="{r.get("html_url","")}" style="color:#58a6ff;text-decoration:none;">{r.get("full_name","")}</a>'
                f' <span style="color:#d29922;">★{num(r.get("stars",0))}</span>'
                f' <span style="color:#5d6b7a;">{r.get("lang") or ""}</span>'
            )
            line.setTextFormat(Qt.RichText)
            line.setOpenExternalLinks(True)
            vl.addWidget(line)
            d = QLabel((r.get("description") or "")[:110])
            d.setObjectName("dim")
            d.setWordWrap(True)
            vl.addWidget(d)
        return box

    def _avatar_done(self, reply, label: QLabel):
        try:
            data = reply.readAll()
            pix = QPixmap()
            if pix.loadFromData(data) and label in self.findChildren(QLabel):
                label.setPixmap(rounded(pix, 40))
        except Exception:
            pass

    # ── 收藏 / 历史 ─────────────────────────────────────────
    def toggle_fav(self, repo: dict):
        scroll_position = self.scroll.verticalScrollBar().value()
        focused = QApplication.focusWidget()
        if focused is not None and self.host.isAncestorOf(focused):
            # Removing the focused card otherwise moves focus to another card,
            # which makes QScrollArea scroll that replacement into view.
            self.scroll.setFocus(Qt.OtherFocusReason)
        favs = self.store.setdefault("favs", [])
        name = repo.get("full_name")
        idx = next((i for i, f in enumerate(favs) if f.get("full_name") == name), -1)
        if idx >= 0:
            favs.pop(idx)
        else:
            favs.insert(0, {"full_name": name, "url": repo.get("html_url"), "stars": repo.get("stars", 0),
                            "desc": repo.get("description"), "topics": repo.get("topics", []), "lang": repo.get("lang"), "at": time.time()})
            favs[:] = favs[:60]
        self.discovery.ingest([repo], "你收藏过的方向")
        self.recommendations = self.discovery.recommend(topic=self.topic_override)
        save_store(self.store)
        self.refresh_lists()
        self.render_current_view()
        self.update_recommendation_rail()
        self.host_layout.activate()
        self.scroll.verticalScrollBar().setValue(scroll_position)

    def copy_link(self, repo: dict):
        QApplication.clipboard().setText(repo.get("html_url", ""))
        self.status.setText("链接已复制")

    def open_detail(self, repo: dict):
        self.back_to_search()
        self.intro_service.stop()
        self.intro_service.paused = True
        page = DetailDialog(repo, self.search.text().strip(), self)
        page.setWindowFlags(Qt.Widget)
        page.back_requested.connect(self.back_to_search)
        self.detail_page = page
        self.pages.addWidget(page)
        self.pages.setCurrentWidget(page)

    def back_to_search(self):
        if self.detail_page:
            self.detail_page.shutdown()
            self.pages.removeWidget(self.detail_page)
            self.detail_page.deleteLater()
            self.detail_page = None
            self.intro_service.paused = False
            if not getattr(self, '_closing', False):
                if self.view_mode == 'results': self.queue_introductions(self.visible())
                elif self.view_mode == 'home': self.queue_introductions(self.recommendations)
                elif self.view_mode == 'trending': self.queue_introductions(getattr(self, 'trending_visible', []))
                elif self.view_mode == 'library': self.queue_introductions(self.store.get('favs', []))
        self.pages.setCurrentWidget(self.search_page)

    def search_or_cancel(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.btn_go.setText("搜索")
            self.progress.hide()
            self.status.setText("搜索已取消，可以修改条件重试。")
            return
        self.do_search()

    def _fetch_suggest(self):
        q = self.search.text().strip()
        if len(q) < 2:
            return
        url = QUrl(BASE + "/api/suggest?q=" + urllib.parse.quote(q))
        reply = self.nam.get(QNetworkRequest(url))

        def done():
            try:
                data = json.loads(bytes(reply.readAll()).decode("utf-8"))
                items = [i.get("text", "") for i in data.get("items", []) if i.get("text")]
                if items:
                    self._sug_model.setStringList(items)
            except Exception:
                pass

        reply.finished.connect(done)

    def copy_json(self):
        rows = self.visible()
        payload = [
            {"full_name": r.get("full_name"), "stars": r.get("stars"),
             "url": r.get("html_url"), "desc": r.get("description")}
            for r in rows
        ]
        QApplication.clipboard().setText(json.dumps(payload, ensure_ascii=False, indent=2))
        self.status.setText(f"已复制 {len(payload)} 条 JSON 到剪贴板")

    def open_first(self):
        rows = self.visible()
        if rows:
            QDesktopServices.openUrl(QUrl(rows[0].get("html_url", "")))

    def _push_history(self, q: str):
        h = [x for x in self.store.get("history", []) if x.get("q") != q]
        h.insert(0, {"q": q, "at": time.time()})
        self.store["history"] = h[:15]
        self.store["last"] = q
        save_store(self.store)
        self.refresh_lists()

    def refresh_lists(self):
        self.list_hist.clear()
        for h in self.store.get("history", []):
            it = QListWidgetItem(h["q"])
            it.setData(Qt.UserRole, h["q"])
            self.list_hist.addItem(it)
        self.list_fav.clear()
        for f in self.store.get("favs", []):
            it = QListWidgetItem(f"{f.get('full_name')}  ★{num(f.get('stars',0))}")
            it.setData(Qt.UserRole, f.get("url"))
            self.list_fav.addItem(it)

    def _hist_activate(self, item):
        self.search.setText(item.data(Qt.UserRole))
        self.do_search()

    def _fav_activate(self, item):
        QDesktopServices.openUrl(QUrl(item.data(Qt.UserRole)))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_home_refresh") and self.view_mode in ("home", "library"):
            self._home_refresh.start(180)

    def closeEvent(self, e):
        self._closing = True
        self._home_refresh.stop()
        self.intro_service.stop()
        if self.trending_reply is not None:
            pending = self.trending_reply; self.trending_reply = None; pending.abort()
        if self.discovery_reply:
            pending = self.discovery_reply
            self.discovery_reply = None
            pending.abort()
        self.back_to_search()
        if self.worker and self.worker.isRunning():
            self.worker.stop()
        self.engine.stop()
        super().closeEvent(e)
