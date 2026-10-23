"""PyInstaller 运行时钩子：无控制台的 exe 也要能写日志。

放在 --runtime-hook，会在 Python 起来之后、主脚本之前执行。
windowed 引导器下 sys.stdout / sys.stderr 是 None，照原样赋值会把崩溃吞掉，
这里把它们接到 %TEMP%\\ghf-stdout.log，并打开 faulthandler 记录硬崩溃。
"""
import os
import sys
import tempfile

try:
    log_path = os.path.join(tempfile.gettempdir(), "ghf-stdout.log")
    _f = open(log_path, "a", encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = _f
    if sys.stderr is None:
        sys.stderr = _f
    try:
        import faulthandler

        faulthandler.enable(_f)
    except Exception:
        pass
    try:
        def _hook(t, v, tb):
            import traceback

            _f.write("".join(traceback.format_exception(t, v, tb)))
            _f.flush()

        sys.excepthook = _hook
    except Exception:
        pass
except Exception:
    pass
