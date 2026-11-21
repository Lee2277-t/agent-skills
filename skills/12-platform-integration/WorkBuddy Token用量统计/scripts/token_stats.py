"""Summarize recorded WorkBuddy usage fields; this is not a billing estimator."""
import argparse
import datetime
import json
from pathlib import Path


FIELDS = ("input_tokens", "output_tokens", "cache_read_input_tokens", "total_tokens")


def number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0 else None


def collect(projects):
    sessions = {}
    malformed = 0
    for path in sorted(projects.glob("*/*.jsonl")):
        session = sessions.setdefault(path.parent.name, {"records": {}, "anonymous": [], "title": ""})
        with path.open(encoding="utf-8-sig") as stream:
            for line in stream:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    malformed += 1
                    continue
                if not isinstance(record, dict):
                    malformed += 1
                    continue
                if record.get("type") == "ai-title" and isinstance(record.get("aiTitle"), str):
                    session["title"] = record["aiTitle"]
                message = record.get("message")
                if not isinstance(message, dict) or not isinstance(message.get("usage"), dict):
                    continue
                usage = {key: number(message["usage"].get(key)) for key in FIELDS}
                identity = message.get("id") or record.get("id")
                if isinstance(identity, (str, int)) and not isinstance(identity, bool):
                    session["records"][str(identity)] = usage
                else:
                    session["anonymous"].append(usage)
    return sessions, malformed


def render(projects, sessions, malformed):
    lines = [
        "WorkBuddy 日志用量统计（非账单或剩余额度）",
        "数据源: " + str(projects),
        "统计时间: " + datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "口径: 会话内稳定 ID 按文件名和行顺序保留最后读取的 usage；无 ID 记录逐条计入。",
        "不推断缓存包含关系；缺失 total 不用输入输出补齐。",
        "无效 JSON/非对象记录: " + str(malformed),
        "",
    ]
    all_usage = []
    anonymous = 0
    for name, session in sorted(sessions.items()):
        usage = list(session["records"].values()) + session["anonymous"]
        all_usage.extend(usage)
        anonymous += len(session["anonymous"])
        lines += ["[" + name + "] " + session["title"],
                  "  用量记录数: " + str(len(usage)),
                  "  无稳定 ID 记录: " + str(len(session["anonymous"]))]
        for key in FIELDS:
            values = [item[key] for item in usage if item[key] is not None]
            value = format(sum(values), ",") if values else "未提供"
            lines.append("  " + key + ": " + value + "（缺失 " + str(len(usage) - len(values)) + "）")
        lines.append("")
    lines += ["=== 已记录字段合计 ===", "会话目录数: " + str(len(sessions)),
              "用量记录数: " + str(len(all_usage)), "无稳定 ID 记录: " + str(anonymous)]
    for key in FIELDS:
        values = [item[key] for item in all_usage if item[key] is not None]
        value = format(sum(values), ",") if values else "未提供"
        lines.append(key + ": " + value + "（缺失 " + str(len(all_usage) - len(values)) + "）")
    lines.append("字段口径依日志版本而异；不能据此换算费用或认定账单完整。")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--projects", type=Path, default=Path.home() / ".workbuddy" / "projects")
    parser.add_argument("--output", type=Path, default=Path.cwd() / "Token用量统计.txt")
    args = parser.parse_args()
    projects = args.projects.expanduser().resolve()
    if not projects.is_dir():
        parser.error("日志根目录不存在: " + str(projects))
    if not next(projects.glob("*/*.jsonl"), None):
        parser.error("未发现会话日志；不能将其解释为零用量")
    sessions, malformed = collect(projects)
    report = render(projects, sessions, malformed)
    output = args.output.expanduser().resolve()
    if output.is_relative_to(projects):
        parser.error("报告不能写入日志源目录")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report + "\n", encoding="utf-8")
    print(report)
    print("\n已写入: " + str(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
