#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""repo-publish 审计器：上传前的合格线检查。

用法：
    python audit.py <项目路径>                 # 只读审计（默认 --dry）
    python audit.py <项目路径> --write-report  # 落盘 report.md / report.json
    python audit.py <项目路径> --json          # 只输出 json

退出码：
    0  PASS（可以进入下一步）
    1  WARN（需要逐条确认）
    2  BLOCK（禁止上传，先修）
    3  参数/环境错误

设计约束（本机实测，改动前先读）：
  - 不依赖 gitleaks / trufflehog / detect-secrets —— 本机都没有，正则自实现。
  - 不遍历 .git 内部；历史扫描只走 `git log --all -p` 的有界前 N 个提交。
  - 只读；除 --write-report 外不写任何文件。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

MAX_FILE_BYTES = 50 * 1024 * 1024        # 单文件硬上限
WARN_REPO_BYTES = 200 * 1024 * 1024      # 仓库总体积警戒线
HISTORY_COMMITS = 40                     # 历史扫描的有界窗口
BIG_BLOB_WARN = 5 * 1024 * 1024

# ── 密钥正则表（与 references/secret-patterns.md 保持同一份）────────────
SECRET_PATTERNS: list[tuple[str, str, str]] = [
    ("github_pat",  r"github_pat_[A-Za-z0-9_]{22,}", "GitHub 细粒度 PAT"),
    ("github_tok",  r"\bgh[pousr]_[A-Za-z0-9]{36}\b", "GitHub 经典 token"),
    ("aws_key",     r"\bAKIA[0-9A-Z]{16}\b", "AWS Access Key ID"),
    ("private_key", r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "私钥文件内容"),
    ("bili_sessdata", r"SESSDATA=[A-Za-z0-9%]{25,}", "B 站登录 cookie"),
    ("bili_jct",    r"bili_jct=[0-9a-f]{28,}", "B 站 CSRF token"),
    ("bearer",      r"Bearer\s+[A-Za-z0-9._\-]{20,}", "Bearer token"),
    ("generic_assign",
     r"(?i)\b(api[_-]?key|apikey|secret|token|passwd|password|access[_-]?key)\b"
     r"\s*[:=]\s*[\"']([^\"'\s]{16,})[\"']", "疑似硬编码密钥"),
    ("sk_key",      r"\bsk-[A-Za-z0-9]{20,}\b", "OpenAI 风格 sk- 密钥"),
]

# 占位符白名单：命中这些就不算泄漏
PLACEHOLDER_RE = re.compile(
    r"(?i)(\$\{|\{\{|<[A-Z_]+>|your[_-]|xxx+|\.\.\.|placeholder|example|redacted|"
    r"change[_-]?me|dummy|fake|test[_-]?key|env\[|process\.env|os\.environ)"
)

# ── 文件名/路径黑名单 ───────────────────────────────────────────────
PRIVACY_NAME_RE = re.compile(
    r"(?i)(^|/)(\.env(\.(?!example)[\w-]+)?|"
    r"[\w.\-]*credential[\w.\-]*\.json|"
    r"[\w.\-]*secret[\w.\-]*\.(json|txt|ya?ml|ini)|"
    r"[\w.\-]*token[\w.\-]*\.(json|txt)|"
    r"[\w.\-]*令牌[\w.\-]*|[\w.\-]*秘钥[\w.\-]*|[\w.\-]*密钥[\w.\-]*|"
    r"whale-diary[^/]*\.md|"
    r"[\w.\-]*\.(pem|key|p12|pfx|keystore|jks)|"
    r"id_rsa|id_ed25519|\.git-credentials|\.npmrc|\.pypirc)$"
)
PRIVACY_ALLOW_RE = re.compile(r"(?i)(\.example\.|example$|sample|template|^readme|readme\.md$)")

JUNK_DIR_RE = re.compile(
    r"(^|/)(node_modules|dist|build|out|target|__pycache__|\.venv|venv|"
    r"\.next|\.nuxt|\.cache|\.parcel-cache|coverage|\.pytest_cache|"
    r"\.mypy_cache|\.idea|\.vscode|\.DS_Store|Thumbs\.db)(/|$)"
)
JUNK_FILE_RE = re.compile(
    r"(?i)(\.log$|\.tmp$|\.bak$|\.swp$|\.pyc$|\.pyo$|\.db$|\.sqlite3?$|"
    r"\.mp4$|\.mov$|\.zip$|\.7z$|\.exe$|\.msi$|\.dmg$|\.iso$)"
)
# 上面这些“不该被 git 跟踪”，但发布安装包时 exe/zip 是 Release 资产，允许例外
RELEASE_ASSET_ALLOW_RE = re.compile(r"(?i)^(release|dist/assets)/")

ABS_PATH_RE = re.compile(r"[A-Za-z]:\\\\?Users\\\\?([^\\\\/\s\"'<>]{2,32})")
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b")
PHONE_CN_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
ID_CN_RE = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")

TEXT_EXTS = {
    ".md", ".txt", ".json", ".jsonl", ".yml", ".yaml", ".toml", ".ini", ".cfg",
    ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".vue", ".svelte",
    ".py", ".sh", ".bash", ".ps1", ".bat", ".cmd", ".html", ".htm", ".css",
    ".scss", ".sql", ".env", ".xml", ".c", ".h", ".cpp", ".rs", ".go", ".java",
}
SKIP_CONTENT_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf",
                    ".zip", ".7z", ".exe", ".dll", ".so", ".woff", ".woff2"}


def sh(args: list[str], cwd: Path) -> tuple[int, str]:
    try:
        p = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120)
        return p.returncode, p.stdout
    except Exception as e:  # noqa: BLE001
        return 1, f"__ERR__ {e}"


@dataclass
class Finding:
    level: str          # BLOCK / WARN / PASS
    code: str
    where: str
    detail: str


@dataclass
class Report:
    root: str
    is_git: bool = False
    tracked: int = 0
    untracked: int = 0
    total_bytes: int = 0
    findings: list[Finding] = field(default_factory=list)
    will_upload: list[dict] = field(default_factory=list)
    excluded: list[dict] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        levels = {f.level for f in self.findings}
        if "BLOCK" in levels:
            return "BLOCK"
        if "WARN" in levels:
            return "WARN"
        return "PASS"


def collect(root: Path, rep: Report) -> tuple[list[str], list[str]]:
    """返回 (会进仓库的文件, 未跟踪但会被 add 的文件)。"""
    is_git = (root / ".git").exists()
    rep.is_git = is_git
    if is_git:
        rc, out = sh(["git", "ls-files", "-z"], root)
        tracked = [x for x in out.split("\0") if x] if rc == 0 else []
        rc2, out2 = sh(["git", "status", "--porcelain", "--untracked-files=all"], root)
        untracked = []
        if rc2 == 0:
            for line in out2.splitlines():
                if line.startswith("?? "):
                    untracked.append(line[3:].strip().strip('"'))
        rep.tracked, rep.untracked = len(tracked), len(untracked)
        return tracked, untracked

    # 非 git：按 .gitignore 的粗略语义走一遍
    ignore = set()
    gi = root / ".gitignore"
    if gi.exists():
        for line in gi.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("!"):
                ignore.add(line.rstrip("/"))
    files = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if rel.startswith(".git/"):
            continue
        if any(part in ignore for part in rel.split("/")):
            continue
        files.append(rel)
    rep.tracked = len(files)
    return files, []


def check_names(rep: Report, files: list[str]) -> None:
    for rel in files:
        if PRIVACY_NAME_RE.search("/" + rel) and not PRIVACY_ALLOW_RE.search(rel):
            rep.findings.append(Finding("BLOCK", "privacy-file", rel,
                                        "文件名本身属于隐私/凭据，绝不能进仓库"))


def check_sizes(rep: Report, root: Path, files: list[str]) -> None:
    total = 0
    for rel in files:
        p = root / rel
        try:
            size = p.stat().st_size
        except OSError:
            continue
        total += size
        if size > MAX_FILE_BYTES:
            rep.findings.append(Finding(
                "BLOCK", "big-file", rel,
                f"{size/1048576:.1f} MB > 50 MB；GitHub 单文件硬限 100 MB，"
                "应放 Release 资产或 Git LFS"))
        elif size > BIG_BLOB_WARN:
            rep.findings.append(Finding(
                "WARN", "large-file", rel,
                f"{size/1048576:.1f} MB；二进制大文件会让 clone 变慢"))
    rep.total_bytes = total
    if total > WARN_REPO_BYTES:
        rep.findings.append(Finding(
            "WARN", "repo-size", ".",
            f"会进仓库的总量 {total/1048576:.0f} MB，建议把产物挪到 Release"))


def check_junk(rep: Report, files: list[str]) -> None:
    for rel in files:
        if JUNK_DIR_RE.search(rel):
            rep.findings.append(Finding("WARN", "junk-tracked", rel,
                                        "构建产物/依赖目录被跟踪，应从索引移除"))
        elif JUNK_FILE_RE.search(rel) and not RELEASE_ASSET_ALLOW_RE.search(rel):
            rep.findings.append(Finding("WARN", "junk-tracked", rel,
                                        "运行产物/二进制被跟踪，确认是否真需要"))


def check_content(rep: Report, root: Path, files: list[str], limit: int = 400) -> None:
    """密钥 / 绝对路径 / 联系方式。只扫文本文件，前 limit 个文件。"""
    scanned = 0
    for rel in files:
        if scanned >= limit:
            rep.findings.append(Finding(
                "WARN", "scan-truncated", ".",
                f"内容扫描只看了前 {limit} 个文本文件，剩余请人工抽查"))
            break
        p = root / rel
        if p.suffix.lower() in SKIP_CONTENT_EXT:
            continue
        if p.suffix.lower() not in TEXT_EXTS and p.name not in {".gitignore", ".gitattributes", "LICENSE", "NOTICE"}:
            continue
        try:
            if p.stat().st_size > 2 * 1024 * 1024:
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        scanned += 1
        for lineno, line in enumerate(text.splitlines(), 1):
            if len(line) > 4000:
                line = line[:4000]
            for code, pat, label in SECRET_PATTERNS:
                for m in re.finditer(pat, line):
                    hit = m.group(0)
                    if PLACEHOLDER_RE.search(hit) or PLACEHOLDER_RE.search(
                            line[max(0, m.start() - 40): m.start()]):
                        continue
                    rep.findings.append(Finding(
                        "BLOCK", f"secret:{code}", f"{rel}:{lineno}",
                        f"{label}；值形如 {mask(hit)}"))
            for m in ABS_PATH_RE.finditer(line):
                user = m.group(1)
                if user.lower() in {"public", "default", "all users"}:
                    continue
                rep.findings.append(Finding(
                    "WARN", "abs-path", f"{rel}:{lineno}",
                    f"写死了本机绝对路径，含用户名 {mask(user)}"))
                break
            if p.suffix.lower() in {".md", ".txt", ".json", ".yml", ".yaml"}:
                for m in EMAIL_RE.finditer(line):
                    if m.group(0).lower().endswith(("example.com", "test.com")):
                        continue
                    rep.findings.append(Finding(
                        "WARN", "contact", f"{rel}:{lineno}",
                        f"邮箱 {mask(m.group(0))}；公开仓库会招来垃圾邮件"))
                for m in PHONE_CN_RE.finditer(line):
                    rep.findings.append(Finding(
                        "WARN", "contact", f"{rel}:{lineno}",
                        f"手机号 {mask(m.group(0))}"))


def mask(s: str) -> str:
    s = s.strip()
    if len(s) <= 8:
        return s[:2] + "***"
    return s[:6] + "***" + s[-4:]


def check_history(rep: Report, root: Path) -> None:
    if not rep.is_git:
        return
    rc, out = sh(["git", "log", "--all", "-p", f"-{HISTORY_COMMITS}", "--no-color"], root)
    if rc != 0:
        rep.findings.append(Finding("WARN", "history-unread", ".",
                                    "无法读取 git 历史，历史泄漏未检查"))
        return
    for code, pat, label in SECRET_PATTERNS[:8]:
        if re.search(pat, out):
            rep.findings.append(Finding(
                "BLOCK", f"history-secret:{code}", "git log",
                f"历史提交里出现过{label}；删文件没用，必须重写历史或用 filter-repo"))
    rc2, names = sh(["git", "log", "--all", "--name-only", "--pretty=format:"], root)
    if rc2 == 0:
        for line in set(names.splitlines()):
            line = line.strip()
            if line and PRIVACY_NAME_RE.search("/" + line) and not PRIVACY_ALLOW_RE.search(line):
                rep.findings.append(Finding(
                    "BLOCK", "history-privacy", line,
                    "隐私文件曾进入历史，即使现在删了也还在"))


def check_docs(rep: Report, root: Path, files: list[str]) -> None:
    lower = {f.lower() for f in files}
    if not any(f.startswith("readme") for f in lower):
        rep.findings.append(Finding("WARN", "no-readme", ".",
                                    "缺 README，别人打开仓库不知道这是什么"))
    if not any(f.startswith(("license", "licence", "copying")) for f in lower):
        rep.findings.append(Finding("WARN", "no-license", ".",
                                    "缺 LICENSE，别人不敢用"))
    if ".gitignore" not in lower and ".git/info/exclude" not in lower:
        rep.findings.append(Finding("WARN", "no-gitignore", ".",
                                    "缺 .gitignore，垃圾文件迟早被 add 进来"))
    for rel in files:
        if rel.lower().startswith("readme"):
            try:
                text = (root / rel).read_text(encoding="utf-8", errors="replace")
            except OSError:
                return
            for marker in ("TODO", "TBD", "FIXME", "占位", "待补充", "Lorem ipsum"):
                if marker.lower() in text.lower():
                    rep.findings.append(Finding(
                        "WARN", "readme-placeholder", rel,
                        f"README 里有占位符「{marker}」"))
            break


def build_manifest(rep: Report, root: Path, files: list[str],
                   untracked: list[str]) -> None:
    flagged = {f.where.split(":")[0] for f in rep.findings if f.level == "BLOCK"}
    for rel in files:
        try:
            size = (root / rel).stat().st_size
        except OSError:
            size = 0
        entry = {"path": rel, "bytes": size,
                 "sha256_8": sha8(root / rel)}
        if rel in flagged:
            rep.excluded.append({**entry, "reason": "BLOCK 命中，修好前不上传"})
        else:
            rep.will_upload.append(entry)
    for rel in untracked:
        rep.excluded.append({"path": rel, "bytes": 0, "sha256_8": "",
                             "reason": "未跟踪，本次不上传（确认后再 add）"})


def sha8(p: Path) -> str:
    try:
        if p.stat().st_size > 8 * 1024 * 1024:
            return "(skip)"
        return hashlib.sha256(p.read_bytes()).hexdigest()[:8]
    except OSError:
        return ""


def render_md(rep: Report) -> str:
    L = []
    L.append("# 上传清单\n")
    L.append(f"- 项目：`{rep.root}`")
    L.append(f"- 是否 git 仓库：{'是' if rep.is_git else '否'}")
    L.append(f"- 已跟踪 {rep.tracked} 个文件，未跟踪 {rep.untracked} 个")
    L.append(f"- 会进仓库总量：{rep.total_bytes/1048576:.2f} MB")
    L.append(f"\n## 判定：**{rep.verdict}**\n")
    if rep.verdict == "BLOCK":
        L.append("> 存在 BLOCK 项，脚本拒绝放行。修完重新审计。\n")
    elif rep.verdict == "WARN":
        L.append("> 存在 WARN 项，逐条确认后才可上传。\n")

    blocks = [f for f in rep.findings if f.level == "BLOCK"]
    warns = [f for f in rep.findings if f.level == "WARN"]
    if blocks:
        L.append("## 必须修（BLOCK）\n")
        L.append("| 位置 | 问题 | 说明 |")
        L.append("|---|---|---|")
        for f in blocks:
            L.append(f"| `{f.where}` | {f.code} | {f.detail} |")
        L.append("")
    if warns:
        L.append("## 需要确认（WARN）\n")
        L.append("| 位置 | 问题 | 说明 |")
        L.append("|---|---|---|")
        for f in warns:
            L.append(f"| `{f.where}` | {f.code} | {f.detail} |")
        L.append("")

    L.append("## 会上传\n")
    L.append("| 文件 | 大小 | sha256(8) |")
    L.append("|---|---|---|")
    for e in rep.will_upload[:80]:
        L.append(f"| `{e['path']}` | {e['bytes']} B | `{e['sha256_8']}` |")
    if len(rep.will_upload) > 80:
        L.append(f"| …共 {len(rep.will_upload)} 个 | | |")
    L.append("")
    L.append("## 不会上传 / 需要处理\n")
    L.append("| 文件 | 原因 |")
    L.append("|---|---|")
    for e in rep.excluded[:80]:
        L.append(f"| `{e['path']}` | {e['reason']} |")
    if len(rep.excluded) > 80:
        L.append(f"| …共 {len(rep.excluded)} 个 | | |")
    L.append("")
    return "\n".join(L)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    ap = argparse.ArgumentParser(description="上传前的合格线审计")
    ap.add_argument("path", nargs="?", default=".", help="项目目录")
    ap.add_argument("--dry", action="store_true", default=True, help="只读（默认）")
    ap.add_argument("--write-report", action="store_true", help="写 report.md / report.json")
    ap.add_argument("--json", action="store_true", help="只输出 json")
    ap.add_argument("--limit", type=int, default=400, help="内容扫描文件数上限")
    args = ap.parse_args()

    root = Path(args.path).expanduser().resolve()
    if not root.is_dir():
        print(f"错误：不是目录 -> {root}", file=sys.stderr)
        return 3

    rep = Report(root=str(root))
    files, untracked = collect(root, rep)
    check_names(rep, files)
    check_sizes(rep, root, files)
    check_junk(rep, files)
    check_content(rep, root, files, limit=args.limit)
    check_history(rep, root)
    check_docs(rep, root, files)
    build_manifest(rep, root, files, untracked)

    if args.write_report:
        (root / "report.md").write_text(render_md(rep), encoding="utf-8")
        (root / "report.json").write_text(
            json.dumps({"root": rep.root, "verdict": rep.verdict,
                        "findings": [asdict(f) for f in rep.findings],
                        "will_upload": rep.will_upload,
                        "excluded": rep.excluded},
                       ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps({"verdict": rep.verdict,
                          "findings": [asdict(f) for f in rep.findings]},
                         ensure_ascii=False, indent=2))
    else:
        print(render_md(rep))

    return {"PASS": 0, "WARN": 1, "BLOCK": 2}[rep.verdict]


if __name__ == "__main__":
    raise SystemExit(main())
