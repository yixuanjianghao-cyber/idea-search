"""仓库解读窗口：白话说明 + 适不适合 + 怎么用 + 一键部署。"""
from __future__ import annotations

import html
import json
import os
import subprocess
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QProcess, QTimer
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton,
    QScrollArea, QSizePolicy, QTextBrowser, QCheckBox, QVBoxLayout, QWidget, QSplitter, QGridLayout, QComboBox,
)

from assistant import ChatWorker
from client import StreamWorker
from degraded import build_brief
from engine import BASE
from env import check_needs, scan as env_scan, summary as env_summary
from project_guide import project_guide

DEPLOY_DIR = Path.home() / "ghf-deploy"


class AnalyzeWorker(StreamWorker):
    stage = Signal(str)
    done = Signal(dict)
    analysis_failed = Signal(str, str)

    def __init__(self, repo, query, parent=None):
        url = BASE + "/api/analyze/stream?" + urllib.parse.urlencode({"repo": repo, "q": query})
        super().__init__(url, parent)
        self.event.connect(self._event)
        self.failed.connect(lambda msg: self.analysis_failed.emit(msg, "NET"))

    def _event(self, ev):
        if ev.get("type") == "stage": self.stage.emit(ev.get("name", ""))
        elif ev.get("type") == "done": self.done.emit(ev.get("data") or {})
        elif ev.get("type") == "error": self.analysis_failed.emit(ev.get("message", "分析失败"), ev.get("code", "ERR"))


def section(title: str) -> QLabel:
    lbl = QLabel(title)
    lbl.setObjectName("panelTitle")
    return lbl


def body(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setTextFormat(Qt.RichText)
    lbl.setStyleSheet("color:#c3ccd6;font-size:13px;")
    return lbl


class CommandRow(QWidget):
    """一条命令 + 复制按钮。"""

    def __init__(self, cmd: str, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        box = QLabel(f"<code style='font-family:Consolas,monospace;color:#7ee787;'>{cmd}</code>")
        box.setTextFormat(Qt.RichText)
        box.setWordWrap(True)
        box.setStyleSheet("background:#0d1520;border:1px solid #1f2a37;border-radius:6px;padding:6px 9px;")
        box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        row.addWidget(box, 1)
        btn = QPushButton("复制")
        btn.setObjectName("ghost")
        btn.setFixedWidth(48)
        btn.clicked.connect(lambda _=False, c=cmd: QApplication.clipboard().setText(c))
        row.addWidget(btn)


class DetailDialog(QDialog):
    back_requested = Signal()
    def __init__(self, repo: dict, query: str = "", parent=None):
        super().__init__(parent)
        self.deploy_process = None
        self.release_download = None
        self.runtime_process = None
        self.repo = repo
        self.query = query
        self.data: dict | None = None
        self.worker: AnalyzeWorker | None = None
        self.env = env_scan()
        self.chat_worker: ChatWorker | None = None
        self.chat_history: list[dict] = []

        self.setWindowTitle(f"看懂它 · {repo.get('full_name', '')}")
        self.resize(920, 760)
        self.setMinimumSize(760, 560)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 14)
        outer.setSpacing(10)

        # 头部
        head = QHBoxLayout()
        back = QPushButton("← 返回搜索")
        back.clicked.connect(self.back_requested.emit)
        head.addWidget(back)
        title = QLabel(f"<b style='font-size:16px;'>{repo.get('full_name','')}</b>")
        title.setTextFormat(Qt.RichText)
        title.setWordWrap(True)
        head.addWidget(title, 1)
        self.btn_open = QPushButton("打开仓库")
        self.btn_open.setObjectName("ghost")
        self.btn_open.clicked.connect(lambda: self._open(repo.get("html_url", "")))
        head.addWidget(self.btn_open)
        outer.addLayout(head)

        meta = QLabel(
            f"<span style='color:#d29922;'>★ {repo.get('stars', 0)}</span>"
            f"<span style='color:#5d6b7a;'> · </span>{repo.get('lang') or '-'}"
            f"<span style='color:#5d6b7a;'> · </span>{repo.get('license') or '无许可证'}"
        )
        meta.setTextFormat(Qt.RichText)
        meta.setStyleSheet("font-size:12px;color:#8b98a5;")
        outer.addWidget(meta)

        self.env_line = QLabel()
        self.env_line.setObjectName("dim")
        self.env_line.setWordWrap(True)
        self.env_line.setStyleSheet("font-size:11px;color:#5d6b7a;")
        self.env_line.setText("你的电脑：" + env_summary(self.env))
        outer.addWidget(self.env_line)

        # 内容区
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.host = QWidget()
        self.host_layout = QVBoxLayout(self.host)
        self.host_layout.setContentsMargins(0, 0, 6, 0)
        self.host_layout.setSpacing(14)
        self.scroll.setWidget(self.host)
        self.content_splitter = QSplitter(Qt.Horizontal)
        self.content_splitter.setChildrenCollapsible(False)
        self.content_splitter.addWidget(self.scroll)
        outer.addWidget(self.content_splitter, 1)

        # ── AI 助手：只懂这个仓库 + 你这台电脑 ──
        self.chat_box = QFrame()
        self.chat_box.setObjectName("panel")
        chat_l = QVBoxLayout(self.chat_box)
        chat_l.setContentsMargins(12, 10, 12, 10)
        chat_l.setSpacing(6)

        head_row = QHBoxLayout()
        self.chat_title = QLabel("项目问答")
        self.chat_title.setObjectName("panelTitle")
        head_row.addWidget(self.chat_title)
        head_row.addStretch(1)
        ai_settings = QPushButton('AI 设置'); ai_settings.setObjectName('ghost')
        ai_settings.clicked.connect(self.configure_ai); head_row.addWidget(ai_settings)
        self.model_tag = QLabel("")
        self.model_tag.setObjectName("dim")
        self.model_tag.setStyleSheet("font-size:10px;color:#5d6b7a;")
        head_row.addWidget(self.model_tag)
        chat_l.addLayout(head_row)

        self.transcript = QTextBrowser()
        self.transcript.setOpenExternalLinks(True)
        self.transcript.setMinimumHeight(170)
        self.transcript.setStyleSheet(
            "background:#141624;border:1px solid #34334a;border-radius:10px;padding:12px;font-size:13px;")
        self.transcript.setHtml(
            "<div style='color:#8b98a5;font-size:12px;'>基于已读取的 README 摘录和本机检测回答；未读取的信息会明确说明。<br>"
            "先问它能做什么，再了解如何开始。</div>")
        chat_l.addWidget(self.transcript, 1)

        chips = QGridLayout()
        chips.setSpacing(6)
        self.question_buttons = []
        for index, text in enumerate(("它能干什么？", "我电脑能跑吗？", "要装什么？", "怎么开始？", "端口多少？")):
            b = QPushButton(text)
            b.setObjectName("ghost")
            b.setStyleSheet("font-size:11px;padding:4px 8px;")
            b.clicked.connect(lambda _=False, q=text: self.ask(q))
            chips.addWidget(b, index // 2, index % 2)
            self.question_buttons.append(b)
        chat_l.addLayout(chips)

        row_in = QHBoxLayout()
        row_in.setSpacing(8)
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("问点什么…（Enter 发送）")
        self.chat_input.returnPressed.connect(self.ask_current)
        row_in.addWidget(self.chat_input, 1)
        self.btn_ask = QPushButton("发送")
        self.btn_ask.setObjectName("go")
        self.btn_ask.setStyleSheet("padding:6px 16px;font-size:13px;border-radius:8px;")
        self.btn_ask.clicked.connect(self.ask_current)
        row_in.addWidget(self.btn_ask)
        chat_l.addLayout(row_in)

        self.content_splitter.addWidget(self.chat_box)
        self.content_splitter.setStretchFactor(0, 3)
        self.content_splitter.setStretchFactor(1, 2)
        self.content_splitter.setSizes([700, 400])

        self.progress = QProgressBar()
        self.progress.setObjectName("thin")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        outer.addWidget(self.progress)

        self.footer = QLabel("正在读 README、目录和依赖清单…")
        self.footer.setObjectName("dim")
        outer.addWidget(self.footer)

        self.terminal = QTextBrowser()
        self.terminal.setMinimumHeight(100)
        self.terminal.setMaximumHeight(180)
        self.terminal.setVisible(False)
        self.terminal.setStyleSheet("font-family:Consolas; background:#0d1520;")
        outer.addWidget(self.terminal)
        self.stop_deploy = QPushButton("停止部署进程")
        self.stop_deploy.hide()
        self.stop_deploy.clicked.connect(self.stop_process)
        outer.addWidget(self.stop_deploy)
        self.open_service = QPushButton('打开本地服务'); self.open_service.hide()
        self.open_service.clicked.connect(lambda: self._open(self.service_url)); outer.addWidget(self.open_service)
        self.cancel_download = QPushButton('取消下载'); self.cancel_download.hide()
        self.cancel_download.clicked.connect(self.cancel_release); outer.addWidget(self.cancel_download)
        self._render_loading()
        self.start()

    # ── 数据 ────────────────────────────────────────────────
    def start(self):
        if self.worker:
            self.worker.stop()
        self.progress.setVisible(True)
        self.progress.setValue(3)
        self.footer.setText("正在读这个仓库…")
        self.worker = AnalyzeWorker(self.repo.get("full_name", ""), self.query, self)
        self.worker.stage.connect(self.on_stage)
        self.worker.done.connect(self.on_data)
        self.worker.analysis_failed.connect(self.on_fail)
        self.worker.start()

    def on_stage(self, name: str):
        if (self.data or {}).get("degraded"):
            return
        order = ["读取仓库信息", "读取 README", "扫描目录结构", "读取依赖清单", "整理成白话"]
        idx = order.index(name) + 1 if name in order else 1
        self.progress.setValue(int(5 + 90 * idx / len(order)))
        self.footer.setText(f"{name}…")

    def on_fail(self, msg: str, code: str = "ERR"):
        self.progress.setVisible(False)
        # 用搜索结果里已有的信息拼一份简版，别让窗口空着
        self.data = build_brief(self.repo, self.query, msg)
        self._clear()

        box = QFrame()
        box.setObjectName("panel")
        bl = QVBoxLayout(box)
        bl.setContentsMargins(12, 10, 12, 10)
        title = 'GitHub API 配额已用完' if code == 'RATE_LIMIT' else '仓库读取未完成'
        t = QLabel(f"<span style='color:#d29922;'>{title}：{html.escape(msg)}</span>")
        t.setTextFormat(Qt.RichText)
        t.setWordWrap(True)
        bl.addWidget(t)
        hint = QLabel("下面是简化版（只用搜索结果里的信息，没读 README）。"
                      "可重试读取公开文件；如仍无法读取，请在设置中配置 GitHub Token。DeepSeek Key 用于 AI 问答，不能增加 GitHub 配额。")
        hint.setObjectName("dim")
        hint.setWordWrap(True)
        bl.addWidget(hint)
        row = QHBoxLayout()
        b_retry = QPushButton("重试")
        b_retry.setObjectName("ghost")
        b_retry.clicked.connect(self.start)
        row.addWidget(b_retry)
        b_settings = QPushButton('配置 GitHub Token'); b_settings.setObjectName('ghost')
        b_settings.clicked.connect(lambda: self.window().open_settings() if hasattr(self.window(),'open_settings') else None)
        row.addWidget(b_settings)
        row.addStretch(1)
        bl.addLayout(row)
        self._render_brief(self.data)
        self.host_layout.insertWidget(0, box)
        self.footer.setText("简化模式 · 没读 README")

    def on_data(self, d: dict):
        self.progress.setValue(100)
        self.progress.setVisible(False)
        self._render_brief(d)

    def _render_brief(self, d: dict):
        self.data = d
        self._clear()
        self.footer.setText(("缓存命中 · " if d.get("cached") else "刚读取 · ") + (d.get("quotaNote") or ""))

        fit = d.get("fit") or {}
        level = fit.get("level", "maybe")
        label, color = {
            "good": ("基本条件已识别，仍需核验", "#3fb950"),
            "maybe": ("需要核对运行条件", "#d29922"),
            "poor": ("不太合适", "#f85149"),
        }.get(level, ("看看再说", "#8b98a5"))

        self._render_overview(d)
        self._render_launch(d)

        # 适不适合
        self.host_layout.addWidget(section("适不适合你"))
        est = d.get("estimate") or ""
        head = QLabel(
            f"<span style='color:{color};font-weight:600;font-size:14px;'>● {label}</span>"
            + (f"<span style='color:#5d6b7a;font-size:12px;'>　预计 {est}</span>" if est else ""))
        head.setTextFormat(Qt.RichText)
        self.host_layout.addWidget(head)
        reasons = fit.get("reasons") or []
        if reasons:
            self.host_layout.addWidget(body("".join(f"· {html.escape(r)}<br>" for r in reasons)))

        # 需要准备什么
        needs = d.get("needs") or []
        if needs:
            self.host_layout.addWidget(section("开跑之前要准备"))
            rows = check_needs(self.env, needs)
            needs_html = ""
            for r in rows:
                mark = "<span style='color:#3fb950;'>✓ 已具备</span>" if r["ok"] is True else \
                       f"<span style='color:#f85149;'>待处理：{r['fix']}</span>"
                needs_html += f"· {r['need']} —— {mark}<br>"
            self.host_layout.addWidget(body(needs_html))

        # 里面有什么
        self.host_layout.addWidget(section("里面有什么"))
        stack = d.get("stack") or []
        chips = "<span style='color:#7ee787;'>" + " · ".join(stack) + "</span>" if stack else "没法判断"
        self.host_layout.addWidget(body(f"技术栈：{chips}"))
        files = d.get("files") or []
        if files:
            self.host_layout.addWidget(body("顶层文件：" + html.escape("、".join(files[:14]))))
        mf = d.get("manifest") or {}
        if mf.get("deps"):
            self.host_layout.addWidget(body("主要依赖：" + html.escape("、".join(mf["deps"][:8]))))
        heads = d.get("headings") or []
        if heads:
            self.host_layout.addWidget(body(
                "<span style='color:#5d6b7a;'>README 章节：</span>" + " · ".join(heads)))
        size_mb = round((d.get("size") or 0) / 1024, 1)
        self.host_layout.addWidget(body(f"体积约 {size_mb} MB · 未关闭 issue {d.get('issues', 0)}"))

        # 怎么用
        self.host_layout.addWidget(section("怎么用（照着点）"))
        steps = d.get("steps") or []
        for i, s in enumerate(steps, 1):
            self.host_layout.addWidget(body(f"<b style='color:#58a6ff'>{i}.</b> {html.escape(s)}"))
        cmds = d.get("commands") or []
        if cmds:
            self.host_layout.addWidget(body("<span style='color:#5d6b7a;'>命令（点复制，粘到终端里）：</span>"))
            for c in cmds:
                self.host_layout.addWidget(CommandRow(c))

        # 一键部署（提示词合集 / 清单类没有部署这回事）
        kind = d.get("kind")
        if kind in ("examples", "prompts", "awesome", "dataset", "api-service"):
            self.host_layout.addWidget(section("要不要部署"))
            self.host_layout.addWidget(body(
                html.escape(project_guide(d)['usage'])))
            self.host_layout.addStretch(1)
            self.footer.setText(("缓存命中 · " if d.get("cached") else "刚读取 · ") + (d.get("quotaNote") or ""))
            return

        dep = d.get("deploy") or {}
        self.host_layout.addWidget(section("部署计划"))
        script = dep.get("script") or ""
        if script:
            preview = QLabel(script.replace("&", "&amp;").replace("<", "&lt;").replace("\r\n", "\n"))
            preview.setWordWrap(True)
            preview.setStyleSheet(
                "background:#0d1520;border:1px solid #1f2a37;border-radius:8px;padding:10px;"
                "font-family:Consolas,monospace;font-size:11px;color:#8b98a5;")
            self.host_layout.addWidget(preview)
        if not script and dep.get("mode") != "android":
            self.host_layout.addWidget(body("尚未核验可执行入口。请重试读取项目文件；GitHub 配额不足时可配置 GitHub Token。"))
            retry = QPushButton('重新识别部署方式'); retry.setObjectName('go'); retry.clicked.connect(self.start)
            self.host_layout.addWidget(retry)
            self.host_layout.addStretch(1)
            return
        self.deploy_review = QCheckBox("我已核对下方脚本；安装依赖会运行项目提供的代码")
        self.host_layout.addWidget(self.deploy_review)
        rowh = QHBoxLayout()
        is_android = dep.get("mode") == "android"
        b_copy = QPushButton("复制部署脚本")
        b_copy.setObjectName("ghost")
        b_copy.clicked.connect(lambda: QApplication.clipboard().setText(script))
        rowh.addWidget(b_copy)
        b_run = QPushButton("打开下载页" if is_android else "在应用内运行部署")
        b_run.setObjectName("go")
        b_run.setEnabled(is_android)
        self.deploy_review.toggled.connect(b_run.setEnabled)
        b_run.clicked.connect(self.run_deploy)
        rowh.addWidget(b_run)
        rowh.addStretch(1)
        self.host_layout.addLayout(rowh)
        notes = dep.get("notes") or []
        if notes:
            self.host_layout.addWidget(body("<span style='color:#5d6b7a;'>" + " · ".join(notes) + "</span>"))

        # 注意
        risks = d.get("risks") or []
        if risks:
            self.host_layout.addWidget(section("要注意"))
            self.host_layout.addWidget(body("".join(
                f"<span style='color:#d29922;'>· {r}</span><br>" for r in risks)))

        note = d.get("quotaNote") or ""
        self.host_layout.addStretch(1)
        self.footer.setText(("缓存命中 · " if d.get("cached") else "刚读取 · ") + note)

    # ── 行为 ────────────────────────────────────────────────
    # ── 聊天 ────────────────────────────────────────────────
    def _render_chat(self, partial: str = "") -> None:
        import html as _h

        parts = ["<div style='color:#5d6b7a;font-size:11px;margin-bottom:6px;'>"
                 "基于已读取的 README 摘录和本机检测回答；未读取的信息会明确说明。</div>"]
        for m in self.chat_history:
            role = m.get("role")
            color = "#58a6ff" if role == "user" else "#7ee787"
            name = "我" if role == "user" else "助手"
            message = _h.escape(m.get("content", "")).replace("\n", "<br>")
            parts.append(f"<div style='margin:12px 0;color:#ddddeb;line-height:145%;'>"
                         f"<span style='color:{color};font-weight:600;'>{name}</span><br>{message}</div>")
        if partial:
            parts.append(f"<div style='margin:6px 0;'><span style='color:#7ee787;'>助手：</span>"
                         f"<span style='color:#c9d1d9;'>{_h.escape(partial).replace(chr(10), '<br>')}</span></div>")
        self.transcript.setHtml("".join(parts))
        cursor = self.transcript.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.transcript.setTextCursor(cursor)
        self.transcript.ensureCursorVisible()
        bar = self.transcript.verticalScrollBar()
        bar.setValue(bar.maximum())

    def ask_current(self):
        self.ask(self.chat_input.text().strip())

    def ask(self, q: str):
        if not q:
            return
        if not self.data:
            self.chat_history.append({"role": "assistant", "content": "还在读仓库，等两秒再问。"})
            self._render_chat()
            return
        if self.chat_worker and self.chat_worker.isRunning():
            return

        self.chat_input.clear()
        self.chat_history.append({"role": "user", "content": q})
        self._partial = ""
        self._render_chat()

        from env import prompt_block

        self.model_tag.setText("正在回答…")
        self.chat_worker = ChatWorker(
            q, self.data, prompt_block(self.env),
            history=self.chat_history[:-1],
            query=self.query, parent=self, model=getattr(self.window(), 'store', {}).get('ai_model', ''), settings=getattr(self.window(), 'store', {}))

        def on_chunk(piece: str):
            self._partial += piece
            self._render_chat(self._partial)

        def on_done(text: str):
            self._partial = ""
            self.model_tag.setText(self.chat_worker.answer_source)
            self.chat_history.append({"role": "assistant", "content": text})
            self._render_chat()

        self.chat_worker.chunk.connect(on_chunk)
        self.chat_worker.finished_text.connect(on_done)
        self.chat_worker.start()

    def configure_ai(self):
        from ai_support import AISettings
        store = getattr(self.window(), 'store', {})
        AISettings(store, self).exec()

    def _render_overview(self, data):
        guide = project_guide(data)
        panel = QFrame(); panel.setObjectName('projectOverview')
        layout = QVBoxLayout(panel); layout.setContentsMargins(20, 18, 20, 18); layout.setSpacing(12)
        badge = QLabel(guide['kind_label']); badge.setObjectName('guideBadge')
        layout.addWidget(badge, 0, Qt.AlignLeft)
        title = QLabel('先看懂这个项目'); title.setObjectName('guideTitle'); layout.addWidget(title)
        summary = body(html.escape(guide['summary'])); summary.setObjectName('projectSummary')
        summary.setTextInteractionFlags(Qt.TextSelectableByMouse); layout.addWidget(summary)
        layout.addWidget(section('你能用它做什么'))
        for index, capability in enumerate(guide['capabilities'], 1):
            item = body(f"<span style='color:#bdaaff;font-weight:600;'>{index:02d} · {html.escape(capability['title'])}</span><br>"
                f"{html.escape(capability['detail'])}")
            item.setToolTip(capability['source'] + '：' + capability['evidence'])
            layout.addWidget(item)
        note = body(html.escape(guide['note'])); note.setStyleSheet('color:#9298b1;font-size:11px;'); layout.addWidget(note)
        layout.addWidget(section('如何开始'))
        layout.addWidget(body(html.escape(guide['usage'])))
        original = body(html.escape(guide['original'] or '作者尚未提供简介。'))
        original.setTextInteractionFlags(Qt.TextSelectableByMouse); original.hide()
        toggle = QPushButton('查看作者原文'); toggle.setObjectName('ghost'); toggle.setCheckable(True)
        toggle.toggled.connect(original.setVisible)
        layout.addWidget(toggle, 0, Qt.AlignLeft); layout.addWidget(original)
        self.host_layout.addWidget(panel)

    def _render_launch(self, data):
        plan = data.get('launch')
        if not plan: return
        panel = QFrame(); panel.setObjectName('panel')
        layout = QVBoxLayout(panel); layout.setContentsMargins(18, 16, 18, 16)
        layout.addWidget(section('推荐使用路线 · ' + plan.get('title', '')))
        layout.addWidget(body(html.escape(plan.get('description', ''))))
        asset = plan.get('asset') or {}
        if asset:
            layout.addWidget(body(html.escape(asset.get('name', '')) + f" · 约 {round(asset.get('size',0)/1024**2,1)} MB · GitHub Releases"))
        self.case_selector = None
        if plan.get('mode') == 'examples':
            self.case_selector = QComboBox(); self.case_selector.addItems(data.get('dirs') or ['查看全部案例']); layout.addWidget(self.case_selector)
        action = QPushButton(plan.get('button') or '开始使用'); action.setObjectName('go')
        action.clicked.connect(self.run_recommended_action); layout.addWidget(action)
        self.launch_button = action
        if plan.get('mode') in ('script','environment'):
            layout.addWidget(body('点击后会运行仓库的安装代码；遇到错误会停止，下方可查看完整日志。'))
            from runtime_setup import required_runtimes, RUNTIMES
            import shutil
            for runtime in required_runtimes(data.get('how') or ''):
                if shutil.which(runtime): continue
                name = RUNTIMES[runtime][0]
                missing = QPushButton('先安装缺少的 ' + name); missing.setObjectName('ghost')
                missing.clicked.connect(lambda _, tool=runtime: self.install_runtime(tool)); layout.addWidget(missing)
            if data.get('how') in ('compose','docker'):
                docker_desktop = Path(os.environ.get('ProgramFiles','C:/Program Files'))/'Docker'/'Docker'/'Docker Desktop.exe'
                if docker_desktop.exists():
                    start_docker = QPushButton('启动 Docker Desktop'); start_docker.setObjectName('ghost')
                    start_docker.clicked.connect(lambda: self._open(docker_desktop.as_uri())); layout.addWidget(start_docker)
        self.host_layout.addWidget(panel)

    def install_runtime(self, runtime):
        from runtime_setup import installer_command, refresh_process_path, RUNTIMES
        import shutil
        jobs = getattr(self.window(), 'runtime_install_jobs', {})
        if runtime in jobs and jobs[runtime].poll() is None:
            self.footer.setText('环境安装正在进行，请等待当前安装完成。'); return
        command = installer_command(runtime)
        if not command:
            self._open(RUNTIMES[runtime][2]); self.footer.setText('系统未提供 winget，已打开官方安装页面。'); return
        import time
        DEPLOY_DIR.mkdir(parents=True,exist_ok=True)
        log = DEPLOY_DIR / f'runtime-{runtime}-{time.time_ns()}.log'
        try:
            with log.open('wb') as output:
                self.runtime_process = subprocess.Popen([command[0],*command[1]],stdout=output,stderr=subprocess.STDOUT,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except OSError as exc: self.footer.setText('环境安装无法启动：'+str(exc)); return
        jobs[runtime]=self.runtime_process; self.window().runtime_install_jobs=jobs
        self.terminal.clear(); self.terminal.show(); offset=[0]
        process=self.runtime_process
        timer=QTimer(self)
        def poll():
            try:
                with log.open('rb') as output:
                    output.seek(offset[0]); data=output.read(); offset[0]=output.tell()
                if data: self.terminal.insertPlainText(data.decode('utf-8','replace'))
            except OSError: pass
            code=process.poll()
            if code is None: return
            timer.stop(); refresh_process_path()
            self.env.setdefault('tools', {})[runtime] = '已检测到（版本未核验）' if shutil.which(runtime) else None
            self.env_line.setText('你的电脑：' + env_summary(self.env))
            self.footer.setText('环境安装流程完成，请重新点击「一键部署」。Docker 可能还需启动或按安装器提示重启。' if code in (0,3010) else f'环境安装未完成（退出码 {code}），请查看日志或使用官网安装。')
        timer.timeout.connect(poll); timer.start(700)
        self.footer.setText('环境安装在后台进行，系统可能要求确认。返回浏览不会中断安装器。')

    def run_recommended_action(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        plan = (self.data or {}).get('launch') or {}
        mode = plan.get('mode')
        if mode == 'release':
            if self.release_download: return
            from release_install import ReleaseDownload
            self.release_download = ReleaseDownload(plan['asset'], self.data['full_name'], DEPLOY_DIR, self)
            self.launch_button.setEnabled(False)
            self.cancel_download.show()
            self.progress.setRange(0,100); self.progress.show()
            self.release_download.status.connect(self.footer.setText)
            self.release_download.progress.connect(lambda got,total: self.progress.setValue(int(100*got/total)) if total>0 else None)
            self.release_download.failed.connect(self.release_failed)
            self.release_download.ready.connect(self.release_ready)
            self.release_download.start()
        elif mode in ('script','environment'):
            if hasattr(self,'deploy_review'): self.deploy_review.setChecked(True)
            self.run_deploy()
        elif mode == 'examples':
            directory = self.case_selector.currentText() if self.case_selector else ''
            url = self.data.get('html_url', '')
            if directory and directory != '查看全部案例': url += '/tree/' + urllib.parse.quote(self.data.get('default_branch') or 'HEAD',safe='') + '/' + urllib.parse.quote(directory,safe='')
            self._open(url)
        elif mode == 'browse': self._open(self.data.get('html_url', ''))
        else: self.ask('根据已读取的 README，我第一次要怎么用这个项目？请区分安装包、开发库和源码运行，不要猜命令。')

    def release_failed(self, message):
        self.progress.hide(); self.cancel_download.hide(); self.launch_button.setEnabled(True); self.footer.setText(message)
        if self.release_download: self.release_download.deleteLater(); self.release_download = None

    def release_ready(self, path):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        self.progress.hide(); self.cancel_download.hide(); self.launch_button.setEnabled(True)
        target = Path(path)
        if self.data.get('kind') == 'cli' and target.suffix.lower() == '.exe':
            self.terminal.clear(); self.terminal.show(); self.stop_deploy.show()
            self.deploy_process = QProcess(self); self.deploy_process.setProcessChannelMode(QProcess.MergedChannels)
            self.deploy_process.readyReadStandardOutput.connect(self._deploy_output)
            self.deploy_process.finished.connect(self._deploy_finished)
            self.deploy_process.start(str(target), ['--help'])
            self.footer.setText('命令行工具已下载，下方显示帮助。实际参数可继续向项目助手提问。')
            if self.release_download: self.release_download.deleteLater(); self.release_download = None
            return
        if target.suffix.lower() == '.exe':
            result = QProcess.startDetached(str(target), [], str(target.parent))
            ok = result[0] if isinstance(result, tuple) else result
        else: ok = QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
        self.footer.setText(('下载完成，已打开安装器或程序；请完成界面中的设置。' if target.is_file() else '已下载并解压，打开文件夹选择主程序。') if ok else '下载完成，但未能打开。文件位置：' + path)
        if self.release_download: self.release_download.deleteLater(); self.release_download = None

    def cancel_release(self):
        if self.release_download: self.release_download.stop()
        self.release_failed('下载已取消。')

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'content_splitter'):
            orientation = Qt.Horizontal if self.width() >= 1050 else Qt.Vertical
            if self.content_splitter.orientation() != orientation:
                self.content_splitter.setOrientation(orientation)
                self.content_splitter.setSizes([600, 350])

    def run_deploy(self):
        if not self.data:
            return
        dep = self.data.get("deploy") or {}
        if dep.get("mode") == "android":
            self._open(self.repo.get("html_url", "") + "/releases")
            return
        script = dep.get("script") or ""
        if not script or not self.deploy_review.isChecked():
            return
        if self.deploy_process and self.deploy_process.state() != QProcess.NotRunning:
            self.footer.setText("部署正在运行，请先停止。")
            return
        DEPLOY_DIR.mkdir(parents=True, exist_ok=True)
        import re
        name = re.sub(r"[^a-zA-Z0-9_.-]", "_", self.repo.get("full_name", "repo"))
        path = DEPLOY_DIR / f"{name}-deploy.cmd"
        try:
            path.write_text(script, encoding="utf-8", newline="")
            self.terminal.clear()
            self.terminal.show()
            self.stop_deploy.show()
            self.deploy_process = QProcess(self)
            self.deploy_process.setProcessChannelMode(QProcess.MergedChannels)
            self.deploy_process.setWorkingDirectory(str(DEPLOY_DIR))
            self.deploy_process.readyReadStandardOutput.connect(self._deploy_output)
            self.deploy_process.finished.connect(self._deploy_finished)
            self.deploy_process.errorOccurred.connect(lambda _: self.footer.setText("部署进程无法启动"))
            self.deploy_process.start(os.environ.get("COMSPEC", "cmd.exe"), ["/d", "/c", str(path)])
            self.footer.setText("部署输出显示在下方。离开此页会停止前台进程，后台容器需单独管理。")
        except Exception as e:
            self.footer.setText(f"运行失败：{e}")

    def _deploy_output(self):
        raw = bytes(self.deploy_process.readAllStandardOutput())
        text = raw.decode("utf-8", "replace")
        self.terminal.moveCursor(self.terminal.textCursor().MoveOperation.End)
        self.terminal.insertPlainText(text)
        import re
        cleaned = re.sub(r'\x1b\[[0-9;]*m', '', text)
        match = re.search(r'https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0):([0-9]{2,5})(?:/[^\s<>"\']*)?', cleaned)
        if match and 0 < int(match[1]) < 65536:
            self.service_url = match[0].replace('0.0.0.0', '127.0.0.1')
            self.open_service.setText('打开服务 · ' + self.service_url); self.open_service.show()

    def _deploy_finished(self, code, status):
        self._deploy_output()
        self.stop_deploy.hide()
        mode = ((self.data or {}).get('launch') or {}).get('mode')
        success = '开发环境已准备好；按 README 示例在代码中调用。' if mode == 'environment' else '工具已就绪；下方可查看帮助。' if (self.data or {}).get('kind') == 'cli' else '部署命令执行完成；请核验服务是否启动。'
        self.footer.setText(success if code == 0 else f"部署已停止（退出码 {code}），请查看输出。")

    def stop_process(self):
        proc = self.deploy_process
        if proc and proc.state() != QProcess.NotRunning:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(proc.processId()), "/T", "/F"],
                    capture_output=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                proc.kill()
            proc.waitForFinished(1500)

    def shutdown(self):
        if self.release_download: self.release_download.stop()
        if self.worker: self.worker.stop()
        if self.chat_worker: self.chat_worker.stop()
        self.stop_process()

    def closeEvent(self, event):
        self.shutdown()
        super().closeEvent(event)

    def _open(self, url: str):
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl

        QDesktopServices.openUrl(QUrl(url))

    def _clear(self):
        while self.host_layout.count():
            item = self.host_layout.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
            elif item.layout():
                while item.layout().count():
                    sub = item.layout().takeAt(0)
                    sw = sub.widget()
                    if sw:
                        sw.hide()
                        sw.setParent(None)
                        sw.deleteLater()

    def _render_loading(self):
        self._clear()
        self.host_layout.addWidget(section("正在读这个仓库"))
        self.host_layout.addWidget(body(
            "拉 README、看目录结构、找依赖清单…… 大概两三秒。<br>"
            "<span style='color:#5d6b7a;'>读完会告诉你：它是干什么的、适不适合你、里面有什么、怎么跑起来。</span>"))
        self.host_layout.addStretch(1)

