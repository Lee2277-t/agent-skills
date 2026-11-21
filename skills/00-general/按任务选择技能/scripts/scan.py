#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""扫描本机已装技能，按任务打分排名。

用法：
    python scan.py                              # 列出所有技能
    python scan.py --task "帮我把工具发到 GitHub"   # 打分排名
    python scan.py --task "..." --top 3         # 只看前 3
    python scan.py --json

它读什么：
  SKILL.md 的 frontmatter（name / description / whenToUse）
  references/ 下的文件名（当作补充关键词）
  scripts/ 下的文件名（同上）

本地整理（2026-10-29）：增加 --root，可显式指定本库或当前宿主目录。
脚本会在本地读取 SKILL.md 来解析头部；输出元数据，不将所有正文注入模型。
"""
import argparse
import json
import re
import sys
from pathlib import Path

# 扫描根（顺序 = DSH 优先级，先找到的优先）
HOME = Path.home()
ROOTS = [
    HOME / ".dsh" / "skills",
    HOME / ".agents" / "skills",
]
PARKED = HOME / ".dsh" / "skills-parked"

# DSH 自带的 bundled 技能（office 系列等）。位置随安装路径变，
# 这里按本机实测的路径猜几个，找不到就跳过，不影响主流程。
BUNDLED_CANDIDATES = [
    HOME / "AppData" / "Local" / "Programs" / "DeepSeek Harness" / "resources" / "runtime" / "office-skills",
]
for _c in BUNDLED_CANDIDATES:
    if _c.is_dir():
        ROOTS.append(_c)
        break

# 中文虚词/停用词，不参与打分
STOP = set("的 了 和 与 在 是 我 你 他 她 它 们 这 那 个 把 被 给 让 帮 请 要 想 能 会 就 都 也 还 又 很 太 一 下 上 中 里 次 点 么 吗 呢 吧 啊 呀 帮我 这个 那个 一下 现在 需要 可以 怎么 什么 一个 我的 你的 帮我做 能不能".split())

CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_+-]{2,}")

# 中英桥：很多技能（尤其 qianwen-*）的 description 是英文，用户用中文提问就一个词
# 也命中不了。这里把中文概念映射到英文关键词，双向都加进任务 token。
# 只放高频、歧义小的词；加太多会让所有技能都命中，反而失去区分度。
BRIDGE = {
    "图片": ["image", "images", "picture"],
    "图像": ["image"],
    "海报": ["poster", "image"],
    "插画": ["illustration", "image"],
    "生成": ["generate", "generation"],
    "视频": ["video"],
    "动画": ["animation"],
    "语音": ["speech", "audio", "tts"],
    "朗读": ["speech", "tts", "read"],
    "配音": ["voiceover", "tts"],
    "识别": ["recognition", "understand"],
    "文字": ["text"],
    "文本": ["text"],
    "写作": ["write", "text"],
    "代码": ["code"],
    "部署": ["deploy", "deployment"],
    "上线": ["deploy", "publish"],
    "发布": ["publish", "release"],
    "上传": ["upload", "publish", "push"],
    "仓库": ["repo", "repository"],
    "安装包": ["installer", "release", "setup"],
    "技能": ["skill", "skills"],
    "额度": ["quota", "usage", "billing"],
    "账单": ["billing", "usage"],
    "余额": ["balance"],
    "花了": ["cost", "usage", "billing"],
    "费用": ["cost", "billing", "usage"],
    "花费": ["cost", "usage", "billing"],
    "多少钱": ["cost", "billing", "price"],
    "用量": ["usage", "quota"],
    "订阅": ["subscription"],
    "充值": ["recharge", "payment"],
    "支付": ["payment"],
    "登录": ["login", "auth"],
    "密钥": ["key", "auth", "credential"],
    "前端": ["frontend", "ui"],
    "页面": ["page", "ui"],
    "样式": ["style", "css"],
    "美化": ["beautiful", "design", "ui"],
    "单片机": ["stm32", "embedded", "mcu"],
    "嵌入式": ["embedded"],
    "文档": ["document", "docx"],
    "表格": ["spreadsheet", "xlsx", "excel"],
    "幻灯片": ["presentation", "pptx", "slide"],
    "搜索": ["search", "find"],
    "安装": ["install"],
}

# 英文缩写 → 全称/同义。技能 description 里通常写全称（presentation 而不是 ppt），
# 用户却习惯写缩写。
EN_SYNONYMS = {
    "ppt": ["pptx", "presentation", "slide"],
    "pptx": ["presentation", "slide"],
    "doc": ["docx", "document", "word"],
    "docx": ["document", "word"],
    "xls": ["xlsx", "excel", "spreadsheet"],
    "xlsx": ["excel", "spreadsheet"],
    "excel": ["xlsx", "spreadsheet"],
    "word": ["docx", "document"],
    "pdf": ["pdf", "export"],
    "img": ["image"],
    "pic": ["image"],
    "ui": ["frontend", "design"],
    "ux": ["frontend", "design"],
    "repo": ["repository", "git"],
    "gh": ["github"],
}


def parse_frontmatter(text):
    """极简 YAML 解析：只取 name / description / whenToUse，支持折叠块与引号。"""
    out = {}
    if not text.startswith("---"):
        return out
    end = text.find("\n---", 3)
    if end < 0:
        return out
    block = text[3:end]
    lines = block.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$", line)
        if not m:
            i += 1
            continue
        key, rest = m.group(1), m.group(2).strip()
        if rest in (">", ">-", "|", "|-", ">+", "|+"):
            buf = []
            i += 1
            while i < len(lines) and (lines[i].startswith(" ") or lines[i].strip() == ""):
                buf.append(lines[i].strip())
                i += 1
            out[key] = (" " if rest.startswith(">") else "\n").join(
                x for x in buf if x)
            continue
        if (rest.startswith('"') and rest.endswith('"')) or \
           (rest.startswith("'") and rest.endswith("'")):
            rest = rest[1:-1]
        out[key] = rest
        i += 1
    return out


def load_skills():
    skills = []
    seen = set()
    for root in ROOTS:
        if not root.is_dir():
            continue
        for entry in sorted(root.iterdir()):
            md = None
            if entry.is_dir() and (entry / "SKILL.md").exists():
                md = entry / "SKILL.md"
            elif entry.is_file() and entry.suffix == ".md":
                md = entry
            if not md:
                continue
            try:
                text = md.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            fm = parse_frontmatter(text)
            name = fm.get("name") or entry.stem
            if name in seen:
                continue
            seen.add(name)
            extra = []
            d = entry if entry.is_dir() else entry.parent
            for sub in ("references", "scripts", "templates"):
                p = d / sub
                if p.is_dir():
                    extra += [f.stem for f in p.iterdir() if f.is_file()]
            skills.append({
                "name": name,
                "description": fm.get("description", ""),
                "whenToUse": fm.get("whenToUse", ""),
                "path": str(md),
                "dir": str(d),
                "extra": extra,
                "size": len(text),
            })
    return skills


def stem(w):
    """极轻量词干：让 documents/document、pdfs/pdf、images/image 能对上。

    不做真正的词干还原（Porter 之类太重且对中文无用），只处理最常见的
    复数 's' 和动词 'ing'/'ed'。两边都过这个函数，所以只要一致就能匹配。
    """
    out = {w}
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        out.add(w[:-1])
    if len(w) > 5 and w.endswith("ing"):
        out.add(w[:-3])
    if len(w) > 4 and w.endswith("ed"):
        out.add(w[:-2])
    return out


def tokens_of(text):
    """任务文本 → 关键词集合。

    中文按 2–4 字切片；**跨标点不切**（先按标点/空格分段，再在段内切），
    否则「上传到 GitHub，包括在线网页」会切出「传到」「括在」这种废词。
    英文按词，长度 ≥3。
    """
    toks = set()
    for w in WORD_RE.findall(text):
        toks |= stem(w.lower())
    for seg in re.split(r"[^\u4e00-\u9fff]+", text):
        if not seg:
            continue
        for n in (4, 3, 2):
            for i in range(len(seg) - n + 1):
                g = seg[i:i + n]
                if g in STOP or len(g) < 2:
                    continue
                toks.add(g)
    # 中→英桥接
    for zh, ens in BRIDGE.items():
        if zh in text:
            for e in ens:
                toks |= stem(e)
    # 英→英同义（缩写展开）
    for w in list(toks):
        for s in EN_SYNONYMS.get(w, []):
            toks |= stem(s)
    return toks


def split_triggers(desc):
    """从 description 里拆出 TRIGGER / DO NOT TRIGGER 两段。"""
    d = desc or ""
    m = re.search(r"DO\s+NOT\s+TRIGGER", d, re.I)
    if m:
        return d[:m.start()], d[m.start():]
    return d, ""


def score_skill(skill, task_toks, task_raw):
    name = skill["name"].lower()
    desc = skill["description"] or ""
    when = skill["whenToUse"] or ""
    do_part, dont_part = split_triggers(desc)

    hits = []
    total = 0

    # 用户点名
    if name in task_raw.lower():
        total += 100
        hits.append(f"点名:{name}")

    # 技能名分词
    for part in re.split(r"[-_]", name):
        if len(part) >= 3 and part in task_toks:
            total += 6
            hits.append(f"名:{part}")

    # TRIGGER 部分命中
    do_toks = tokens_of(do_part)
    for t in do_toks & task_toks:
        total += 10
        hits.append(f"触发:{t}")

    # whenToUse
    for t in tokens_of(when) & task_toks:
        total += 4
        hits.append(f"when:{t}")

    # references/scripts 文件名
    for e in skill["extra"]:
        for t in tokens_of(e) & task_toks:
            total += 2
            hits.append(f"文件:{e}")
            break

    # DO NOT TRIGGER 命中 → 减分
    #
    # 关键细节：DO NOT TRIGGER 里常有和 TRIGGER 重复的词。例如
    # qianwen-image-generation 的 DO 段有 "images / generation"，
    # 它的 DO NOT 段也有 "video generation" 和 "existing images"。
    # 直接把重复词算成排除，会把「生成一张图片」这个**正确**任务判成负分。
    # 所以先做差集：只有**只在 DO NOT 里出现**的词才算排除信号。
    dont_only = tokens_of(dont_part) - do_toks
    dont_hits = dont_only & task_toks
    if dont_hits:
        total -= min(30, 15 * len(dont_hits))
        for t in list(dont_hits)[:3]:
            hits.append(f"排除:{t}")

    # 命中太弱视为噪声：单个 2 字虚词命中不该让技能上榜
    strong = [h for h in hits if not h.startswith("排除:")]
    if len(strong) <= 1 and total < 20:
        return 0, []

    return total, hits


def render_list(skills):
    L = ["# 已装技能", ""]
    L.append(f"共 {len(skills)} 个，目录成本约 {sum(min(len(s['description']), 500) for s in skills)} 字"
             "（DSH 每条 description 最多 500 字进目录）")
    L.append("")
    L.append("| 技能 | 正文长度 | 目录里的 description（前 60 字） |")
    L.append("|---|---|---|")
    for s in sorted(skills, key=lambda x: -x["size"]):
        d = (s["description"] or "").replace("|", "／")[:60]
        L.append(f"| `{s['name']}` | {s['size']} 字 | {d}… |")
    L.append("")
    parked = []
    if PARKED.is_dir():
        parked = [p.name for p in PARKED.iterdir() if p.is_dir()]
    if parked:
        L.append(f"## 已停用（在 `{PARKED}`）")
        L.append("")
        L.append("、".join(f"`{p}`" for p in parked))
        L.append("")
    return "\n".join(L)


def render_rank(skills, task, top):
    toks = tokens_of(task)
    scored = []
    for s in skills:
        sc, hits = score_skill(s, toks, task)
        if sc > 0:
            scored.append((sc, s["name"], hits))
    scored.sort(reverse=True)

    L = ["# 任务 → 技能", ""]
    L.append(f"任务：**{task}**")
    L.append("")
    if not scored:
        L += ["没有技能命中。可能真的不需要技能，或者该写一个新的。", ""]
        return "\n".join(L)

    L.append("| 排名 | 技能 | 分 | 命中 |")
    L.append("|---|---|---|---|")
    for i, (sc, name, hits) in enumerate(scored[:top], 1):
        L.append(f"| {i} | `{name}` | {sc} | {'、'.join(hits[:6])} |")
    L.append("")

    load = [n for _, n, _ in scored[:min(3, len(scored))]]
    L.append(f"## 建议加载（≤3 个）")
    L.append("")
    for n in load:
        L.append(f"- `{n}`")
    L.append("")
    rest = [n for _, n, _ in scored[3:]]
    if rest:
        L.append(f"## 不加载（{len(rest)} 个）")
        L.append("")
        L.append("、".join(f"`{n}`" for n in rest))
        L.append("")
    L.append("> 加载 = 把正文塞进上下文。只用真正要执行的那几个。")
    L.append("")
    return "\n".join(L)


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass

    ap = argparse.ArgumentParser(description="扫描并给技能打分")
    ap.add_argument("--root", action="append", type=Path, help="扫描根目录，可重复；替代 DSH 默认根")
    ap.add_argument("--task", help="用户原始需求，用于打分")
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.root:
        ROOTS[:] = [p.expanduser().resolve() for p in args.root]
    skills = load_skills()
    if not skills:
        print(f"✗ 在 {[str(r) for r in ROOTS]} 下没找到技能", file=sys.stderr)
        return 3

    if args.json:
        if args.task:
            toks = tokens_of(args.task)
            out = []
            for s in skills:
                sc, hits = score_skill(s, toks, args.task)
                out.append({"name": s["name"], "score": sc, "hits": hits})
            out.sort(key=lambda x: -x["score"])
            print(json.dumps(out, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(skills, ensure_ascii=False, indent=2))
        return 0

    if args.task:
        print(render_rank(skills, args.task, args.top))
    else:
        print(render_list(skills))
    return 0


if __name__ == "__main__":
    sys.exit(main())
