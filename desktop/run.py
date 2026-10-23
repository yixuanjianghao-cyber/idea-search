"""桌面端入口。

图形界面：  python run.py
自检模式：  python run.py --selftest "一句想法" [--shot out.png]
打包后的 exe 用法相同：想法搜索.exe --selftest "自托管的笔记软件"
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))



import tempfile  # noqa: E402

TRACE = Path(tempfile.gettempdir()) / "ghf-start.log"


def trace(msg: str) -> None:
    """启动轨迹：打包后没有控制台，出问题就看这个文件。"""
    try:
        with open(TRACE, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    except Exception:
        pass

from PySide6.QtCore import Qt, QTimer  # noqa: E402
from PySide6.QtGui import QFont, QIcon  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtNetwork import QNetworkProxyFactory  # noqa: E402


def build_app() -> QApplication:
    trace(f"build_app frozen={getattr(sys, 'frozen', False)} platform={os.environ.get('QT_QPA_PLATFORM')}")
    app = QApplication.instance() or QApplication(sys.argv)
    QNetworkProxyFactory.setUseSystemConfiguration(True)
    trace("QApplication ok")
    app.setApplicationName("IdeaSearch")
    app.setApplicationDisplayName("想法搜索")
    app.setOrganizationName("IdeaSearch")
    app.setApplicationVersion("2.8.0")
    asset_root = Path(getattr(sys, "_MEIPASS", HERE.parent))
    app.setWindowIcon(QIcon(str(asset_root / "assets" / "app.ico")))
    app.setStyle("Fusion")
    from theme import QSS

    app.setStyleSheet(QSS)
    app.setFont(QFont("Microsoft YaHei UI", 9))
    return app


def headless(query: str, shot: str | None = None, log: str | None = None) -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ['GHF_DISABLE_DISCOVERY'] = '1'
    os.environ['GHF_DISABLE_INTRO'] = '1'
    app = build_app()

    from engine import Engine
    from ui import MainWindow

    lines: list[str] = []

    def out(s: str) -> None:
        lines.append(s)
        try:
            print(s, flush=True)
        except Exception:
            pass

    eng = Engine()
    ok, msg = eng.ensure()
    out(f"engine={'ok' if ok else 'fail'} · {msg}")
    if not ok:
        _flush_log(lines, log)
        return 2

    win = MainWindow(eng)
    win.resize(1280, 840)
    win.show()
    win.search.setText(query)
    win.do_search()

    deadline = time.time() + 90
    while time.time() < deadline and not win.last_done:
        app.processEvents()
        time.sleep(0.05)
    for _ in range(40):
        app.processEvents()
        time.sleep(0.02)

    out(f"query={query}")
    out(f"done={win.last_done} results={len(win.items)} native={len(win.native)}")
    out(f"status={win.status.text()}")
    plan = win.plan or {}
    out(f"plan={plan.get('primary')} variants={[v.get('label') for v in plan.get('variants', [])]}")

    # 顺带验证「看懂它」：打一次 /api/analyze
    rows = win.visible()
    if rows:
        import json as _json
        import urllib.parse as _up
        import urllib.request as _ur
        from engine import BASE as _BASE

        try:
            url = f"{_BASE}/api/analyze?" + _up.urlencode({"repo": rows[0]["full_name"], "q": query})
            with _ur.urlopen(url, timeout=60) as r:
                d = _json.loads(r.read().decode("utf-8"))
            out(f"analyze={d.get('full_name')} how={d.get('how')} fit={(d.get('fit') or {}).get('level')}")
            out(f"what={(d.get('what') or '')[:70]}")
            out(f"steps={len(d.get('steps') or [])} commands={len(d.get('commands') or [])} deploy={(d.get('deploy') or {}).get('mode')}")
        except Exception as e:
            out(f"analyze_fail={e}")
    if shot:
        Path(shot).parent.mkdir(parents=True, exist_ok=True)
        win.grab().save(shot)
        out(f"shot={shot}")

    eng.stop()
    _flush_log(lines, log)
    return 0 if (win.last_done and len(win.items) > 0) else 1


def _flush_log(lines: list[str], log: str | None) -> None:
    """打包成无控制台的 exe 后，stdout 看不见，落一份文件。"""
    import tempfile

    path = Path(log) if log else Path(tempfile.gettempdir()) / "ghf-selftest.txt"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines), "utf-8")
    except Exception:
        pass


def main() -> int:
    trace(f"main start argv={sys.argv[1:]}")
    if "--selftest" in sys.argv:
        i = sys.argv.index("--selftest")
        query = sys.argv[i + 1] if len(sys.argv) > i + 1 else "自托管的笔记软件，支持双链"
        shot = None
        if "--shot" in sys.argv:
            j = sys.argv.index("--shot")
            shot = sys.argv[j + 1] if len(sys.argv) > j + 1 else "shot.png"
        log = None
        if "--log" in sys.argv:
            k = sys.argv.index("--log")
            log = sys.argv[k + 1] if len(sys.argv) > k + 1 else None
        return headless(query, shot, log)

    app = build_app()
    from engine import Engine
    from ui import MainWindow

    if "--smoke-test" in sys.argv:
        os.environ['GHF_DISABLE_DISCOVERY'] = '1'
        os.environ['GHF_DISABLE_INTRO'] = '1'
        engine = Engine()
        ok, message = engine.ensure()
        if not ok:
            trace(message)
            return 2
        win = MainWindow(engine)
        win.show()
        def finish():
            if "--shot" in sys.argv:
                path = Path(sys.argv[sys.argv.index("--shot") + 1])
                path.parent.mkdir(parents=True, exist_ok=True)
                win.grab().save(str(path))
            win.close()
            engine.stop()
            app.quit()
        QTimer.singleShot(800, finish)
        return app.exec()

    from instance import SingleInstance
    instance = SingleInstance()
    if not instance.acquire():
        return 0
    engine = Engine()
    win = MainWindow(engine)
    instance.connect(win)
    app.aboutToQuit.connect(engine.stop)
    app.aboutToQuit.connect(instance.close)
    win.show()
    win.btn_go.setEnabled(False)
    if '--configure-deepseek' in sys.argv:
        QTimer.singleShot(1200,lambda:win.open_ai_settings('deepseek'))
    win.status.setText("正在连接本地搜索引擎…")
    started = time.monotonic()
    timer = QTimer(win)
    def ready():
        ok, message = engine.ensure(wait_s=0)
        if ok:
            timer.stop()
            win.btn_go.setEnabled(True)
            win.status.setText("准备好了。输入需求开始搜索。")
            win.refresh_health()
        elif time.monotonic() - started > 12:
            timer.stop()
            win.status.setText(message)
    timer.timeout.connect(ready)
    timer.start(250)
    return app.exec()



if __name__ == "__main__":
    raise SystemExit(main())
