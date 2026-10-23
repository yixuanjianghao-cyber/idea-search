"""配额用光时，用搜索结果里已有的信息拼一份「简版解读」。"""
from __future__ import annotations

import re
import time


def _ago(iso: str | None) -> str:
    if not iso:
        return "未知"
    try:
        ts = time.mktime(time.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S"))
    except Exception:
        return "未知"
    d = (time.time() - ts) / 86400
    if d < 30:
        return f"{int(d)} 天前"
    if d < 365:
        return f"{int(d/30)} 个月前"
    return f"{int(d/365)} 年前"


def guess_kind(repo: dict) -> tuple[str, str]:
    name = (repo.get("full_name") or "").lower()
    desc = (repo.get("description") or "").lower()
    topics = " ".join(repo.get("topics") or []).lower()
    blob = f"{name} {desc} {topics}"
    if re.search(r'\bcookbooks?\b|code examples|示例合集|代码示例', name + ' ' + desc):
        return 'examples', '看起来是代码示例与教程合集；需读取对应案例的说明后使用'
    if re.search(r"prompt|jailbreak|提示词|破甲", blob):
        return "prompts", "看着像提示词/文本合集：不用装，复制就能用"
    if re.search(r"awesome|curated|清单", blob):
        return "awesome", "看着像清单/合集：没有东西可装，翻目录挑项目"
    if re.search(r"dataset|corpus|数据集", blob):
        return "dataset", "看着像数据集：下载下来喂程序用"
    if re.search(r"vscode|chrome|extension|plugin|插件|油猴", blob):
        return "plugin", "看着像插件：装进你已有的软件里用"
    if repo.get("topics") and any(t in topics for t in ("cli", "command-line")):
        return "cli", "看着像命令行工具：装完在终端敲名字"
    return "unknown", "搜索结果里只有简介，没有 README，具体怎么跑得点开仓库看"


def build_brief(repo: dict, query: str = "", reason: str = "") -> dict:
    kind, hint = guess_kind(repo)
    desc = repo.get("description") or "（搜索结果里没有描述）"
    stars = repo.get("stars") or 0
    lang = repo.get("lang") or "未知"
    lic = repo.get("license") or "无"
    pushed = repo.get("pushed_at")

    fit_reasons = [f"{stars} 星" if stars else "星很少", f"最近更新：{_ago(pushed)}"]
    if lic == "无":
        fit_reasons.append("没有许可证，商用前要问作者")

    steps = ["点右上角「打开仓库」", "读 README 前 30 行（作者一般写在这）",
             "看有没有 Releases / 安装包可以直接下"]
    if kind == "prompts":
        steps = ["打开仓库，找 prompts / examples 目录", "挑一份，整段复制", "贴到你要用的模型里"]
    elif kind == "awesome":
        steps = ["打开仓库，看目录索引", "挑你需要的那个项目", "点进去看它自己的 README"]
    elif kind == 'examples':
        steps = ['打开仓库，选择一个案例或 Notebook', '核对该案例的说明、依赖与配置', '按案例说明运行和修改']

    return {
        "full_name": repo.get("full_name"),
        "html_url": repo.get("html_url"),
        "what": desc,
        "readme": "",
        "kind": kind,
        "kindHint": hint,
        "degraded": True,
        "degradedReason": reason,
        "fit": {"level": "maybe", "reasons": fit_reasons},
        "estimate": "要联网查了才知道",
        "needs": [],
        "stack": [lang] if lang != "未知" else [],
        "headings": [],
        "files": [],
        "manifest": {},
        "size": repo.get("size") or 0,
        "issues": repo.get("issues") or 0,
        "stars": stars,
        "license": None if lic == "无" else lic,
        "steps": steps,
        "commands": [],
        "deploy": {"mode": "unknown", "script": "", "notes": ["简化模式：不生成部署脚本"]},
        "risks": ["没说清怎么装"] if kind == "unknown" else [],
        "cached": False,
        "quotaNote": "这是简版：GitHub 配额用光（或没网），没用 README 分析。",
    }
