"""深色主题 QSS。"""
QSS = """
* { font-family: "Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei", sans-serif; font-size: 13px; }
QMainWindow, QDialog, QStackedWidget { background: #0b0f14; }
QWidget { color: #e6edf3; }
QLabel { background: transparent; }
QLabel#title { font-size: 17px; font-weight: 700; letter-spacing: .4px; }
QLabel#title span { color: #3fb950; }
QLabel#sub { color: #5d6b7a; font-size: 11px; }
QLabel#badge {
    color: #8b98a5; border: 1px solid #1f2a37; border-radius: 10px;
    padding: 3px 10px; font-size: 11px;
}
QLabel#badge[warn="true"] { color: #d29922; }
QLabel#panelTitle { color: #91a4bb; font-size: 12px; font-weight: 700; letter-spacing: 1px; }
QLabel#dim { color: #8b98a5; font-size: 11px; }
QLabel#status { color: #8b98a5; font-size: 11px; }

QLineEdit, QComboBox, QSpinBox {
    background: #121a24; border: 1px solid #1f2a37; border-radius: 9px;
    padding: 6px 10px; selection-background-color: #1f6feb; color: #e6edf3;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: #58a6ff; }
QLineEdit#search {
    font-size: 15px; padding: 11px 14px; border-radius: 12px; background: #0f1620;
}
QLineEdit#search:focus { border-color: #58a6ff; }
QComboBox::drop-down { border: 0; width: 18px; }
QComboBox QAbstractItemView {
    background: #16202c; border: 1px solid #1f2a37; selection-background-color: #1f6feb;
    outline: none; padding: 4px;
}
QComboBox::down-arrow { image: none; border-left: 4px solid transparent; border-right: 4px solid transparent;
    border-top: 5px solid #8b98a5; margin-right: 6px; }
QSpinBox::up-button, QSpinBox::down-button { width: 0; border: 0; }

QPushButton {
    background: #16202c; border: 1px solid #1f2a37; border-radius: 9px;
    padding: 7px 14px; color: #cdd7e1;
}
QPushButton:hover { border-color: #2c3a4b; color: #ffffff; }
QPushButton:pressed { background: #1b2734; }
QPushButton#go {
    background: #238636; border: 0; color: #ffffff; font-weight: 700;
    padding: 11px 26px; border-radius: 11px; font-size: 14px;
}
QPushButton#go:hover { background: #2ea043; }
QPushButton#go:disabled { background: #1c3a26; color: #7d9a86; }
QPushButton#ghost { background: transparent; border: 1px solid #1f2a37; color: #8b98a5; padding: 5px 10px; }
QPushButton#ghost:hover { color: #e6edf3; }
QPushButton#star { background: transparent; border: 0; color: #d29922; font-size: 15px; padding: 2px 6px; }
QPushButton#star:hover { color: #f0b429; }

QCheckBox { color: #8b98a5; font-size: 12px; spacing: 6px; }
QCheckBox::indicator { width: 14px; height: 14px; border-radius: 4px; border: 1px solid #2c3a4b; background: #0f1620; }
QCheckBox::indicator:checked { background: #2ea043; border-color: #2ea043; }

QFrame#panel { background: #121a24; border: 1px solid #1f2a37; border-radius: 12px; }
QFrame#card { background: #121a24; border: 1px solid #1f2a37; border-radius: 12px; }
QFrame#card:hover { border-color: #2c3a4b; background: #131c27; }
QFrame#hline { background: #1a2431; max-height: 1px; border: 0; }

QScrollArea { border: 0; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #22303f; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #2e4256; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

QProgressBar { background: #16202c; border: 0; border-radius: 2px; height: 4px; text-align: center; }
QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3fb950, stop:1 #58a6ff); border-radius: 2px; }

QTabWidget::pane { border: 1px solid #1f2a37; border-radius: 10px; top: -1px; }
QTabBar::tab {
    background: transparent; color: #5d6b7a; padding: 6px 14px; border: 0; font-size: 12px;
}
QTabBar::tab:selected { color: #e6edf3; border-bottom: 2px solid #3fb950; }
QListWidget { background: transparent; border: 0; outline: none; font-size: 12px; }
QListWidget::item { padding: 5px 4px; color: #b6c2ce; border-bottom: 1px dashed #172130; }
QListWidget::item:hover { color: #ffffff; }
QListWidget::item:selected { background: #16202c; color: #ffffff; }

QToolTip { background: #16202c; color: #e6edf3; border: 1px solid #1f2a37; padding: 5px 8px; }
QProgressBar#thin { max-height: 4px; }
QMenu { background: #16202c; border: 1px solid #1f2a37; }
QMenu::item:selected { background: #1f6feb; }
"""

# Discovery visual system: ink, violet and mint; typography and cards share a rhythm.
QSS += """
QMainWindow, QDialog, QStackedWidget, QWidget#appShell { background:#10111b; }
QFrame#navigation { background:#161724; border-right:1px solid #292a3c; }
QLabel#brand { font-size:20px; font-weight:700; color:#efeaff; }
QLabel#eyebrow { font-size:10px; color:#7d7e99; letter-spacing:1.4px; padding:4px 0; }
QPushButton#navButton { text-align:left; background:transparent; border:0; padding:13px 12px; color:#9699b2; font-size:14px; border-radius:10px; }
QPushButton#navButton:hover { color:#ded7ff; background:#202135; }
QPushButton#navButton:checked { color:#e0d7ff; background:#322b4e; border:1px solid #494069; }
QPushButton#navTopic { text-align:left; background:transparent; border:0; color:#9295b0; padding:10px 0; }
QPushButton#navTopic:hover { color:#c4b6ff; }
QLabel#title { font-size:15px; color:#b4b7cf; font-weight:500; }
QLabel#dim { color:#9397b0; font-size:12px; }
QLineEdit#search { background:#1b1d2e; border:1px solid #36374f; border-radius:14px; font-size:16px; padding:15px 18px; }
QLineEdit#search:focus { border:1px solid #ad99ff; }
QPushButton#go { background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #a58af6,stop:1 #7760d3); border-radius:12px; color:#fff; padding:13px 25px; }
QPushButton#go:hover { background:#a48bf0; }
QPushButton#go:disabled { background:#39324e; color:#8c829f; }
QPushButton#ghost { color:#a9abc3; border-color:#35364d; padding:7px 11px; }
QPushButton#ghost:hover { background:#28263c; border-color:#776693; }
QFrame#hero { background:qlineargradient(x1:0,y1:0,x2:1,y2:.8,stop:0 #2c2547,stop:.55 #282640,stop:1 #192e38); border:1px solid #49415f; border-radius:22px; }
QLabel#heroKicker { font-size:11px; color:#c0afea; letter-spacing:2px; }
QLabel#heroTitle { font-size:30px; font-weight:700; color:#faf7ff; }
QLabel#heroSubtitle { font-size:13px; color:#bbb5d1; }
QPushButton#heroSecondary { background:#36304a; border:1px solid #5d526f; border-radius:12px; padding:12px 17px; color:#e8dcff; }
QLabel#sectionTitle { color:#ebe9f7; font-size:19px; font-weight:600; padding:6px 0; }
QLabel#signal { color:#8f9db5; font-size:11px; padding:0 0 5px 0; }
QPushButton#topicButton { background:#1d1f2f; border:1px solid #36364d; border-radius:14px; padding:10px 13px; }
QPushButton#topicButton:hover, QPushButton#topicButton:checked { background:#35304c; border-color:#8c77b8; }
QFrame#discoveryCard { background:#1b1d2c; border:1px solid #303247; border-radius:17px; }
QFrame#discoveryCard:hover { background:#202234; border-color:#77669e; }
QLabel#projectTitle { font-size:15px; font-weight:600; color:#eeeaf9; }
QLabel#projectDescription { font-size:12px; color:#aaafc5; }
QLabel#projectMeta { font-size:11px; color:#bbb0ce; }
QLabel#reason { font-size:11px; color:#84cdbf; }
QPushButton#tilePrimary { background:#343049; border:1px solid #594c78; color:#ddd0ff; padding:7px 12px; border-radius:8px; }
QPushButton#tilePrimary:hover { background:#514165; }
QPushButton#tileAction { background:transparent; border:1px solid #36394e; color:#aeb2c9; padding:7px 10px; border-radius:8px; }
QPushButton#tileAction:hover { color:#e7defb; border-color:#8f7bb1; }
QPushButton#dismiss { background:transparent; border:0; color:#737790; font-size:20px; padding:0; min-width:22px; }
QPushButton#dismiss:hover { color:#ffadbf; }
QPushButton#seedButton { text-align:left; background:#1e2331; border:1px solid #34404f; border-radius:10px; padding:14px; color:#bdd2d6; }
QPushButton#seedButton:hover { border-color:#69bbaa; }
QFrame#emptyDiscovery { background:#1b1f2c; border:1px dashed #46435f; border-radius:16px; }
QLabel#emptyText { color:#9da3bf; padding:40px; font-size:15px; }
QPushButton#railProject { text-align:left; background:transparent; border:0; color:#bcb0ef; padding:8px 0; font-size:11px; }
QFrame#panel, QFrame#card { background:#1b1e2e; border:1px solid #30334b; border-radius:15px; }
QFrame#card:hover { background:#202538; border-color:#6b5b91; }
QTableWidget#comparisonTable { background:#1c1e2d; alternate-background-color:#222437; border:1px solid #373a50; gridline-color:#34364c; color:#d9d8e7; selection-background-color:#3f355b; }
QHeaderView::section { background:#2c2942; color:#d5c9f2; padding:12px; border:1px solid #3c3656; font-size:12px; }
QHeaderView { background:#1c1e2d; }
QTableCornerButton::section { background:#2c2942; border:1px solid #3c3656; }
QFrame#projectOverview { background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #27233c,stop:1 #182b32); border:1px solid #49405f; border-radius:16px; }
QLabel#guideBadge { background:#3c3358; color:#d3c0ff; padding:5px 10px; border-radius:8px; font-size:11px; }
QLabel#guideTitle { font-size:21px; font-weight:700; color:#f4efff; }
QSplitter::handle { background:#252638; }
QSplitter::handle:horizontal { width:8px; }
QSplitter::handle:vertical { height:8px; }
QFrame#trendingHero { background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #312640,stop:1 #18323b); border:1px solid #4d3d61; border-radius:16px; }
QFrame#rankingCard { background:#1c1e2e; border:1px solid #34344b; border-radius:14px; }
QFrame#rankingCard:hover { border-color:#8d76b0; }
QLabel#rankingNumber { color:#aa95eb; font-size:27px; font-weight:700; }
QLabel#rankingGrowth { color:#83ddbf; font-size:24px; font-weight:700; }
QLabel#chineseIntro { color:#d7d5e9; font-size:13px; }
QLabel#originalDescription { color:#9299af; font-size:11px; }
QPushButton#originalToggle { background:transparent; border:0; color:#8d96b3; text-align:left; padding:0; font-size:11px; }
QPushButton#originalToggle:checked { color:#bdadf3; }
QTabBar::tab:selected { border-bottom:2px solid #a991ed; }
QScrollBar::handle:vertical { background:#3c3857; }
QProgressBar::chunk { background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #b698f7,stop:1 #78d8c3); }
"""
