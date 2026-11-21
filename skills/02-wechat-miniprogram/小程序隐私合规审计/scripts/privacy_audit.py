#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
微信小程序隐私接口线索扫描（历史映射，非合规结论）
==========================

用法:
    python privacy_audit.py <小程序根目录>

它做四件事：
  0. 核对隐私开关（__usePrivacyCheck__）与授权链路（onNeedPrivacyAuthorization / requirePrivacyAuthorize）
  1. 按历史映射查找可能涉及隐私的接口文本，输出待核对项（带代码位置）
  2. 对照历史位置接口清单检查 app.json 声明，实际要求需核对当前官方规则
  3. 找出 fail: () => {} 静默失败点，并区分「合理静默」与「需检查」

结果同时落盘到当前目录 privacy_audit.json。
映射表源自历史整理，可能过时或不完整；不判断后台状态，不保证覆盖动态调用或组件行为。
"""
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ---------------------------------------------------------------- 映射表
# 后台项名 -> 触发它的接口 / 组件写法
PRIVACY_MAP = [
    ("收集你的昵称、头像", [
        'open-type="chooseAvatar"', 'type="nickname"', "type='nickname'",
        "wx.getUserInfo", "wx.getUserProfile", 'open-type="userInfo"',
    ]),
    ("收集你的位置信息", [
        "scope.userLocation", "scope.userLocationBackground", "scope.userFuzzyLocation",
        "wx.getLocation", "wx.startLocationUpdate", "wx.getFuzzyLocation", "moveToLocation",
    ]),
    ("收集你选择的位置信息", ["wx.choosePoi", "wx.chooseLocation"]),
    ("收集你的地址", ["wx.chooseAddress"]),
    ("收集你的发票信息", ["wx.chooseInvoiceTitle", "wx.chooseInvoice"]),
    ("收集你的微信运动步数", ["scope.werun", "wx.getWeRunData"]),
    ("收集你的手机号", [
        'open-type="getPhoneNumber"', 'open-type="getRealtimePhoneNumber"',
    ]),
    ("收集你的车牌号", ["wx.chooseLicensePlate"]),
    ("收集你选中的照片或视频信息", [
        "wx.chooseImage", "wx.chooseMedia", "wx.chooseVideo",
    ]),
    ("收集你选中的文件", ["wx.chooseMessageFile"]),
    ("访问你的麦克风", [
        "scope.record", "wx.startRecord", "RecorderManager",
        "<live-pusher", "wx.joinVoIPChat",
    ]),
    ("访问你的摄像头", [
        "scope.camera", "wx.createVKSession", "<camera", "<voip-room",
    ]),
    ("访问你的蓝牙", [
        "scope.bluetooth", "wx.openBluetoothAdapter", "wx.createBLEPeripheralServer",
    ]),
    ("使用你的相册(仅写入)权限", [
        "scope.writePhotosAlbum", "wx.saveImageToPhotosAlbum", "wx.saveVideoToPhotosAlbum",
    ]),
    ("使用你的通讯录(仅写入)权限", [
        "scope.addPhoneContact", "wx.addPhoneContact",
    ]),
    ("使用你的日历(仅写入)权限", [
        "scope.addPhoneCalendar", "wx.addPhoneRepeatCalendar", "wx.addPhoneCalendar",
    ]),
    ("调用你的加速传感器", ["wx.startAccelerometer"]),
    ("调用你的磁场传感器", ["wx.startCompass"]),
    ("调用你的方向传感器", ["wx.startDeviceMotionListening"]),
    ("调用你的陀螺仪传感器", ["wx.startGyroscope"]),
    ("读取你的剪切板", ["wx.setClipboardData", "wx.getClipboardData"]),
]

# requiredPrivateInfos 里必须声明的「地理位置类」接口
GEO_APIS = [
    "getLocation", "getFuzzyLocation", "chooseLocation", "choosePoi",
    "onLocationChange", "startLocationUpdate", "startLocationUpdateBackground",
]
# 互斥对：同时声明会直接报错
MUTEX_PAIRS = [("getLocation", "getFuzzyLocation")]

# 这些场景的失败无需告知用户（用户无感知 / 主要是用户主动取消）
BENIGN_SILENT_HINTS = [
    "showModal", "showActionSheet", "vibrateShort", "vibrateLong", "makePhoneCall",
    "hideLoading", "hideToast", "stopPullDownRefresh", "setNavigationBarColor",
]
# 向上回溯多少行去找"这个 fail 属于哪个调用"
SILENT_LOOKBACK = 40

SKIP_DIRS = {"node_modules", "miniprogram_npm", "_trash", ".git", "cloudfunctions"}
SILENT_RE = re.compile(r"fail\s*:\s*(?:\(\s*\)\s*=>\s*\{\s*\}|function\s*\(\s*\)\s*\{\s*\})")


def iter_src(root):
    """遍历小程序侧源码（跳过依赖、备份、云函数）。"""
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in SKIP_DIRS]
        for f in fn:
            if f.endswith((".js", ".wxml", ".json")):
                yield os.path.join(dp, f)


def is_comment_line(s):
    t = s.strip()
    return t.startswith(("//", "*", "/*", "<!--"))


def rel(root, p):
    return os.path.relpath(p, root).replace("\\", "/")


def read_app_json(root):
    for name in ("app.json", "miniprogram/app.json"):
        p = os.path.join(root, name)
        if os.path.isfile(p):
            try:
                with open(p, encoding="utf-8") as f:
                    return json.load(f), rel(root, p), p
            except Exception as e:
                print("[!] 解析 %s 失败: %s" % (p, e))
    return {}, None, None


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    root = os.path.abspath(sys.argv[1])
    if not os.path.isdir(root):
        print("[!] 目录不存在: %s" % root)
        return 1

    files = list(iter_src(root))
    hits = {}          # 后台项 -> [(rel, line_no, pattern, code)]
    silent = []        # [(rel, line_no, code, context)]
    auth_probe = {}    # 探针 -> [(rel, line_no)]
    geo_used = set()

    for path in files:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()
        except Exception:
            continue
        r = rel(root, path)
        for i, line in enumerate(lines, 1):
            if not is_comment_line(line):
                for api in GEO_APIS:
                    if re.search(r"\bwx\." + re.escape(api) + r"\s*\(", line):
                        geo_used.add(api)
                for item, patterns in PRIVACY_MAP:
                    for p in patterns:
                        if p in line and not is_comment_line(line):
                            hits.setdefault(item, []).append((r, i, p, line.strip()[:110]))
            # 授权链路探针
            for probe in ("onNeedPrivacyAuthorization", "requirePrivacyAuthorize",
                          "openPrivacyContract", "getPrivacySetting"):
                if probe in line and not is_comment_line(line):
                    auth_probe.setdefault(probe, []).append((r, i))
            # 静默失败：向上回溯，找出这个 fail 属于哪个"已知无需告知用户"的调用。
            # 关键：取**缩进最小的候选**（最外层对象字面量）—— 因为
            #   wx.showActionSheet({ success: () => { wx.showModal({...}) }, fail: ... })
            # 里那个 fail 属于外层 showActionSheet，内层 showModal 缩进更深。
            # 只看缩进层级或只看"最近"都会判错。
            if SILENT_RE.search(line) and not is_comment_line(line):
                start = max(0, i - 1 - SILENT_LOOKBACK)
                owner, dist, best_indent = "", -1, 10 ** 9
                for back, txt in enumerate(reversed(lines[start:i])):
                    kw = next((k for k in BENIGN_SILENT_HINTS if k in txt), "")
                    if not kw:
                        continue
                    indent = len(txt) - len(txt.lstrip())
                    if indent < best_indent:
                        owner, dist, best_indent = kw, back, indent
                silent.append((r, i, line.strip(), owner, dist))

    app, app_rel, app_path = read_app_json(root)
    declared = app.get("requiredPrivateInfos", []) or []
    privacy_on = app.get("__usePrivacyCheck__")

    # ---------------- 输出 ----------------
    print("=" * 66)
    print("微信小程序隐私接口线索扫描")
    print("提示：历史映射与正则启发式结果，须核对当前官方规则和后台状态；不是合规或提审结论。")
    print("=" * 66)
    print("工程根目录: %s" % root)
    print("扫描文件数: %d" % len(files))
    print()

    print("───── 0. 隐私开关与授权链路 ─────")
    if privacy_on is True:
        print("__usePrivacyCheck__         : true（只读取配置，未验证运行行为）")
    elif privacy_on is False:
        print("__usePrivacyCheck__         : false（具体要求须核对当前基础库和后台）")
    else:
        print("__usePrivacyCheck__         : 未设置 ⚠")
    for probe, label in [
        ("onNeedPrivacyAuthorization", "onNeedPrivacyAuthorization（授权弹窗回调）"),
        ("requirePrivacyAuthorize", "requirePrivacyAuthorize（调用隐私接口前的授权门）"),
        ("openPrivacyContract", "openPrivacyContract（打开协议原文）"),
        ("getPrivacySetting", "getPrivacySetting（查询授权状态）"),
    ]:
        loc = auth_probe.get(probe, [])
        if loc:
            where = ", ".join("%s:%d" % (a, b) for a, b in loc[:3])
            print("%-28s: 发现文本引用，未验证执行  (%s%s)" % (
                label, where, " …" if len(loc) > 3 else ""))
        else:
            print("%-28s: 未发现直接文本引用（不代表不存在）" % label)
    print()

    print("───── 1. 历史映射命中的待核对项（共 %d 项）─────" % len(hits))
    print("后台路径：设置 → 服务内容声明 → 用户隐私保护指引")
    if not hits:
        print("  未命中当前映射；仍需检查封装、动态调用与 WXML 组件。")
    for idx, (item, locs) in enumerate(hits.items(), 1):
        print("[%d] %s    (%d 处调用)" % (idx, item, len(locs)))
        shown = {}
        for r, i, p, code in locs:
            key = (r, p)
            if key in shown:
                continue
            shown[key] = True
            print("      %s:%d  →  %s" % (r, i, p))
    print()
    print("  ⚠ 以后台的实际提示为准：后台会根据提交版本自动把调用到的接口标为必填，标红的一律不能漏。")
    print("  声明应与真实功能一致；扫描结果不能直接确定应勾选项。")
    print()

    print("───── 2. requiredPrivateInfos 校验 ─────")
    if app_rel:
        print("配置文件        : %s" % app_rel)
        print("当前声明        : %s" % (declared if declared else "[]（空）"))
        missing = []
        for api in GEO_APIS:
            used = api in geo_used
            if used and api not in declared:
                missing.append(api)
        if missing:
            for api in missing:
                print("  待核对：发现 %s 直接调用，app.json 未列出该项；如当前规则要求，可能出现：" % api)
                print("     %s:fail the api need to be declared in the requiredPrivateInfos field in app.json" % api)
            print("     仅在当前规则要求后再补声明；不要直接按历史清单修改配置。")
        else:
            print("  本次直接调用与历史清单对照未见缺项；不代表全部位置接口均已覆盖。")
        for a, b in MUTEX_PAIRS:
            if a in declared and b in declared:
                print("  待核对历史互斥提示：%s 与 %s 同时出现，请查当前官方规则。" % (a, b))
        if declared:
            print("  ℹ 另需在后台「开发 → 开发管理 → 接口设置」开通对应接口，光改 app.json 不够。")
    else:
        print("  ⚠ 未找到 app.json")
    print()

    print("───── 3. 静默失败点（fail: () => {}）─────")
    if not silent:
        print("  未发现 ✅")
    else:
        need_check = []
        for r, i, code, owner, dist in silent:
            if owner:
                print("  · %s:%d  （疑似合理静默：附近 %s，向上约 %d 行）"
                      % (r, i, owner, dist))
            else:
                print("  ! %s:%d  ⚠ 需检查  ← %s" % (r, i, code))
                need_check.append((r, i))
        print()
        if need_check:
            print("  需检查的 %d 处：失败时用户看到的是「点了没反应」，应改为给可读原因 + console.error 原始 errMsg。" % len(need_check))
        else:
            print("  全部命中附近关键词，仍须按语法结构与真实失败原因核对；不代表可安全忽略。")
        print("  ℹ 判定是启发式的：向上回溯 %d 行找最近的已知调用，请对「需检查」项人工过一眼。" % SILENT_LOOKBACK)
    print()

    print("───── 4. 需要另行核对的后台状态 ─────")
    print("  对照真实功能、当前官方说明与已授权后台入口检查声明、用途、联系信息和接口设置。")
    print("  本脚本未访问后台，不能判断配置是否完成；也未执行真机授权测试。")
    print()

    out = {
        "root": root,
        "heuristic_only": True,
        "direct_geo_calls": sorted(geo_used),
        "privacy_check_enabled": privacy_on,
        "declared_required_private_infos": declared,
        "need_declare_items": {k: [{"file": a, "line": b, "pattern": c} for a, b, c, _ in v]
                               for k, v in hits.items()},
        "silent_failures": [{"file": a, "line": b, "code": c, "near": d, "up_lines": e}
                            for a, b, c, d, e in silent],
    }
    with open("privacy_audit.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("结果已写入 privacy_audit.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
