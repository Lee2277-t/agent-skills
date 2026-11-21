#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""汇总回归 / 命令行报告 JSON，输出可写进文档的标准数字。

用法：
    python summarize-reports.py tests/regress-report.json tests/cli-report.json

支持三种形状：
    {"ok": bool, "results": [{"name": ..., "ok": ..., "ms": ...}, ...]}
    {"ok": bool, "cases": 298, "failed": [...]}
    {"cases": [...], "failed": [...]}            # 引擎级报告

任一报告判定失败则退出码为 1，可直接当收尾门禁。
"""
import json
import os
import sys


def load(path):
    if not os.path.exists(path):
        return None, '缺少文件'
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f), None
    except Exception as exc:
        return None, 'JSON 解析失败：%s' % exc


def summarize(label, data):
    """返回 (是否通过, 单行摘要, 问题)。"""
    if 'results' in data and isinstance(data['results'], list):
        results = data['results']
        failed = [str(r.get('name', '?')) for r in results if not r.get('ok')]
        total = sum(int(r.get('ms') or 0) for r in results)
        ok = bool(data.get('ok')) and not failed
        line = '%-8s ok=%-5s cases=%d  sum_ms=%d  (%.1f s)' % (
            label, str(ok).lower(), len(results), total, total / 1000.0)
        return ok, line, failed

    if isinstance(data.get('cases'), int):
        failed = data.get('failed') or []
        ok = bool(data.get('ok')) and not failed
        line = '%-8s ok=%-5s cases=%d failed=%d' % (
            label, str(ok).lower(), data['cases'], len(failed))
        return ok, line, failed

    if isinstance(data.get('cases'), list):
        failed = data.get('failed') or []
        ok = bool(data.get('ok')) and not failed
        line = '%-8s ok=%-5s cases=%d failed=%d' % (
            label, str(ok).lower(), len(data['cases']), len(failed))
        return ok, line, failed

    return False, '%-8s 不认识这个报告的字段' % label, ['unknown-shape']


def main(argv):
    if len(argv) < 2:
        print(__doc__.strip())
        return 2

    all_ok = True
    for path in argv[1:]:
        label = os.path.splitext(os.path.basename(path))[0].replace('-report', '')
        data, err = load(path)
        if err:
            print('%-8s ERROR %s (%s)' % (label[:8], err, path))
            all_ok = False
            continue
        ok, line, failed = summarize(label[:8], data)
        print(line)
        if failed:
            print('         failed: %s' % ', '.join(str(x) for x in failed[:10]))
        all_ok = all_ok and ok

    print('ALL OK' if all_ok else 'HAS FAILURE')
    return 0 if all_ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
