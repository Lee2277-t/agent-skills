# -*- coding: utf-8 -*-
"""微信小程序静态资源引用审计（通用版）。

用法:
    python audit_assets.py <小程序工程根目录>            # 默认审计 assets/icons
    python audit_assets.py <工程根目录> assets/icons     # 指定资源子目录

产出: 控制台报告 + <当前目录>/asset_audit.json (含 keep / unused 列表)

原则: 宁可多留，绝不误删。任何无法确定的组合一律保留。
"""
import os, re, sys, json

IMG_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg",
           ".ico", ".mp3", ".wav", ".m4a", ".aac")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    ROOT = sys.argv[1].rstrip("/\\")
    ICON_SUB = sys.argv[2] if len(sys.argv) > 2 else "assets/icons"
    ICON_DIR = os.path.join(ROOT, *ICON_SUB.split("/"))
    if not os.path.isdir(ICON_DIR):
        print("目录不存在:", ICON_DIR)
        return 1

    disk = sorted(f for f in os.listdir(ICON_DIR)
                  if f.lower().endswith(IMG_EXT))
    disk_set = set(disk)
    size = {f: os.path.getsize(os.path.join(ICON_DIR, f)) for f in disk}

    # 配色（tone）集合：从 name--tone.ext 里自动推导
    TONES = set()
    for f in disk:
        stem = f.rsplit(".", 1)[0]
        if "--" in stem:
            TONES.add(stem.rsplit("--", 1)[1])
    TONES = sorted(TONES)
    TONE_RE = "|".join(re.escape(t) for t in TONES) if TONES else r"(?!)"

    # 收集源码
    srcs = []
    for dp, dn, fn in os.walk(ROOT):
        if any(x in dp for x in ("node_modules", "_trash", "miniprogram_npm", ".git")):
            continue
        for f in fn:
            if f.endswith((".wxml", ".js", ".json", ".wxss", ".wxs")):
                srcs.append(os.path.join(dp, f))

    # JS 字符串数组（tabIcons / toolIcons ...）
    arrays = {}
    for p in srcs:
        if not p.endswith(".js"):
            continue
        t = open(p, encoding="utf-8", errors="replace").read()
        for m in re.finditer(r"([A-Za-z_$][\w$]*)\s*:\s*\[([^\]]*)\]", t):
            vals = [a or b for a, b in re.findall(r"'([^']*)'|\"([^\"]*)\"", m.group(2))]
            if vals and all(NAME_RE.match(v) for v in vals):
                arrays.setdefault(m.group(1), set()).update(vals)

    def norm(L):
        s = L.rsplit("/", 1)[-1]
        s = re.sub(r"\.[a-z0-9]+$", "", s, flags=re.I)
        if "--" in s:
            a, _, b = s.partition("--")
            if b in TONES and NAME_RE.match(a):
                return (a, b)
            if NAME_RE.match(a):
                return (a, None)
        if s in TONES:
            return (None, s)
        if NAME_RE.match(s):
            return (s, None)
        return None

    def parse(expr):
        names, tones = set(), set()
        for L in re.findall(r"'([^']*)'", expr):
            r = norm(L)
            if not r:
                continue
            n, t = r
            if n:
                names.add(n)
            if t:
                tones.add(t)
        static = re.sub(r"\{\{.*?\}\}", "\u0001", expr)
        for nm in re.findall(r"([A-Za-z0-9][\w-]*)--(?=\u0001)", static):
            names.add(nm)
        if TONES:
            for t in re.findall(r"--(" + TONE_RE + r")\b", static):
                tones.add(t)
        for arr in re.findall(r"\{\{\s*([A-Za-z_$][\w$]*)\s*\[", expr):
            if arr in arrays:
                names |= arrays[arr]
        if not names or not tones:
            return set(), True
        return {(n, t) for n in names for t in tones}, False

    def prefixes(expr):
        static = re.sub(r"\{\{.*?\}\}", "\u0001", expr)
        return re.findall(r"([A-Za-z0-9][\w-]*-)(?=\u0001)", static)

    def find_exprs(text, ext):
        out = [m.group(1) for m in re.finditer(r'"([^"]*' + re.escape(ICON_SUB) + r'[^"]*)"', text)]
        if ext == ".js":  # JS 常用单引号，必须补扫；WXML 不能扫单引号（会跨段误匹配）
            out += [m.group(1) for m in re.finditer(r"'([^']*" + re.escape(ICON_SUB) + r"[^']*)'", text)]
            out += [m.group(1) for m in re.finditer(r"`([^`]*" + re.escape(ICON_SUB) + r"[^`]*)`", text)]
        return out

    combos, plain, exprs, unresolved = set(), set(), [], []
    for p in srcs:
        text = open(p, encoding="utf-8", errors="replace").read()
        for expr in find_exprs(text, os.path.splitext(p)[1]):
            exprs.append((os.path.relpath(p, ROOT), expr))
            if "{{" not in expr:
                b = os.path.basename(expr)
                if "--" in b:
                    n, _, t = re.sub(r"\.[a-z0-9]+$", "", b, flags=re.I).partition("--")
                    combos.add((n, t))
                else:
                    plain.add(b)
                continue
            c, generic = parse(expr)
            combos |= c
            if generic:
                unresolved.append((os.path.relpath(p, ROOT), expr.strip()))

    # 通用组件 empty-state / icon-button 调用点池
    for p in srcs:
        if not p.endswith(".wxml"):
            continue
        t = open(p, encoding="utf-8", errors="replace").read()
        for tag in re.findall(r"<empty-state[^>]*?/>", t, re.S):
            icons = re.findall(r'\bicon="([A-Za-z0-9-]+)"', tag)
            cols = re.findall(r'\bicon-?[Cc]olor="([A-Za-z0-9-]+)"', tag) or ["faint"]
            for i in icons:
                for c in cols:
                    combos.add((i, c))

    keep = set()
    for (n, t) in combos:
        fn = f"{n}--{t}.svg"
        if fn in disk_set:
            keep.add(fn)
        else:
            for f in disk:
                if f == f"{n}--{t}" + os.path.splitext(f)[1]:
                    keep.add(f)
    for b in plain:
        if b in disk_set:
            keep.add(b)
    for _, expr in unresolved:
        for pf in prefixes(expr):
            for f in disk:
                if f.startswith(pf):
                    keep.add(f)

    def covered(expr):
        c, generic = parse(expr)
        if not generic:
            for (n, t) in c:
                if any(f.startswith(f"{n}--") for f in keep):
                    return True
            return False
        return any(f.startswith(pf) for pf in prefixes(expr) for f in keep)

    bad = [(f, e) for f, e in exprs if "{{" in e and not covered(e)]
    unused = [f for f in disk if f not in keep]

    def dsize(d):
        return sum(os.path.getsize(os.path.join(d, x)) for x in os.listdir(d)
                   if os.path.isfile(os.path.join(d, x)))

    assets_dir = os.path.join(ROOT, "assets")
    total_img = 0
    if os.path.isdir(assets_dir):
        for dp, dn, fn in os.walk(assets_dir):
            for x in fn:
                if x.lower().endswith(IMG_EXT):
                    total_img += os.path.getsize(os.path.join(dp, x))

    print("资源目录        :", ICON_SUB)
    print("磁盘文件        :", len(disk), "个  %.1f KB" % (sum(size.values()) / 1024))
    print("保留(会被引用)  :", len(keep), "个  %.1f KB" % (sum(size[f] for f in keep) / 1024))
    print("可删(未被引用)  :", len(unused), "个  %.1f KB" % (sum(size[f] for f in unused) / 1024))
    print("配色(tone)      :", TONES)
    print("assets 图片音频总量: %.1f KB   %s"
          % (total_img / 1024, ">> 超过 200K，需处理" if total_img > 200 * 1024 else "OK"))
    print()
    print("=== 安全校验：匹配不到保留文件的表达式（应为空）===")
    for f, e in bad:
        print("  !!", f, "->", e[:110])
    if not bad:
        print("  ✓ 通过")
    print()
    print("=== 半动态（已按前缀保守保留）===")
    for f, e in unresolved:
        print("  ~", f, "->", e[:90], "| 前缀:", prefixes(e))
    print()
    print("=== 可删文件（前 40）===")
    for f in unused[:40]:
        print("  ", f)

    json.dump({"keep": sorted(keep), "unused": sorted(unused),
               "tones": TONES, "bad": [list(x) for x in bad]},
              open("asset_audit.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n明细已写入 asset_audit.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
