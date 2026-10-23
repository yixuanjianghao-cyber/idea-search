"""Discovery workspace, recommendation controls and project comparison."""
import html
import math
import time
import urllib.parse
from PySide6.QtCore import Qt, QUrl, QTimer, QRectF, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPainter, QColor, QPen, QLinearGradient, QFont, QPixmap, QIcon, QPainterPath
from PySide6.QtNetwork import QNetworkRequest, QNetworkReply
from PySide6.QtWidgets import (QWidget, QFrame, QLabel, QPushButton, QHBoxLayout, QVBoxLayout,
    QGridLayout, QLineEdit, QGraphicsOpacityEffect, QTableWidget, QTableWidgetItem, QHeaderView)
from discovery import Discovery
from engine import BASE
from trending_ui import TrendingMixin

TOPICS = [
    ('AI 与自动化', 'ai-agents', '本地 AI 助手和工作流自动化', '#a794ff'),
    ('知识与笔记', 'note-taking', '自托管的笔记软件，支持双链', '#6fe0ce'),
    ('开发者工具', 'developer-tools', '开发者效率工具，命令行', '#84bfff'),
    ('效率与生活', 'productivity', '轻量的任务管理和日程工具', '#ffbe83'),
    ('创作与设计', 'design-tools', '开源的设计和图片编辑工具', '#f6a7d4'),
    ('本地优先', 'local-first', '本地离线的数据管理工具', '#b9e88a'),
]


def text_label(text, name='', wrap=False):
    label = QLabel(text)
    label.setTextFormat(Qt.PlainText)
    label.setObjectName(name)
    label.setWordWrap(wrap)
    return label


def navigation_icon(name):
    pix = QPixmap(24, 24); pix.fill(Qt.transparent)
    painter = QPainter(pix); painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor('#b7a5e5'), 1.7)); painter.setBrush(Qt.NoBrush)
    if name == 'home':
        for x, y in ((3, 3), (14, 3), (3, 14), (14, 14)):
            painter.drawRoundedRect(x, y, 7, 7, 2, 2)
    elif name == 'results':
        painter.drawEllipse(3, 3, 13, 13); painter.drawLine(15, 15, 22, 22)
    elif name == 'library':
        path = QPainterPath(); path.moveTo(5, 3); path.lineTo(19, 3); path.lineTo(19, 22)
        path.lineTo(12, 16); path.lineTo(5, 22); path.closeSubpath(); painter.drawPath(path)
    elif name == 'trending':
        painter.drawLine(3, 21, 3, 13); painter.drawLine(11, 21, 11, 8); painter.drawLine(19, 21, 19, 2)
    else:
        painter.drawRoundedRect(3, 4, 7, 16, 2, 2); painter.drawRoundedRect(14, 4, 7, 16, 2, 2)
    painter.end(); return QIcon(pix)


class Orbit(QWidget):
    """Native vector artwork; animates only while the discovery hero is visible."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(240, 180)
        self.phase = 0
        self.timer = QTimer(self)
        self.timer.setInterval(70)
        self.timer.timeout.connect(self.tick)

    def showEvent(self, event):
        self.timer.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def tick(self):
        self.phase += .008
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        radius = min(self.width(), self.height()) * .39
        p.setBrush(Qt.NoBrush)
        for scale in (.65, 1, 1.34):
            p.setPen(QPen(QColor('#4b457c'), 1))
            p.drawEllipse(QRectF(cx-radius*scale, cy-radius*scale*.54, radius*2*scale, radius*1.08*scale))
        grad = QLinearGradient(cx-50, cy-50, cx+50, cy+50)
        grad.setColorAt(0, QColor('#b4a0ff')); grad.setColorAt(1, QColor('#5549bc'))
        p.setPen(Qt.NoPen); p.setBrush(grad)
        p.drawRoundedRect(QRectF(cx-42, cy-42, 84, 84), 24, 24)
        p.setPen(QPen(QColor('#ffffff'), 3))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QRectF(cx-15, cy-18, 26, 26)); p.drawLine(int(cx+7), int(cy+5), int(cx+20), int(cy+18))
        for i, color in enumerate(('#71e4d1', '#c0b0ff', '#ffc489', '#86bfff')):
            angle = self.phase + i * math.pi / 2
            x, y = cx + math.cos(angle)*radius*1.14, cy+math.sin(angle)*radius*.64
            p.setPen(Qt.NoPen); p.setBrush(QColor(color)); p.drawEllipse(QRectF(x-7, y-7, 14, 14))
        p.end()


class DiscoveryMixin(TrendingMixin):
    def init_discovery(self):
        self.init_trending()
        self.discovery = Discovery(self.store)
        self.view_mode = 'home'
        self.recommendations = self.discovery.recommend()
        self.comparison = {}
        self.discovery_reply = None
        self.discovery_message = '从搜索和收藏中逐渐了解你的兴趣'
        self.discovery_pages = {}
        self.discovery_requested = False
        self.topic_override = ''
        self.saved_queries = self.store.setdefault('saved_queries', [])
        self._home_refresh = QTimer(self)
        self._home_refresh.setSingleShot(True)
        self._home_refresh.timeout.connect(self.render_current_view)

    def make_navigation(self):
        rail = QFrame()
        rail.setObjectName('navigation')
        rail.setFixedWidth(186)
        layout = QVBoxLayout(rail)
        layout.setContentsMargins(18, 26, 18, 18)
        mark = text_label('想法搜索', 'brand')
        layout.addWidget(mark)
        layout.addWidget(text_label('IDEA / DISCOVERY', 'eyebrow'))
        layout.addSpacing(30)
        self.nav_buttons = {}
        for mode, title in [('home', '  为你发现'), ('trending', '  热度排行'), ('results', '  搜索工作台'), ('library', '  我的收藏'), ('compare', '  项目对比')]:
            button = QPushButton(title)
            button.setObjectName('navButton')
            button.setIcon(navigation_icon(mode))
            button.setCheckable(True)
            button.clicked.connect(lambda _, m=mode: self.navigate(m))
            layout.addWidget(button)
            self.nav_buttons[mode] = button
        layout.addSpacing(26)
        layout.addWidget(text_label('快速探索', 'eyebrow'))
        for title, query, idea, color in TOPICS[:4]:
            button = QPushButton('  ' + title + '  ↗')
            button.setObjectName('navTopic')
            button.clicked.connect(lambda _, q=query: self.select_topic(q))
            layout.addWidget(button)
        layout.addStretch(1)
        self.nav_stats = text_label('', 'dim', True)
        layout.addWidget(self.nav_stats)
        layout.addSpacing(16)
        layout.addWidget(text_label('LOCAL FIRST\n偏好保存在这台电脑', 'eyebrow', True))
        return rail

    def persist_discovery(self):
        from ui import save_store
        save_store(self.store)
        self.nav_stats.setText(f"{len(self.discovery.data['pool'])} 个发现  ·  {len(self.store.get('favs', []))} 个收藏")

    def navigate(self, mode):
        self.back_to_search()
        self.view_mode = mode
        self._render_timer.stop()
        self._home_refresh.stop()
        if mode == 'home': self.recommendations = self.discovery.recommend(topic=self.topic_override)
        self.render_current_view()
        self.scroll.verticalScrollBar().setValue(0)
        if mode == 'trending': self.fetch_trending()

    def render_current_view(self):
        if not hasattr(self, 'host_layout'): return
        for mode, button in self.nav_buttons.items(): button.setChecked(mode == self.view_mode)
        self.history_rail.setVisible(self.view_mode == 'results')
        self.search_toolbar.setVisible(self.view_mode == 'results')
        self.filter_panel.setVisible(self.view_mode == 'results' and self.btn_filters.isChecked())
        self.status.setVisible(self.view_mode == 'results')
        self.plan_frame.setVisible(self.view_mode == 'results' and self.btn_plan.isChecked() and bool(self.plan))
        self.persist_discovery()
        if self.view_mode == 'home': self.show_discovery()
        elif self.view_mode == 'library': self.show_library()
        elif self.view_mode == 'compare': self.show_comparison()
        elif self.view_mode == 'trending': self.show_trending()
        elif self.view_mode == 'builder': self.show_builder()
        else: self.render_results()

    def hero(self):
        frame = QFrame(); frame.setObjectName('hero')
        row = QHBoxLayout(frame); row.setContentsMargins(28, 24, 22, 24)
        left = QVBoxLayout(); left.setSpacing(10)
        left.addWidget(text_label('YOUR NEXT GREAT FIND', 'heroKicker'))
        left.addWidget(text_label('让好项目，\n遇见你的下一個想法。'.replace('個', '个'), 'heroTitle'))
        left.addWidget(text_label('从一个念头出发，发现值得收藏、比较和动手尝试的开源项目。', 'heroSubtitle', True))
        row_buttons = QHBoxLayout()
        start = QPushButton('探索我的兴趣  →'); start.setObjectName('go')
        start.clicked.connect(lambda: self.fetch_recommendations())
        lucky = QPushButton('给我一点灵感'); lucky.setObjectName('heroSecondary')
        lucky.clicked.connect(self.surprise)
        row_buttons.addWidget(start); row_buttons.addWidget(lucky); row_buttons.addStretch()
        left.addSpacing(8); left.addLayout(row_buttons)
        row.addLayout(left, 3); row.addWidget(Orbit(frame), 1)
        return frame

    def section_row(self, title, subtitle='', action=None, action_text=''):
        row = QHBoxLayout()
        col = QVBoxLayout(); col.setSpacing(3)
        col.addWidget(text_label(title, 'sectionTitle'))
        if subtitle: col.addWidget(text_label(subtitle, 'dim', True))
        row.addLayout(col, 1)
        if action:
            button = QPushButton(action_text); button.setObjectName('ghost'); button.clicked.connect(action); row.addWidget(button)
        self.host_layout.addLayout(row)

    def show_discovery(self):
        self.clear_cards()
        self.host_layout.addWidget(self.hero())
        # Search directions are clearly labelled; these are not fabricated repository results.
        topics = QHBoxLayout(); topics.setSpacing(8)
        for title, query, idea, color in TOPICS:
            button = QPushButton(title)
            button.setObjectName('topicButton')
            button.setStyleSheet(f'color:{color};')
            button.setCheckable(True); button.setChecked(query == self.topic_override)
            button.clicked.connect(lambda _, q=query: self.select_topic(q))
            topics.addWidget(button)
        self.host_layout.addLayout(topics)
        weights = self.discovery.interests()
        interests = ' / '.join(sorted(weights, key=weights.get, reverse=True)[:4])
        self.section_row('为你发现', self.discovery_message, self.rotate_recommendations, '换一批')
        control = QHBoxLayout()
        control.addWidget(text_label('兴趣信号  ' + (interests or '还在认识你，试着搜索或收藏一个项目'), 'signal', True), 1)
        reset = QPushButton('重置兴趣'); reset.setObjectName('ghost'); reset.clicked.connect(self.reset_interests); control.addWidget(reset)
        self.host_layout.addLayout(control)
        if self.recommendations:
            self.add_tiles(self.recommendations)
        else:
            empty = QFrame(); empty.setObjectName('emptyDiscovery')
            v = QVBoxLayout(empty); v.setContentsMargins(24, 22, 24, 22)
            v.addWidget(text_label('你的发现空间，从这里开始', 'sectionTitle'))
            v.addWidget(text_label('推荐会随搜索和收藏更新。选择上方方向，或直接输入你想解决的问题。', 'dim', True))
            self.host_layout.addWidget(empty)
        self.section_row('灵感启动器', '把模糊的念头变成可搜索的需求', self.show_builder, '组合我的需求  +')
        seeds = QHBoxLayout()
        for title, q, idea, color in TOPICS[:3]:
            button = QPushButton(idea + '  →'); button.setObjectName('seedButton')
            button.clicked.connect(lambda _, text=idea: self._run_example(text)); seeds.addWidget(button)
        self.host_layout.addLayout(seeds)
        if self.saved_queries:
            self.section_row('保存的搜索方案', '保留语言、星标与更新条件，一键重跑')
            for entry in self.saved_queries:
                row = QHBoxLayout()
                button = QPushButton(entry['q']); button.setObjectName('seedButton'); button.clicked.connect(lambda _, e=entry: self.restore_query(e))
                remove = QPushButton('移除'); remove.setObjectName('ghost'); remove.clicked.connect(lambda _, e=entry: self.remove_query(e))
                row.addWidget(button, 1); row.addWidget(remove); self.host_layout.addLayout(row)
        self.host_layout.addStretch(1)

    def add_tiles(self, rows):
        grid_widget = QWidget(); grid = QGridLayout(grid_widget)
        grid.setContentsMargins(0, 0, 0, 0); grid.setSpacing(14)
        columns = 3 if self.width() >= 1360 else 2
        for index, repo in enumerate(rows): grid.addWidget(self.project_tile(repo, index), index // columns, index % columns)
        for col in range(columns): grid.setColumnStretch(col, 1)
        self.host_layout.addWidget(grid_widget)
        self.queue_introductions(rows)

    def project_tile(self, repo, index=0):
        frame = QFrame(); frame.setObjectName('discoveryCard')
        frame.setMinimumHeight(240)
        layout = QVBoxLayout(frame); layout.setContentsMargins(18, 16, 18, 16); layout.setSpacing(9)
        title = repo.get('full_name', '')
        top = QHBoxLayout()
        accent = TOPICS[index % len(TOPICS)][3]
        initials = text_label(title.split('/')[-1][:2].upper(), 'projectMonogram')
        initials.setAlignment(Qt.AlignCenter); initials.setFixedSize(42, 42)
        initials.setStyleSheet(f'color:{accent}; background:#25263e; border-radius:12px; font-size:16px; font-weight:700;')
        top.addWidget(initials); top.addStretch()
        if self.view_mode != 'library':
            dismiss = QPushButton('×'); dismiss.setObjectName('dismiss'); dismiss.setToolTip('不感兴趣，不再推荐此项目')
            dismiss.clicked.connect(lambda: self.dismiss_project(title)); top.addWidget(dismiss)
        layout.addLayout(top)
        layout.addWidget(text_label(title, 'projectTitle', True))
        label = self.make_intro_label(repo)
        label.setMinimumHeight(42); layout.addWidget(label)
        layout.addWidget(self.original_description(repo))
        stars = repo.get('stars') or 0
        star_text = f'{stars/1000:.1f}k' if stars >= 1000 else str(stars)
        layout.addWidget(text_label(f"★ {star_text}    ·    {repo.get('lang') or '语言未标注'}    ·    {repo.get('license') or '许可证未知'}", 'projectMeta', True))
        reason = repo.get('recommend_reason') or ('已收藏 · 随时继续探索' if self.view_mode == 'library' else '来自搜索结果')
        layout.addWidget(text_label(reason, 'reason', True))
        layout.addStretch()
        actions = QHBoxLayout(); actions.setSpacing(6)
        open_button = QPushButton('看懂它  ↗'); open_button.setObjectName('tilePrimary'); open_button.clicked.connect(lambda: self.open_detail(repo)); actions.addWidget(open_button)
        favorite = title in {f['full_name'] for f in self.store.get('favs', [])}
        fav = QPushButton('已收藏' if favorite else '收藏'); fav.setObjectName('tileAction'); fav.clicked.connect(lambda: self.toggle_fav(repo)); actions.addWidget(fav)
        compare = QPushButton('已选' if title in self.comparison else '对比'); compare.setObjectName('tileAction'); compare.clicked.connect(lambda: self.toggle_compare(repo)); actions.addWidget(compare)
        layout.addLayout(actions)
        return frame

    def select_topic(self, query):
        if self.discovery_reply is not None:
            previous = self.discovery_reply
            self.discovery_reply = None
            previous.abort()
        self.topic_override = query
        self.navigate('home')
        self.fetch_recommendations(query)

    def fetch_recommendations(self, query=None, advance=False):
        if self.discovery_reply is not None: return
        weights = self.discovery.interests()
        query = query or self.topic_override or (max(weights, key=weights.get) if weights else 'developer-tools')
        page = self.discovery_pages.get(query, 1)
        if advance: page = page % 5 + 1
        self.discovery_pages[query] = page
        self.discovery_requested = True
        self.discovery_message = f'正在从 GitHub 获取 {query} 项目…'
        if self.view_mode == 'home': self.show_discovery()
        request = QNetworkRequest(QUrl(BASE + '/api/discover?' + urllib.parse.urlencode({'q': query, 'page': page})))
        request.setTransferTimeout(95000)
        reply = self.nam.get(request)
        self.discovery_reply = reply
        def finished():
            import json
            if self.discovery_reply is not reply:
                reply.deleteLater()
                return
            self.discovery_reply = None
            try:
                data = json.loads(bytes(reply.readAll()))
                if reply.error() != QNetworkReply.NetworkError.NoError or data.get('error'): raise ValueError(data.get('error') or reply.errorString())
                rows = data.get('items') or []
                self.discovery.ingest(rows, '探索方向 · ' + query)
                self.recommendations = self.discovery.recommend(rotate=advance, topic=self.topic_override)
                self.discovery_message = ('使用 GitHub 缓存' if data.get('cached') else '刚从 GitHub 更新') + f' · {len(rows)} 个候选 · 偏好只在本机计算'
                if not rows: self.discovery_message = '这个方向暂无更多结果，已保留现有推荐。'
                self.persist_discovery()
            except Exception as exc:
                self.discovery_message = '更新失败，保留已有推荐 · ' + str(exc)[:100]
            finally:
                reply.deleteLater()
                if self.view_mode == 'home': self.show_discovery()
                self.update_recommendation_rail()
        reply.finished.connect(finished)

    def rotate_recommendations(self):
        old = {r['full_name'] for r in self.recommendations}
        batch = self.discovery.recommend(rotate=True, topic=self.topic_override)
        self.recommendations = batch
        self.discovery_message = '已换一批 · 按你的兴趣从本机候选中挑选'
        if self.view_mode == 'home': self.show_discovery()
        self.update_recommendation_rail()
        if len(batch) < 6 or old.intersection(r['full_name'] for r in batch):
            self.fetch_recommendations(advance=True)

    def dismiss_project(self, name):
        self.discovery.dismiss(name)
        self.recommendations = self.discovery.recommend(topic=self.topic_override)
        self.persist_discovery()
        self.render_current_view()
        self.update_recommendation_rail()

    def reset_interests(self):
        self.discovery.reset(); self.topic_override = ''
        self.discovery_message = '搜索兴趣与“不感兴趣”已重置；收藏仍会影响推荐'
        self.recommendations = self.discovery.recommend()
        self.render_current_view()

    def surprise(self):
        index = self.store.get('inspiration_index', -1) + 1
        self.store['inspiration_index'] = index
        self.select_topic(TOPICS[index % len(TOPICS)][1])

    def update_recommendation_rail(self):
        if not hasattr(self, 'rec_rail_layout'): return
        while self.rec_rail_layout.count():
            item = self.rec_rail_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self.rec_rail_layout.addWidget(text_label('与你的搜索有关', 'sectionTitle'))
        for repo in self.recommendations[:3]:
            button = QPushButton(repo['full_name']); button.setObjectName('railProject'); button.setToolTip(repo.get('recommend_reason', ''))
            button.clicked.connect(lambda _, r=repo: self.open_detail(r)); self.rec_rail_layout.addWidget(button)
        if not self.recommendations: self.rec_rail_layout.addWidget(text_label('搜索后会更新推荐', 'dim'))
        button = QPushButton('换一批'); button.setObjectName('ghost'); button.clicked.connect(self.rotate_recommendations); self.rec_rail_layout.addWidget(button)

    def show_library(self):
        self.clear_cards()
        self.section_row('我的收藏', '留住值得继续探索的项目', self.copy_library, '复制项目清单')
        rows = []
        for fav in self.store.get('favs', []):
            rows.append({**fav, 'html_url': fav.get('url', ''), 'description': fav.get('desc', ''), **self.discovery.data['pool'].get(fav['full_name'], {})})
        if rows: self.add_tiles(rows)
        else: self.host_layout.addWidget(text_label('还没有收藏。在项目卡片上点击「收藏」，它就会出现在这里。', 'emptyText', True))
        self.host_layout.addStretch()

    def copy_library(self):
        from PySide6.QtWidgets import QApplication
        text = '\n'.join(f"- [{f['full_name']}]({f.get('url', f.get('html_url', ''))})" for f in self.store.get('favs', []))
        QApplication.clipboard().setText(text)
        self.status.setText('已复制 Markdown 项目清单')

    def toggle_compare(self, repo):
        name = repo['full_name']
        if name in self.comparison: self.comparison.pop(name)
        elif len(self.comparison) < 3: self.comparison[name] = repo
        else:
            self.status.setText('最多对比三个项目，请先移除一个。'); return
        self.nav_buttons['compare'].setText(f'  项目对比  {len(self.comparison)}/3')
        self.status.setText(f'已选 {len(self.comparison)} 个项目，可从左侧进入对比。')
        self.render_current_view()

    def show_comparison(self):
        self.clear_cards()
        self.section_row('放在一起，才好选择', '对比最多三个项目的公开指标；不将星标当作适配结论', self.copy_comparison, '复制对比摘要')
        if not self.comparison:
            self.host_layout.addWidget(text_label('在搜索结果或推荐卡片中点击「对比」，建立你的候选清单。', 'emptyText', True))
        else:
            rows = list(self.comparison.values())
            actions = QHBoxLayout()
            for repo in rows:
                button = QPushButton('移除 ' + repo['full_name'].split('/')[-1]); button.clicked.connect(lambda _, r=repo: self.toggle_compare(r)); actions.addWidget(button)
            self.host_layout.addLayout(actions)
            fields = [('星标', 'stars'), ('主要语言', 'lang'), ('许可证', 'license'), ('最近提交', 'pushed_at'), ('未关闭 issues', 'issues'), ('描述', 'description')]
            table = QTableWidget(len(fields), len(rows))
            table.setObjectName('comparisonTable')
            table.setHorizontalHeaderLabels([r['full_name'] for r in rows]); table.setVerticalHeaderLabels([f[0] for f in fields])
            table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            table.setEditTriggers(QTableWidget.NoEditTriggers)
            table.setWordWrap(True)
            for y, (_, key) in enumerate(fields):
                for x, repo in enumerate(rows):
                    value = repo.get(key)
                    text = str(value) if value is not None else '未标注'
                    if key == 'pushed_at': text = text[:10]
                    table.setItem(y, x, QTableWidgetItem(text))
                table.setRowHeight(y, 140 if key == 'description' else 52)
            table.setMinimumHeight(460)
            self.host_layout.addWidget(table)
            self.host_layout.addWidget(text_label('功能是否满足、许可证是否适用于你的用途、运行环境是否兼容，仍需逐项核对。', 'dim', True))
        self.host_layout.addStretch()

    def copy_comparison(self):
        from PySide6.QtWidgets import QApplication
        lines = ['| 项目 | 星标 | 语言 | 许可证 |', '|---|---:|---|---|']
        for r in self.comparison.values(): lines.append(f"| {r['full_name']} | {r.get('stars', 0)} | {r.get('lang') or '未知'} | {r.get('license') or '未知'} |")
        QApplication.clipboard().setText('\n'.join(lines)); self.status.setText('已复制对比摘要')

    def save_query(self):
        q = self.search.text().strip()
        if not q: self.status.setText('先输入一个需求再保存。'); return
        entry = dict(q=q, lang=self.cb_lang.currentIndex(), stars=self.sp_stars.value(), updated=self.cb_updated.currentIndex(), sort=self.cb_sort.currentIndex(), license=self.chk_license.isChecked(), archived=self.chk_archived.isChecked(), limit=self.sp_limit.value())
        self.saved_queries[:] = [entry] + [e for e in self.saved_queries if e['q'] != q][:19]
        self.persist_discovery(); self.status.setText('已保存搜索方案，可在发现页一键重跑。')

    def restore_query(self, entry):
        widgets = [(self.cb_lang, 'lang'), (self.cb_updated, 'updated'), (self.cb_sort, 'sort')]
        for widget, key in widgets:
            widget.blockSignals(True); widget.setCurrentIndex(entry.get(key, 0)); widget.blockSignals(False)
        self.sp_stars.setValue(entry.get('stars', 0)); self.sp_limit.setValue(entry.get('limit', 30))
        self.chk_license.setChecked(entry.get('license', False)); self.chk_archived.setChecked(entry.get('archived', False))
        self._run_example(entry['q'])

    def remove_query(self, entry):
        self.saved_queries[:] = [e for e in self.saved_queries if e != entry]
        self.persist_discovery(); self.show_discovery()

    def show_builder(self):
        self.view_mode = "builder"
        self.clear_cards()
        self.section_row('把需求拼出来', '先描述用途，再选择约束；选好后可以继续编辑。', lambda: self.navigate('home'), '返回发现')
        editor = QLineEdit(); editor.setPlaceholderText('例如：管理个人知识的笔记软件'); editor.setMinimumHeight(56)
        self.host_layout.addWidget(editor)
        choices = QHBoxLayout(); selected = set()
        groups = [('本地离线', '本地离线'), ('自托管', '自托管'), ('轻量', '轻量'), ('中文支持', '支持中文'), ('无需 Docker', '不要 Docker')]
        for name, value in groups:
            button = QPushButton(name); button.setCheckable(True); button.setObjectName('topicButton')
            button.toggled.connect(lambda checked, v=value: selected.add(v) if checked else selected.discard(v)); choices.addWidget(button)
        self.host_layout.addLayout(choices)
        go = QPushButton('生成需求并搜索  →'); go.setObjectName('go')
        def execute():
            if not editor.text().strip(): editor.setFocus(); return
            self._run_example(editor.text().strip() + '，' + '，'.join(v for _, v in groups if v in selected))
        go.clicked.connect(execute); self.host_layout.addWidget(go)
        self.host_layout.addStretch()
