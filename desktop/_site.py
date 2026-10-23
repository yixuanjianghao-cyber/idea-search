"""把用户级 site-packages 补进 sys.path。

这台机器的 PYTHONUSERBASE 指向别的盘，PySide6 却装在 C:\\Users\\...\\Roaming\\Python，
直接 `python run.py` 会报 ModuleNotFoundError。这里兜一层，别让启动成败取决于环境变量。
"""
from __future__ import annotations

import os
import sys


def ensure_site() -> None:
    try:
        import PySide6  # noqa: F401
        return
    except Exception:
        pass

    cands = []
    base = os.environ.get("PYTHONUSERBASE")
    tag = f"Python{sys.version_info[0]}{sys.version_info[1]}"
    if base:
        cands.append(os.path.join(base, tag, "site-packages"))
    home = os.path.expanduser("~")
    cands.append(os.path.join(home, "AppData", "Roaming", "Python", tag, "site-packages"))
    cands.append(os.path.join(os.path.dirname(sys.executable), "Lib", "site-packages"))
    for c in cands:
        if c and os.path.isdir(c) and c not in sys.path:
            sys.path.append(c)

    try:
        import PySide6  # noqa: F401
        sys.stderr.write(f"[site] PySide6 从 {PySide6.__file__} 补载成功\n")
    except Exception as e:
        sys.stderr.write(f"[site] 仍然找不到 PySide6：{e}\n")
