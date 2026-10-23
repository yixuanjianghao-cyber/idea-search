"""扫描本机环境：给 AI 助手和「适不适合我」判断用。

注意：Windows 上 powershell.exe 的中文输出默认是 GBK，直接按 UTF-8 解会炸，
所以这里先拿 bytes，再依次试 utf-8 / gbk。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

CACHE = Path(os.environ.get("GHF_DATA_DIR") or Path.home()) / ".github-finder-env.json"
TTL = 6 * 3600
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _decode(raw: bytes) -> str:
    for enc in ("utf-8", "gbk", "cp936", "latin-1"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", "replace")


def _run_lines(args: list[str], timeout: float = 8.0) -> list[str]:
    try:
        p = subprocess.run(args, capture_output=True, timeout=timeout, creationflags=CREATE_NO_WINDOW)
        text = _decode((p.stdout or b"") + (b"\n" + p.stderr if p.stderr else b""))
        return [ln.strip() for ln in text.splitlines() if ln.strip()]
    except Exception:
        return []


def _run(args: list[str], timeout: float = 6.0) -> str:
    lines = _run_lines(args, timeout)
    return lines[0] if lines else ""


def _ps_lines(cmd: str) -> list[str]:
    return _run_lines(["powershell", "-NoProfile", "-Command",
                       "$OutputEncoding=[Console]::OutputEncoding=[Text.Encoding]::UTF8;" + cmd])


def _ps(cmd: str) -> str:
    lines = _ps_lines(cmd)
    return lines[0] if lines else ""


TOOLS = [
    ("node", ["node", "-v"]),
    ("python", ["python", "-V"]),
    ("git", ["git", "--version"]),
    ("docker", ["docker", "--version"]),
    ("ffmpeg", ["ffmpeg", "-version"]),
    ("go", ["go", "version"]),
    ("cargo", ["cargo", "--version"]),
    ("java", ["java", "-version"]),
    ("adb", ["adb", "version"]),
    ("ollama", ["ollama", "--version"]),
    ("pnpm", ["pnpm", "-v"]),
    ("uv", ["uv", "--version"]),
    ("7z", ["7z"]),
]


def scan(force: bool = False) -> dict:
    if not force and CACHE.exists():
        try:
            data = json.loads(CACHE.read_text("utf-8"))
            if time.time() - data.get("at", 0) < TTL:
                return data
        except Exception:
            pass

    # The UI performs a cheap PATH scan only. Hardware/version probing is opt-in.
    if not force:
        return {"at": time.time(), "os": "Windows", "cpu": "未检测", "ram_gb": "未核验",
                "gpus": [], "vram": "", "disk_free_gb": round(shutil.disk_usage(Path.home()).free / 1024**3, 1),
                "tools": {name: ("已检测到（版本未核验）" if shutil.which(cmd[0]) else None) for name, cmd in TOOLS}}
    tools = {}
    for name, cmd in TOOLS:
        if not shutil.which(cmd[0]):
            tools[name] = None
            continue
        tools[name] = (_run(cmd, timeout=8) or "已安装")[:70]

    os_name = _ps("(Get-CimInstance Win32_OperatingSystem).Caption") or "Windows"
    cpu = _ps("(Get-CimInstance Win32_Processor).Name").split("  ")[0]

    ram_gb = 0.0
    try:
        ram_gb = round(int(_ps("(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory")) / 1024 ** 3, 1)
    except Exception:
        pass

    gpus = []
    try:
        gpus = [g for g in _ps_lines("(Get-CimInstance Win32_VideoController).Name")
                if g and not g.lower().startswith("microsoft basic")]
    except Exception:
        pass
    # 优先把独立显卡放前面
    gpus.sort(key=lambda g: 0 if any(k in g.upper() for k in ("NVIDIA", "RADEON RX", "ARC ")) else 1)

    vram = ""
    try:
        v = _run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"], timeout=6)
        if v:
            vram = v.strip()
    except Exception:
        pass

    if vram and not gpus:
        gpus = [vram.split(',')[0].strip()]

    disk_free = 0.0
    try:
        disk_free = round(shutil.disk_usage("C:\\").free / 1024 ** 3, 1)
    except Exception:
        pass

    data = {
        "at": time.time(),
        "os": os_name,
        "cpu": cpu,
        "ram_gb": ram_gb,
        "gpus": gpus,
        "vram": vram,
        "disk_free_gb": disk_free,
        "tools": tools,
    }
    try:
        CACHE.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
    except Exception:
        pass
    return data


def summary(env: dict) -> str:
    t = env.get("tools") or {}
    has = [k for k, v in t.items() if v]
    lack = [k for k, v in t.items() if not v]
    gpu = ", ".join(env.get("gpus") or []) or "未检测"
    return (f"{(env.get('os') or 'Windows').strip()} · {(env.get('cpu') or '').strip()} · "
            f"内存 {env.get('ram_gb', '未核验')} · {gpu} · 已装 {', '.join(has) or '无'} · "
            f"没装 {', '.join(lack) or '无'}")


def prompt_block(env: dict) -> str:
    t = env.get("tools") or {}
    have = ", ".join(f"{k}（{v}）" for k, v in t.items() if v) or "无"
    miss = ", ".join(k for k, v in t.items() if not v) or "无"
    return (
        f"- 操作系统：{(env.get('os') or 'Windows').strip()}\n"
        f"- CPU：{(env.get('cpu') or '').strip()}；内存：{env.get('ram_gb', 0)} GB；C 盘剩余：{env.get('disk_free_gb', 0)} GB\n"
        f"- 显卡：{', '.join(env.get('gpus') or []) or '未知'}"
        + (f"（{env['vram']}）" if env.get("vram") else "") + "\n"
        f"- 已安装：{have}\n"
        f"- 未安装：{miss}\n"
    )


def check_needs(env: dict, needs: list[str]) -> list[dict]:
    t = env.get("tools") or {}
    out = []
    for n in needs or []:
        low = n.lower()
        ok, fix = None, "尚未核验"
        required_tool = next((tool for tool in ("docker", "python", "node", "git", "go", "cargo", "java") if tool in low), None)
        if required_tool:
            if t.get(required_tool):
                ok, fix = None, "工具已检测到；版本和服务状态未核验"
            else:
                ok, fix = False, f"没检测到 {required_tool}"
        elif "显卡" in n or "gpu" in low or "cuda" in low:
            ok, fix = None, "显卡型号、显存和 CUDA 兼容性需核验"
        elif "数据库" in n:
            ok, fix = None, "数据库连接未验证"
        elif "key" in low or "账号" in n:
            ok, fix = None, "需自行配置账号或 API key"
        out.append({"need": n, "ok": ok, "fix": fix})
    return out
