"""GitHub Trending periods, source snapshots and local interest ordering."""
import json
import time
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtNetwork import QNetworkRequest, QNetworkReply
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QHBoxLayout, QVBoxLayout
from engine import BASE

PERIODS = {'daily': ('日榜', '今日新增'), 'weekly': ('周榜', '本周新增'), 'monthly': ('月榜', '本月新增')}


class TrendingMixin:
    def init_trending(self):
        self.trending_snapshots = self.store.setdefault('trending_snapshots', {})
        self.trending_period = self.store.get('trending_period', 'daily')
        if self.trending_period not in PERIODS: self.trending_period = 'daily'
        self.trending_personalized = bool(self.store.get('trending_personalized'))
        self.trending_reply = None
        self.trending_status = ''

    def select_trending_period(self, period):
        if self.trending_reply is not None:
            previous = self.trending_reply; self.trending_reply = None; previous.abort()
        self.trending_period = period
        self.store['trending_period'] = period
        self.trending_status = ''
        self.scroll.setFocus(Qt.OtherFocusReason)
        self.show_trending()
        self.scroll.verticalScrollBar().setValue(0)
        self.fetch_trending()

    def personalize_trending(self, checked):
        position = self.scroll.verticalScrollBar().value()
        self.scroll.setFocus(Qt.OtherFocusReason)
        self.trending_personalized = checked
        self.store['trending_personalized'] = checked
        self.persist_discovery()
        self.show_trending()
        self.host_layout.activate()
        self.scroll.verticalScrollBar().setValue(position)

    def fetch_trending(self, force=False):
        if self.trending_reply is not None: return
        period = self.trending_period
        hit = self.trending_snapshots.get(period)
        if not force and hit and time.time() * 1000 - hit.get('fetchedAt', 0) < 600000:
            if self.view_mode == 'trending': self.show_trending()
            return
        self.trending_status = '正在同步 GitHub ' + PERIODS[period][0] + '…'
        request = QNetworkRequest(QUrl(BASE + f'/api/trending?period={period}&refresh={int(force)}'))
        request.setTransferTimeout(35000)
        reply = self.nam.get(request)
        self.trending_reply = reply
        if self.view_mode == 'trending': self.show_trending()
        def finished():
            if self.trending_reply is not reply:
                reply.deleteLater(); return
            self.trending_reply = None
            try:
                data = json.loads(bytes(reply.readAll()))
                if reply.error() != QNetworkReply.NetworkError.NoError or data.get('error'):
                    raise ValueError(data.get('error') or reply.errorString())
                if data.get('period') != period or not data.get('items'): raise ValueError('榜单周期或内容不完整')
                self.trending_snapshots[period] = data
                self.discovery.ingest(data['items'], 'GitHub ' + PERIODS[period][0])
                self.recommendations = self.discovery.recommend(topic=self.topic_override)
                self.trending_status = data.get('warning') or ('已读取 GitHub 缓存' if data.get('cached') else '已同步 GitHub')
                self.persist_discovery()
            except Exception as exc:
                self.trending_status = '同步失败 · ' + str(exc)[:120] + (' · 保留上次快照' if hit else '')
            finally:
                reply.deleteLater()
                if self.view_mode == 'trending': self.show_trending()
        reply.finished.connect(finished)

    def show_trending(self):
        from discovery_ui import text_label
        self.clear_cards()
        hero = QFrame(); hero.setObjectName('trendingHero')
        hero_layout = QVBoxLayout(hero); hero_layout.setContentsMargins(24, 20, 24, 20)
        hero_layout.addWidget(text_label('GITHUB / TRENDING', 'heroKicker'))
        hero_layout.addWidget(text_label('正在被发现的好项目', 'guideTitle'))
        hero_layout.addWidget(text_label('跟随 GitHub 热度榜，也可以从中挑选与你兴趣接近的项目。', 'dim', True))
        self.host_layout.addWidget(hero)
        controls = QHBoxLayout()
        self.period_buttons = {}
        for period, (name, _) in PERIODS.items():
            button = QPushButton(name); button.setObjectName('topicButton'); button.setCheckable(True)
            button.setChecked(period == self.trending_period)
            button.clicked.connect(lambda _, p=period: self.select_trending_period(p))
            self.period_buttons[period] = button; controls.addWidget(button)
        controls.addStretch()
        personal = QPushButton('按我的兴趣'); personal.setCheckable(True); personal.setChecked(self.trending_personalized)
        personal.setObjectName('topicButton'); personal.toggled.connect(self.personalize_trending); controls.addWidget(personal)
        sync = QPushButton('同步 GitHub'); sync.setObjectName('go'); sync.clicked.connect(lambda: self.fetch_trending(True))
        sync.setEnabled(self.trending_reply is None); controls.addWidget(sync)
        self.host_layout.addLayout(controls)
        data = self.trending_snapshots.get(self.trending_period) or {}
        rows = self.discovery.rank_trending(data.get('items') or [], self.trending_personalized)
        self.trending_visible = rows
        time_label = time.strftime('%m-%d %H:%M', time.localtime(data['fetchedAt']/1000)) if data.get('fetchedAt') else '尚未同步'
        source = self.trending_status or ('显示保存的 GitHub 快照' if data else '选择周期后从 GitHub 同步')
        self.host_layout.addWidget(text_label(f'{source}  ·  更新时间 {time_label}  ·  {len(rows)} 个项目', 'signal', True))
        if self.trending_personalized:
            info = '依据收藏主题、语言和最近搜索排序，右侧保留 GitHub 原榜名次。'
            if not self.discovery.interests(): info = '还没有兴趣信号，暂按 GitHub 原榜展示。搜索或收藏后会逐渐个性化。'
        else: info = '保持 GitHub 原榜顺序；新增星标来自所选周期，总星标单独列出。'
        self.host_layout.addWidget(text_label(info, 'dim', True))
        link = QPushButton('查看 GitHub 原榜  ↗'); link.setObjectName('ghost')
        link.clicked.connect(lambda: QDesktopServices.openUrl(QUrl('https://github.com/trending?since=' + self.trending_period)))
        self.host_layout.addWidget(link, 0, Qt.AlignLeft)
        if not rows:
            message = '正在连接 GitHub，首次同步可能需要几秒钟…' if self.trending_reply else '尚未取得榜单。请确认网络及 Windows 系统代理可用，再点击「同步 GitHub」。成功同步后会保留榜单，断网也能继续浏览。'
            self.host_layout.addWidget(text_label(message, 'emptyText', True))
        for index, repo in enumerate(rows, 1):
            frame = QFrame(); frame.setObjectName('rankingCard')
            layout = QHBoxLayout(frame); layout.setContentsMargins(20, 18, 20, 18); layout.setSpacing(18)
            rank = text_label(f'{index:02d}', 'rankingNumber'); rank.setFixedWidth(42); layout.addWidget(rank, 0, Qt.AlignTop)
            content = QVBoxLayout(); content.setSpacing(7)
            content.addWidget(text_label(repo['full_name'], 'projectTitle', True))
            content.addWidget(self.make_intro_label(repo))
            content.addWidget(self.original_description(repo))
            stars = f"{repo['stars']:,}" if repo.get('stars') is not None else '未提供'
            content.addWidget(text_label(f"总星标 {stars}  ·  {repo.get('lang') or '语言未标注'}  ·  GitHub 原榜 #{repo.get('trending_rank', index)}", 'projectMeta', True))
            if self.trending_personalized: content.addWidget(text_label(repo['interest_reason'], 'reason', True))
            actions = QHBoxLayout()
            for text, callback in [('看懂它', self.open_detail), ('已收藏' if any(f['full_name'] == repo['full_name'] for f in self.store.get('favs', [])) else '收藏', self.toggle_fav), ('已选对比' if repo['full_name'] in self.comparison else '加入对比', self.toggle_compare)]:
                button = QPushButton(text); button.setObjectName('ghost')
                button.clicked.connect(lambda _, r=repo, fn=callback: fn(r)); actions.addWidget(button)
            actions.addStretch(); content.addLayout(actions)
            layout.addLayout(content, 1)
            growth = repo.get('stars_period')
            metric = QVBoxLayout(); metric.addWidget(text_label(f'+{growth:,}' if growth is not None else '未提供', 'rankingGrowth'))
            metric.addWidget(text_label(PERIODS[self.trending_period][1], 'dim'))
            metric.addStretch(); layout.addLayout(metric)
            self.host_layout.addWidget(frame)
        self.host_layout.addStretch()
        self.persist_discovery()
        self.queue_introductions(rows)
