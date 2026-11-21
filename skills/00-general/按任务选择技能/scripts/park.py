#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""停用 / 恢复技能：把目录在扫描根和停放目录之间挪动。

用法：
    python park.py                          # 看哪些技能能停用、哪些已停用
    python park.py qianwen-payment --dry     # 预演：只显示要挪到哪
    python park.py qianwen-payment --go      # 真挪
    python park.py --restore qianwen-payment --go
    python park.py --all-unused --dry        # 按账本推荐批量停用（仍要 --go）

为什么是「挪目录」而不是「删」：
  DSH 只扫描 ~/.dsh/skills 和 ~/.agents/skills 这两层。把技能挪到兄弟目录
  ~/.dsh/skills-parked/ 就不在扫描根里了，目录清单里消失，额度省下。
  想恢复就挪回来，内容一个字没动。

铁律：默认 --dry，必须显式 --go 才真的动文件。
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

HOME = Path.home()
ROOTS = [HOME / ".dsh" / "skills", HOME / ".agents" / "skills"]
PARKED = HOME / ".dsh" / "skills-parked"
LEDGER = HOME / ".dsh" / "skill-ledger.jsonl"


def find_skill(name):
    """返回 (源目录, 状态)。状态是 'active' 或 'parked'。"""
    for root in ROOTS:
        d = root / name
        if d.is_dir():
            return d, "active"
        md = root / f"{name}.md"
        if md.is_file():
            return md, "active"
    p = PARKED / name
    if p.is_dir():
        return p, "parked"
    return None, None


def list_all():
    active, parked = [], []
    for root in ROOTS:
        if not root.is_dir():
            continue
        for e in sorted(root.iterdir()):
            if e.is_dir() and (e / "SKILL.md").exists():
                active.append(e.name)
            elif e.is_file() and e.suffix == ".md":
                active.append(e.stem)
    if PARKED.is_dir():
        for e in sorted(PARKED.iterdir()):
            if e.is_dir() and (e / "SKILL.md").exists():
                parked.append(e.name)
            elif e.is_file() and e.suffix == ".md":
                parked.append(e.stem)
    return active, parked


def ledger_stats():
    """读账本，返回 {技能名: (used次数, useless次数, 最后使用时间)}。"""
    stats = {}
    if not LEDGER.exists():
        return stats
    for line in LEDGER.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        name = rec.get("skill")
        if not name:
            continue
        used, useless, last = stats.get(name, (0, 0, ""))
        if rec.get("outcome") == "useless":
            useless += 1
        else:
            used += 1
        last = max(last, rec.get("at", ""))
        stats[name] = (used, useless, last)
    return stats


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass

    ap = argparse.ArgumentParser(description="停用/恢复技能（挪目录）")
    ap.add_argument("names", nargs="*", help="技能名（可多个）")
    ap.add_argument("--restore", action="store_true", help="从停放目录挪回扫描根")
    ap.add_argument("--dry", action="store_true", default=True, help="只预演（默认）")
    ap.add_argument("--go", action="store_true", help="真的执行")
    ap.add_argument("--all-unused", action="store_true",
                    help="按账本推荐批量停用（0 次使用 或 useless 过半）")
    args = ap.parse_args()

    active, parked = list_all()
    stats = ledger_stats()

    if args.all_unused:
        # 关键：账本是「从今天起」才开始记的，0 条记录 ≠ 从未使用。
        # 所以只对**账本里有记录**的技能做推荐；没记录的只列出来提示，
        # 不能自动建议停用，否则会把刚建好的技能也推上去。
        names = []
        no_record = []
        for n in active:
            used, useless, _ = stats.get(n, (0, 0, ""))
            if used + useless == 0:
                no_record.append(n)
                continue
            if used == 0 and useless >= 3:
                names.append(n)
            elif used + useless >= 5 and useless * 2 >= used + useless:
                names.append(n)
        if no_record:
            print(f"注意：{len(no_record)} 个技能在账本里没有记录（账本从今天起才记，"
                  f"0 记录不代表没用过）：")
            print("  " + "、".join(f"`{n}`" for n in no_record))
            print()
        if not names:
            print("没有可推荐的技能（有记录的技能里没有明显该停用的）。")
            return 0
        args.names = names
        print(f"按账本推荐停用 {len(names)} 个：{'、'.join(names)}")
        print()

    if not args.names:
        print("# 技能停放状态\n")
        print(f"扫描根：{'、'.join(str(r) for r in ROOTS)}")
        print(f"停放目录：{PARKED}\n")
        print(f"## 启用中（{len(active)}）\n")
        for n in active:
            used, useless, last = stats.get(n, (0, 0, ""))
            tag = "从未使用" if used + useless == 0 else f"用 {used} 次 / 废 {useless} 次"
            print(f"- `{n}` — {tag}" + (f"（最后 {last[:10]}）" if last else ""))
        if parked:
            print(f"\n## 已停用（{len(parked)}）\n")
            for n in parked:
                print(f"- `{n}`")
        print("\n停用：`python park.py <技能名> --dry` → 确认后 `--go`")
        return 0

    rc = 0
    for name in args.names:
        src, state = find_skill(name)
        if not src:
            print(f"✗ 找不到技能：{name}", file=sys.stderr)
            rc = 1
            continue
        if args.restore:
            if state == "active":
                print(f"- {name}：已在启用中，跳过")
                continue
            dst = ROOTS[0] / name
            if dst.exists():
                print(f"✗ {name}：{dst} 已存在，不覆盖", file=sys.stderr)
                rc = 1
                continue
            print(f"- {name}：{src} → {dst}")
        else:
            if state == "parked":
                print(f"- {name}：已停用，跳过")
                continue
            dst = PARKED / name
            if dst.exists():
                print(f"✗ {name}：{dst} 已存在，不覆盖", file=sys.stderr)
                rc = 1
                continue
            print(f"- {name}：{src} → {dst}")

        if not args.go:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        print(f"  ✓ 已挪动")

    if not args.go:
        print("\n（预演模式。确认无误后加 --go 执行。）")
    else:
        print("\n✓ 完成。技能目录会在 DSH 下次刷新时更新。")
    return rc


if __name__ == "__main__":
    sys.exit(main())
