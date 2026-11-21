#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""技能使用账本：记一行，长期看哪些技能该停用。

用法：
    python ledger.py add <技能名> --task "用户原话" --outcome used
    python ledger.py add <技能名> --task "…" --outcome useless
    python ledger.py report          # 汇总
    python ledger.py report --json
    python ledger.py tail -n 10      # 最近 10 条

为什么需要它：
  DSH 的会话日志是 zstd 多帧压缩（`~/.dsh/sessions/**/session.v4.jsonl.zstd`），
  Node 的 zstdDecompressSync 只能解首帧，无法可靠统计历史上加载过哪些技能。
  所以使用记录只能从今天起自己记。

账本格式：一行一个 JSON（jsonl），追加写，不会损坏前面的记录。
位置：~/.dsh/skill-ledger.jsonl
"""
import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

LEDGER = Path.home() / ".dsh" / "skill-ledger.jsonl"


def now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def read_all():
    if not LEDGER.exists():
        return []
    out = []
    for line in LEDGER.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def cmd_add(args):
    if args.outcome not in ("used", "useless"):
        print("✗ --outcome 只能是 used 或 useless", file=sys.stderr)
        return 3
    rec = {
        "at": now(),
        "skill": args.skill,
        "task": args.task or "",
        "outcome": args.outcome,
    }
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"✓ 已记录：{rec['skill']} / {rec['outcome']}")
    return 0


def cmd_report(args):
    recs = read_all()
    if not recs:
        print(f"账本是空的（{LEDGER}）。")
        print("用 `python ledger.py add <技能名> --task \"…\" --outcome used` 开始记。")
        return 0

    per = {}
    for r in recs:
        n = r.get("skill")
        if not n:
            continue
        d = per.setdefault(n, {"used": 0, "useless": 0, "last": "", "tasks": []})
        if r.get("outcome") == "useless":
            d["useless"] += 1
        else:
            d["used"] += 1
        d["last"] = max(d["last"], r.get("at", ""))
        if r.get("task"):
            d["tasks"].append(r["task"][:40])

    if args.json:
        print(json.dumps(per, ensure_ascii=False, indent=2))
        return 0

    first = min(r.get("at", "") for r in recs)[:10]
    last = max(r.get("at", "") for r in recs)[:10]
    print("# 技能使用账本\n")
    print(f"共 {len(recs)} 条记录，{first} → {last}，涉及 {len(per)} 个技能\n")
    print("| 技能 | 用 | 废 | 最后 | 建议 |")
    print("|---|---|---|---|---|")
    for n, d in sorted(per.items(), key=lambda x: -(x[1]["used"] + x[1]["useless"])):
        total = d["used"] + d["useless"]
        if total >= 3 and d["used"] == 0:
            advice = "**该停用**（一次都没用上）"
        elif total >= 5 and d["useless"] * 2 >= total:
            advice = "**该停用**（废用率过半）"
        elif total == 1 and d["useless"] == 1:
            advice = "继续观察（样本太少）"
        elif d["used"] >= 3:
            advice = "留着"
        else:
            advice = "继续观察"
        print(f"| `{n}` | {d['used']} | {d['useless']} | {d['last'][:10]} | {advice} |")
    print()
    print("停用：`python park.py <技能名> --dry` → 确认后 `--go`")
    return 0


def cmd_tail(args):
    recs = read_all()[-args.n:]
    for r in recs:
        print(f"{r.get('at','')[:19]}  {r.get('skill','?'):28} {r.get('outcome','?'):8} {r.get('task','')[:50]}")
    if not recs:
        print("（空）")
    return 0


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass

    ap = argparse.ArgumentParser(description="技能使用账本")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="记一条")
    a.add_argument("skill")
    a.add_argument("--task", default="")
    a.add_argument("--outcome", default="used", choices=["used", "useless"])
    a.set_defaults(func=cmd_add)

    r = sub.add_parser("report", help="汇总")
    r.add_argument("--json", action="store_true")
    r.set_defaults(func=cmd_report)

    t = sub.add_parser("tail", help="最近几条")
    t.add_argument("-n", type=int, default=10)
    t.set_defaults(func=cmd_tail)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
