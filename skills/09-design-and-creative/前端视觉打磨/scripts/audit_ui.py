#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""前端静态审计：查「可机检」的 AI 味与规范问题。

用法：
    python audit_ui.py <目录或文件> [--json] [--limit 400]
    python audit_ui.py ./src --json > ui.json

它查什么（每条都能给出行号或文件）：
  档位收敛  颜色/字号/圆角/间距 用了多少种不同值
  结构      <h1> 是否唯一、img 是否缺 alt、按钮是否 <div onclick>
  样式卫生  !important 数量、内联 style 数量、transition: all
  文案      禁用词（赋能/一站式/无缝…）、占位符（TODO/Lorem）
  视觉      emoji 当图标、渐变文字、玻璃拟态、三层以上阴影
  无障碍    疑似对比度不足（#hex 组合的简单估算）

它不查什么：审美。那部分靠 references/ai-tells.md 人工过。

退出码：0 = 80 分以上；1 = 60–79；2 = 60 以下；3 = 参数错。
"""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

WEB_EXTS = {".html", ".htm", ".css", ".scss", ".sass", ".less",
            ".jsx", ".tsx", ".vue", ".svelte", ".js", ".ts", ".astro"}
SKIP_DIRS = {"node_modules", ".git", "dist", "build", "out", "target",
             "__pycache__", ".venv", "venv", ".next", ".nuxt", ".cache",
             "coverage", ".publish", "release"}

BANNED_WORDS = [
    "赋能", "一站式", "无缝", "极致", "打造", "助力", "引领", "重新定义",
    "颠覆", "全方位", "深度赋能", "闭环", "抓手", "生态", "矩阵", "底层逻辑",
    "革命性", "前所未有的", "Lorem ipsum", "待补充", "示例文本",
]
PLACEHOLDER_RE = re.compile(r"\b(TODO|TBD|FIXME|XXX)\b")

COLOR_RE = re.compile(
    r"#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b"
    r"|rgba?\([^)]{3,60}\)"
    r"|hsla?\([^)]{3,60}\)")
FONT_SIZE_RE = re.compile(r"font-size\s*:\s*([0-9.]+)(px|rem|em|pt|%)")
RADIUS_RE = re.compile(r"border-radius\s*:\s*([^;}{]+)")
SPACING_PROP_RE = re.compile(
    r"\b(?:margin|padding|gap|row-gap|column-gap)(?:-(?:top|right|bottom|left|inline|block))?\s*:\s*([^;}{]+)")
SHADOW_RE = re.compile(r"box-shadow\s*:\s*([^;}{]+)")
EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F]")
INLINE_STYLE_RE = re.compile(r"""style\s*=\s*["'][^"']+["']""")
GRADIENT_TEXT_RE = re.compile(r"-webkit-background-clip\s*:\s*text|background-clip\s*:\s*text")
GLASS_RE = re.compile(r"backdrop-filter\s*:\s*[^;]*(blur|saturate)")
TRANSITION_ALL_RE = re.compile(r"transition\s*:\s*all\b")
DIV_ONCLICK_RE = re.compile(r"<div[^>]*\bonclick\s*=", re.I)
IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.I)
H1_RE = re.compile(r"<h1\b", re.I)

AI_DEFAULT_COLORS = {
    "#667eea": "紫蓝渐变主色（tailwind 示例默认）",
    "#764ba2": "紫蓝渐变副色",
    "#8b5cf6": "紫色，AI 生成高频",
    "#a855f7": "紫色，AI 生成高频",
    "#6366f1": "indigo，shadcn 默认",
    "#3b82f6": "蓝色，默认值",
    "#6c5ce7": "紫，常见模板色",
}


def hex_to_rgb(s):
    s = s.lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) == 4:
        s = "".join(c * 2 for c in s[:3])
    if len(s) == 8:
        s = s[:6]
    if len(s) != 6:
        return None
    try:
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


def rel_luminance(rgb):
    def f(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (f(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(c1, c2):
    a, b = hex_to_rgb(c1), hex_to_rgb(c2)
    if not a or not b:
        return None
    l1, l2 = rel_luminance(a), rel_luminance(b)
    hi, lo = max(l1, l2), min(l1, l2)
    return round((hi + 0.05) / (lo + 0.05), 2)


def chroma(rgb):
    """绝对彩度 0–1 = (max-min)/255。

    不用 HSL 饱和度：它把「接近黑/白但带一点色偏」的值算成高饱和
    （#0f1116 的 HSL 饱和度是 0.19，但肉眼看就是黑）。深色主题里
    这种带色偏的灰特别多，用 HSL 会误判成十几个「彩色」。
    """
    r, g, b = (x / 255 for x in rgb)
    return max(r, g, b) - min(r, g, b)


def norm_color(c):
    c = c.strip().lower().replace(" ", "")
    m = re.fullmatch(r"#([0-9a-f]{3})", c)
    if m:
        return "#" + "".join(ch * 2 for ch in m.group(1))
    m = re.fullmatch(r"#([0-9a-f]{4})", c)
    if m:
        return "#" + "".join(ch * 2 for ch in m.group(1)[:3])
    m = re.fullmatch(r"#([0-9a-f]{8})", c)
    if m:
        return "#" + m.group(1)[:6]
    return c


def norm_size(v, unit):
    try:
        n = float(v)
    except ValueError:
        return None
    if unit == "rem" or unit == "em":
        return round(n * 16)
    if unit == "pt":
        return round(n * 4 / 3)
    if unit == "%":
        return None
    return round(n)


def norm_spacing(expr):
    """'16px 24px' → {16, 24}；忽略 0 和 auto。"""
    out = set()
    for tok in re.split(r"\s+", expr.strip()):
        m = re.fullmatch(r"(-?[0-9.]+)(px|rem|em)", tok)
        if not m:
            continue
        v = norm_size(m.group(1), m.group(2))
        if v and v != 0:
            out.add(v)
    return out


def norm_radius(expr):
    out = set()
    for tok in re.split(r"[\s/]+", expr.strip()):
        if tok in ("0", "0px", "0rem"):
            continue
        m = re.fullmatch(r"([0-9.]+)(px|rem|em|%)", tok)
        if not m:
            if tok == "9999px" or tok == "50%":
                out.add(999)
            continue
        v = norm_size(m.group(1), m.group(2))
        if v:
            out.add(999 if v >= 100 else v)
    return out


def shadow_layers(expr):
    """数阴影层数：按逗号切，排除 rgba(...) 内部的逗号。"""
    depth, layers, cur = 0, 1, ""
    for ch in expr:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            layers += 1
        cur += ch
    return layers


class Audit:
    def __init__(self, root):
        self.root = root
        self.files = []
        self.findings = []          # (severity, code, where, detail)
        self.colors = Counter()
        self.font_sizes = Counter()
        self.radii = Counter()
        self.spacings = Counter()
        self.stats = defaultdict(int)
        self.color_where = {}
        self.uses_vars = False

    # ---------- 采集 ----------
    def collect(self, limit):
        if self.root.is_file():
            self.files = [self.root]
            return
        for p in sorted(self.root.rglob("*")):
            if len(self.files) >= limit:
                break
            if not p.is_file() or p.suffix.lower() not in WEB_EXTS:
                continue
            if any(part in SKIP_DIRS for part in p.parts):
                continue
            if p.stat().st_size > 2 * 1024 * 1024:
                continue
            self.files.append(p)

    def add(self, sev, code, where, detail):
        self.findings.append((sev, code, where, detail))

    def run(self):
        for p in self.files:
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            rel = p.relative_to(self.root) if self.root.is_dir() else p.name
            rel = str(rel).replace("\\", "/")
            self.scan_text(rel, text)

    def scan_text(self, rel, text):
        lines = text.splitlines()
        if "var(--" in text:
            self.uses_vars = True

        # --- 颜色 ---
        for m in COLOR_RE.finditer(text):
            c = norm_color(m.group(0))
            self.colors[c] += 1
            self.color_where.setdefault(c, rel)

        # --- 字号 ---
        for m in FONT_SIZE_RE.finditer(text):
            v = norm_size(m.group(1), m.group(2))
            if v:
                self.font_sizes[v] += 1

        # --- 圆角 ---
        for m in RADIUS_RE.finditer(text):
            for v in norm_radius(m.group(1)):
                self.radii[v] += 1

        # --- 间距 ---
        for m in SPACING_PROP_RE.finditer(text):
            for v in norm_spacing(m.group(1)):
                self.spacings[v] += 1

        # --- 阴影层数 ---
        for m in SHADOW_RE.finditer(text):
            n = shadow_layers(m.group(1))
            if n >= 3:
                self.add("warn", "shadow-stack", rel, f"阴影 {n} 层叠加，只留一层")
                break

        # --- 逐行检查 ---
        for i, line in enumerate(lines, 1):
            where = f"{rel}:{i}"
            low = line.lower()

            if "!important" in line:
                self.stats["important"] += 1
            if TRANSITION_ALL_RE.search(line):
                self.add("warn", "transition-all", where,
                         "transition: all 会连带改动的属性一起动画，指定属性名")
            if GRADIENT_TEXT_RE.search(line):
                self.add("warn", "gradient-text", where,
                         "渐变文字标题是 AI 生成标志，改用字重/字号做层级")
            if GLASS_RE.search(line):
                self.stats["glass"] += 1
            if DIV_ONCLICK_RE.search(line):
                self.add("warn", "div-onclick", where,
                         "<div onclick> 不可键盘操作，改用 <button>")
            if EMOJI_RE.search(line) and ("<" in line or ">" in line or "icon" in low):
                self.add("warn", "emoji-icon", where,
                         "用 emoji 当图标；换 SVG 或去掉")
            if PLACEHOLDER_RE.search(line):
                self.add("warn", "placeholder", where,
                         f"占位符 {PLACEHOLDER_RE.search(line).group(0)}，发布前必须清掉")
            for w in BANNED_WORDS:
                if w in line:
                    self.add("warn", "banned-word", where,
                             f"禁用词「{w}」——换成具体的事实或数字")
                    break
            if INLINE_STYLE_RE.search(line):
                self.stats["inline_style"] += 1

        # --- 结构 ---
        h1 = len(H1_RE.findall(text))
        if h1 == 0 and ("<body" in text.lower() or "<html" in text.lower()):
            self.add("warn", "no-h1", rel, "没有 <h1>；页面需要唯一主标题")
        elif h1 > 1:
            self.add("warn", "multi-h1", rel, f"有 {h1} 个 <h1>；应该只有 1 个")
        self.stats["h1"] += h1

        for m in IMG_TAG_RE.finditer(text):
            tag = m.group(0)
            if "alt=" not in tag.lower():
                self.add("warn", "img-no-alt", rel,
                         f"<img> 缺 alt：{tag[:60]}")
                break

    # ---------- 评分 ----------
    def score(self):
        s = 100
        pen = []

        def take(n, why):
            nonlocal s
            if n:
                s -= n
                pen.append((n, why))

        ncolors = len([c for c in self.colors if c.startswith("#")])
        # 只数「有彩色的」色相：灰阶（饱和度 < 0.15）不算进 3 色预算。
        # 深色主题天然有十几个灰，全算进去会误伤正常项目。
        hue_colors = set()
        for c in self.colors:
            rgb = hex_to_rgb(c) if c.startswith("#") else None
            if rgb and chroma(rgb) >= 0.12:
                hue_colors.add(c)
        nhue = len(hue_colors)
        if nhue > 4:
            take(min(12, (nhue - 4) * 3), f"{nhue} 种有彩色（应 ≤ 3 色 + 1 强调色）")
        if ncolors > 18:
            take(min(6, (ncolors - 18)), f"共 {ncolors} 个色值（含灰阶），偏多")
        nsize = len(self.font_sizes)
        if nsize > 5:
            take(min(10, (nsize - 5) * 3), f"{nsize} 种字号（应 ≤ 4 档）")
        nradius = len(self.radii)
        if nradius > 3:
            take(min(8, (nradius - 3) * 3), f"{nradius} 种圆角（应 ≤ 2 档）")
        nspace = len(self.spacings)
        if nspace > 10:
            take(min(6, (nspace - 10)), f"{nspace} 种间距（应收敛到 8 的倍数）")

        if self.stats["important"] > 3:
            take(min(10, self.stats["important"] - 3), f"{self.stats['important']} 处 !important")
        if self.stats["inline_style"] > 10:
            take(min(8, (self.stats["inline_style"] - 10) // 2), f"{self.stats['inline_style']} 处内联 style")
        if self.stats["glass"] > 1:
            take(4, f"玻璃拟态 {self.stats['glass']} 处（应 ≤ 1）")

        counts = Counter(f[1] for f in self.findings)
        for code, w in (("gradient-text", 3), ("emoji-icon", 2), ("shadow-stack", 3),
                        ("transition-all", 2), ("banned-word", 2), ("placeholder", 4),
                        ("no-h1", 4), ("multi-h1", 3), ("img-no-alt", 3),
                        ("div-onclick", 2)):
            if counts.get(code):
                take(min(10, w * min(counts[code], 3)), f"{code} × {counts[code]}")

        # AI 默认色
        for c, why in AI_DEFAULT_COLORS.items():
            if c in self.colors:
                take(3, f"用了 {c}（{why}）")

        return max(0, s), pen

    def render(self):
        sc, pen = self.score()
        L = ["# 前端审计", ""]
        L.append(f"- 扫描：`{self.root}`")
        L.append(f"- 文件：{len(self.files)} 个")
        L.append(f"- **分数：{sc}/100**")
        L.append("")

        if pen:
            L += ["## 扣分项", "", "| 扣 | 原因 |", "|---|---|"]
            for n, why in sorted(pen, reverse=True):
                L.append(f"| -{n} | {why} |")
            L.append("")

        L += ["## 档位实际分布", "",
              "| 类型 | 种数 | 值（按出现次数） |", "|---|---|---|"]
        for label, counter, cap in (("颜色", self.colors, 8),
                                    ("字号", self.font_sizes, 10),
                                    ("圆角", self.radii, 8),
                                    ("间距", self.spacings, 12)):
            vals = ", ".join(f"{k}×{v}" for k, v in counter.most_common(cap))
            L.append(f"| {label} | {len(counter)} | {vals or '—'} |")
        L.append("")
        if self.uses_vars:
            L += ["> 检测到 CSS 变量（`var(--x)`）。字号/圆角/间距的档位在变量定义处，"
                  "审计器只统计字面量，所以这里显示 0 或偏少是**正常的**——"
                  "说明值已经收敛到一处。去看 `:root` 里的定义是否 ≤ 4 档。", ""]

        by_code = defaultdict(list)
        for sev, code, where, detail in self.findings:
            by_code[code].append((where, detail))
        if by_code:
            L += ["## 问题清单", ""]
            for code in sorted(by_code, key=lambda c: -len(by_code[c])):
                items = by_code[code]
                L.append(f"### {code}（{len(items)}）")
                L.append("")
                for where, detail in items[:6]:
                    L.append(f"- `{where}` — {detail}")
                if len(items) > 6:
                    L.append(f"- …另有 {len(items) - 6} 处")
                L.append("")
        else:
            L += ["## 问题清单", "", "没有发现问题。", ""]

        # 对比度抽查
        dark = [c for c in self.colors if c.startswith("#") and hex_to_rgb(c)
                and rel_luminance(hex_to_rgb(c)) < 0.5]
        light = [c for c in self.colors if c.startswith("#") and hex_to_rgb(c)
                 and rel_luminance(hex_to_rgb(c)) >= 0.5]
        if dark and light:
            L += ["## 对比度抽查（最暗 vs 最亮）", ""]
            d, l = dark[0], light[0]
            r = contrast_ratio(d, l)
            if r:
                ok = "✓ 达标" if r >= 4.5 else "✗ 低于 4.5:1"
                L.append(f"`{d}` on `{l}` → {r}:1 {ok}")
            L.append("")

        L += ["## 下一步", "",
              "机检到此为止。审美部分读 `references/ai-tells.md` 逐条过。", ""]
        return "\n".join(L), sc


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass

    ap = argparse.ArgumentParser(description="前端静态审计")
    ap.add_argument("path", nargs="?", default=".", help="目录或文件")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--limit", type=int, default=400, help="最多扫描文件数")
    args = ap.parse_args()

    root = Path(args.path).expanduser().resolve()
    if not root.exists():
        print(f"✗ 路径不存在：{root}", file=sys.stderr)
        return 3

    a = Audit(root)
    a.collect(args.limit)
    if not a.files:
        print(f"✗ 没找到可扫描的前端文件（{', '.join(sorted(WEB_EXTS))}）", file=sys.stderr)
        return 3
    a.run()
    text, sc = a.render()

    if args.json:
        print(json.dumps({
            "root": str(root),
            "files": len(a.files),
            "score": sc,
            "counts": {
                "colors": dict(a.colors),
                "font_sizes": {str(k): v for k, v in a.font_sizes.items()},
                "radii": {str(k): v for k, v in a.radii.items()},
                "spacings": {str(k): v for k, v in a.spacings.items()},
            },
            "stats": dict(a.stats),
            "findings": [{"severity": s, "code": c, "where": w, "detail": d}
                         for s, c, w, d in a.findings],
        }, ensure_ascii=False, indent=2))
    else:
        print(text)

    return 0 if sc >= 80 else (1 if sc >= 60 else 2)


if __name__ == "__main__":
    sys.exit(main())
