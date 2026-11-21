#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 README 骨架。

用法：
    python make_readme.py <项目路径> --name "项目名" [--desc "一句话"] [--dry]
    python make_readme.py . --name bili-whale --desc "让 AI 自己刷 B 站"

设计原则：
  - 只写能从仓库里**读出来**的事实（包名、脚本命令、目录、许可证、已有截图）。
  - 读不出来的（一句话定位、功能列表）用诚实的默认句式，并在 stderr 列出
    「还需要你补哪几句」，**不往文件里塞 TODO 占位符**（审计器会拦）。
  - 已有 README 时不覆盖，除非 --force。
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

SHOT_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp")


def detect_stack(root: Path):
    """返回 (语言, 安装命令, 启动命令, 构建命令)。读不出来就给 None。"""
    pkg = root / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        scripts = data.get("scripts") or {}
        pm = "pnpm" if (root / "pnpm-lock.yaml").exists() else (
            "yarn" if (root / "yarn.lock").exists() else "npm")
        install = {"npm": "npm install", "pnpm": "pnpm install", "yarn": "yarn"}[pm]
        run = None
        for key in ("dev", "start", "serve"):
            if key in scripts:
                run = {"npm": f"npm run {key}", "pnpm": f"pnpm {key}", "yarn": f"yarn {key}"}[pm]
                break
        build = None
        if "build" in scripts:
            build = {"npm": "npm run build", "pnpm": "pnpm build", "yarn": "yarn build"}[pm]
        return ("Node.js", install, run, build)

    for marker, lang, install, run, build in (
        ("pyproject.toml", "Python", "pip install -e .", None, None),
        ("requirements.txt", "Python", "pip install -r requirements.txt", "python main.py", None),
        ("Cargo.toml", "Rust", "cargo build --release", "cargo run", "cargo build --release"),
        ("go.mod", "Go", "go mod download", "go run .", "go build"),
    ):
        if (root / marker).exists():
            return (lang, install, run, build)

    if any(root.glob("*.html")):
        return ("静态 HTML", None, "直接用浏览器打开 index.html", None)
    return (None, None, None, None)


def find_screenshot(root: Path):
    """在根和 docs/ 下找第一张图片，返回相对路径。"""
    for d in (root, root / "docs", root / "assets", root / "screenshots"):
        if not d.is_dir():
            continue
        for f in sorted(d.iterdir()):
            if f.suffix.lower() in SHOT_EXTS and f.is_file():
                return f.relative_to(root).as_posix()
    return None


def detect_license(root: Path):
    for name in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING"):
        f = root / name
        if f.exists():
            try:
                head = f.read_text(encoding="utf-8", errors="ignore")[:400]
            except Exception:
                return "见 LICENSE"
            if "MIT License" in head or "MIT" in head[:80]:
                return "MIT"
            if "Apache License" in head:
                return "Apache-2.0"
            if "GNU AFFERO" in head.upper():
                return "AGPL-3.0"
            if "GNU GENERAL PUBLIC" in head.upper():
                return "GPL-3.0"
            return "见 LICENSE"
    return None


def detect_repo(root: Path):
    """从 git remote 猜 owner/repo。"""
    import subprocess
    try:
        url = subprocess.run(["git", "remote", "get-url", "origin"], cwd=root,
                             capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        return (None, None)
    m = re.search(r"github\.com[:/]([^/]+)/([^/.]+)", url)
    if m:
        return (m.group(1), m.group(2))
    return (None, None)


def top_dirs(root: Path, limit=8):
    skip = {"node_modules", ".git", "dist", "build", "out", "target", "__pycache__",
            ".venv", "venv", ".next", ".cache", "release", ".publish", ".github"}
    out = []
    for f in sorted(root.iterdir()):
        if f.is_dir() and f.name not in skip and not f.name.startswith("."):
            out.append(f.name)
    return out[:limit]


def build_readme(root: Path, name: str, desc: str, owner=None, repo=None):
    lang, install, run, build = detect_stack(root)
    shot = find_screenshot(root)
    lic = detect_license(root)
    if owner is None or repo is None:
        o, r = detect_repo(root)
        owner = owner or o
        repo = repo or r

    L = []
    L.append(f"# {name}")
    L.append("")
    L.append(desc)
    L.append("")
    if shot:
        L.append(f"![{name} 界面]({shot})")
        L.append("")

    links = []
    if owner and repo:
        links.append(f"[在线试用](https://{owner}.github.io/{repo}/)")
        links.append(f"[下载最新版](https://github.com/{owner}/{repo}/releases/latest)")
        links.append(f"[源码](https://github.com/{owner}/{repo})")
    L.append(" · ".join(links) if links else "<!-- 仓库还没建：建好后把在线试用/下载链接补在这里 -->")
    L.append("")

    L.append("## 这是什么")
    L.append("")
    L.append(desc)
    L.append("")
    L.append("适合谁用：")
    L.append("")
    L.append("- ")
    L.append("")
    L.append("不适合什么：")
    L.append("")
    L.append("- ")
    L.append("")

    L.append("## 快速开始")
    L.append("")
    if install or run:
        L.append("```bash")
        if owner and repo:
            L.append(f"git clone https://github.com/{owner}/{repo}.git")
            L.append(f"cd {repo}")
        if install:
            L.append(install)
        if run:
            L.append(run)
        L.append("```")
        L.append("")
    elif lang == "静态 HTML":
        L.append("用浏览器直接打开 `index.html`，或起一个本地服务：")
        L.append("")
        L.append("```bash")
        L.append("python -m http.server 8000")
        L.append("```")
        L.append("")
    if build:
        L.append(f"构建：`{build}`")
        L.append("")

    L.append("## 截图")
    L.append("")
    if shot:
        L.append(f"![{name}]({shot})")
        L.append("")
        L.append("上面这张展示的是：<!-- 用一句话说清这张图里在发生什么 -->")
    else:
        L.append("<!-- 放 2–4 张截图；没有截图的项目很少有人愿意下载 -->")
    L.append("")

    dirs = top_dirs(root)
    if dirs:
        L.append("## 目录")
        L.append("")
        L.append("```")
        L.append(f"{name}/")
        for d in dirs:
            L.append(f"├── {d}/")
        L.append("```")
        L.append("")

    L.append("## 常见问题")
    L.append("")
    L.append("**Q：需要联网吗？**")
    L.append("")
    L.append("A：")
    L.append("")
    L.append("**Q：会不会上传我的数据？**")
    L.append("")
    L.append("A：")
    L.append("")

    L.append("## 开发")
    L.append("")
    L.append(f"技术栈：{lang or '<!-- 填 -->'}")
    L.append("")
    L.append("```bash")
    if install:
        L.append(install)
    if run:
        L.append(run)
    L.append("```")
    L.append("")

    L.append("## 许可")
    L.append("")
    L.append(f"{lic or '<!-- 还没有 LICENSE，选一个：MIT / Apache-2.0 / AGPL-3.0 -->'}")
    L.append("")

    return "\n".join(L), (lang, shot, lic)


def main():
    ap = argparse.ArgumentParser(description="生成 README 骨架")
    ap.add_argument("path", help="项目目录")
    ap.add_argument("--name", required=True, help="项目名（用在标题和徽章里）")
    ap.add_argument("--desc", default="一句话说清这是什么。", help="一句话定位，≤20 字最好")
    ap.add_argument("--owner", help="GitHub 用户名（不填则从 git remote 猜）")
    ap.add_argument("--repo", help="仓库名（不填则从 git remote 猜）")
    ap.add_argument("--force", action="store_true", help="覆盖已存在的 README.md")
    ap.add_argument("--dry", action="store_true", help="只打印，不写文件")
    args = ap.parse_args()

    # Windows 控制台默认 GBK，中文会变乱码；强制 UTF-8 输出
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass

    root = Path(args.path).expanduser().resolve()
    if not root.is_dir():
        print(f"✗ 不是目录：{root}", file=sys.stderr)
        return 3

    target = root / "README.md"
    if target.exists() and not args.force and not args.dry:
        print(f"✗ README.md 已存在。要覆盖请加 --force（或先 git mv 备份）", file=sys.stderr)
        return 3

    text, (lang, shot, lic) = build_readme(root, args.name, args.desc, args.owner, args.repo)

    if args.dry:
        print(text)
        return 0

    target.write_text(text, encoding="utf-8")
    print(f"✓ 写入 {target}")

    todo = []
    if not shot:
        todo.append("没有截图：放 2–4 张到 docs/ 并在 README 里引用")
    if not lic:
        todo.append("没有 LICENSE：选一个许可证（MIT 最宽松，AGPL 最防闭源商用）")
    if lang is None:
        todo.append("没识别出技术栈：手工补「开发」一节的安装/启动命令")
    todo.append("补完「这是什么」下面的「适合谁用 / 不适合什么」两条")
    todo.append("补完「常见问题」的答案（写真实会被问到的，别写凑数的）")
    todo.append("删掉没用的空小节，别留空标题")

    print("\n还需要你补：", file=sys.stderr)
    for i, t in enumerate(todo, 1):
        print(f"  {i}. {t}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
