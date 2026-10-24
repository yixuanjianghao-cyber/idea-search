"""引擎进程管理：优先复用已在跑的 Node 服务，没有就自己拉一个。"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from network_config import engine_environment
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOST = "127.0.0.1"
def choose_port():
    requested = os.environ.get('GHF_PORT')
    if requested:
        port = int(requested)
        if not 1 <= port <= 65535: raise ValueError('GHF_PORT 必须在 1 到 65535 之间')
        return port
    with socket.socket() as probe:
        try: probe.bind((HOST, 17890))
        except OSError:
            probe.bind((HOST, 0))
        return probe.getsockname()[1]

PORT = choose_port()
BASE = f"http://{HOST}:{PORT}"


def app_root() -> Path:
    """打包后引擎文件在 PyInstaller 的解包目录里，源码运行时在仓库根。"""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return ROOT


def port_open(timeout: float = 0.25) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex((HOST, PORT)) == 0


def http_json(path: str, data: dict | None = None, timeout: float = 5.0):
    url = BASE + path
    if data is None:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
    else:
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json", "Accept": "application/json"}
        )
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def health():
    try:
        data = http_json("/api/health", timeout=1.0)
        return data if data.get("app") == "idea-search" and data.get("version") == "2.8.1" else None
    except Exception:
        return None


class Engine:
    """管理 node server.mjs 的生命周期。"""

    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None
        self.owned = False

    def ensure(self, wait_s: float = 12.0) -> tuple[bool, str]:
        if self.proc is not None and self.proc.poll() is not None:
            self.proc = None
        if port_open() and health():
            self.owned = self.proc is not None
            return True, "本地引擎已连接"

        if not port_open() and self.proc is None:
            node = self._find_node()
            if not node:
                return False, "缺少 Node 引擎，请重新完整解压发布包（不要只复制 EXE）"
            root = app_root()
            script = root / "server.mjs"
            if not script.exists():
                return False, f"找不到服务脚本：{script}"
            flags = 0
            if sys.platform == "win32":
                flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            try:
                self.proc = subprocess.Popen(
                [node, str(script)],
                cwd=str(root),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=flags,
                env={**engine_environment(), "PORT": str(PORT), "HOST": HOST},
                )
            except OSError as exc:
                return False, f"本地引擎无法启动：{exc}。请确认发布包已完整解压。"
            self.owned = True

        if health():
            return True, "已启动本地引擎"
        deadline = time.time() + wait_s
        while time.time() < deadline:
            if port_open() and health():
                return True, "已启动本地引擎"
            time.sleep(0.2)
        return False, "引擎启动超时或端口被其他程序占用；请查看诊断日志"

    def stop(self) -> None:
        if self.proc and self.owned and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=3)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass

    @staticmethod
    def _find_node() -> str | None:
        env = os.environ.get("GHF_NODE")
        if env and Path(env).exists():
            return env
        # 打包版：优先用随包带的 node.exe
        bundled = app_root() / "node.exe"
        if bundled.exists():
            return str(bundled)
        from shutil import which

        for name in ("node.exe", "node"):
            p = which(name)
            if p:
                return p
        for cand in (
            r"C:\Program Files\nodejs\node.exe",
            r"C:\Program Files (x86)\nodejs\node.exe",
        ):
            if Path(cand).exists():
                return cand
        return None
