---
name: tkinter-gui-headless-e2e-qa
description: "通过应用入口与控件级驱动验证 Windows Tkinter 工具的关键流程，检查输出、日志和窗口状态。真实 GUI 验收需要可用桌面会话，不把隐藏窗口或逻辑测试称为完全无显示环境运行。"
---

# tkinter GUI 无人值守端到端验收

## Overview

在控制台进程里直接把 tkinter 应用「跑起来并问它要证据」：不点鼠标、不依赖人工，
驱动 → 轮询 → 取界面日志 → 文件指纹取证 → 抓窗口像素截图。适用于离线/保密模式验收、
「不写日志不落缓存」证明、GUI 截图交付。

## 何时用

- 验收只在 GUI 里发生的行为（界面日志、状态栏、按钮禁用、取消流程）。
- 需要证明某模式下 `logs/`、`cache/` 里的文件**没有**被写。
- 需要一张确实是这个窗口的截图，而 `ImageGrab` 截到了别的窗口或只有左上角。

## 铁律：顺序不能变

`sys.argv` 改写 **必须早于** `import` 被测模块。

```python
sys.argv = ["app", "--offline"]        # 模式开关在模块顶层求值
import app                            # OFFLINE = "--offline" in sys.argv[1:]
qa = app.TranslatorApp()              # 构造里才会设 DPI、建 root
```

反过来 import 在前，`--offline` 这类开关永远是 False，测试会「绿得毫无意义」。
DPI 感知同理：必须在任何窗口句柄被使用之前设，且一个进程只能设一次；被测 app 构造里
的 `SetProcessDpiAwareness(1)` 失败会被 `except: pass` 静默吞掉，所以 QA 进程自己先设成
per-monitor-v2（`-4`）/ per-monitor（`2`）。

## 主流程

1. **摸清驱动面**（每个 app 方法名不同，先 grep 再用）：

   ```
   grep -n "def set_file\|def start_translation\|def cancel\|self.busy\|log_text\|--offline" app.py
   ```

   需要的五样：注入文件的 setter、启动方法、一个 `busy` 布尔、界面日志控件、完成标志
   （如 `output_path`）。日志控件是 `tk.Text` 时读取写 `widget.get("1.0", "end-1c")`。

2. **驱动并轮询**：调 setter → 调 start → 循环 `root.update(); time.sleep(poll)`，
   直到 `app.busy` 变 False 或撞上 `--timeout` 总闸。`update()` 会执行 `after()` 排队的
   回调，因此工作线程投进 `queue` 的 progress/done/error 事件能落地；若某 app 用别的泵，
   显式补调一次（`--pump-callback`）。窗口默认挪到 `-32000,-32000` 免得挡住用户，
   `PrintWindow` 照样渲染。

3. **取界面日志**：任务结束后再 `update()` 几轮，才读得到 `_on_done` 写入的最后几行。

4. **落盘取证**：任务前后对 `logs/app.log`、`cache/` 做快照比对。
   **size + mtime 不够**：SQLite 原地写页可能 mtime 变、size 不变，或反之，所以再加
   sha256（≤8 MB 的文件）。目录也支持，逐文件指纹。

5. **截图**：用 `capture_window.py`（`PrintWindow(hwnd, dc, PW_RENDERFULLCONTENT)` +
   `GetDIBits`）抓指定句柄，别用 `ImageGrab`。用 `ImageStat` 的标准差判空白，
   空白就退出码 2，不要拿空白图当证据。

## 反模式（本项目实测踩过的）

| 做法 | 后果 | 换这个 |
| --- | --- | --- |
| `PIL.ImageGrab.grab()` | `SetForegroundWindow` 后焦点被别窗抢走，截到背景浏览器 | `--hwnd`/`--title` 走 PrintWindow |
| 未设 DPI 就 `GetWindowRect` | 高 DPI 下返回虚拟化坐标，只截到窗口左上角约 1/4 | 进程启动即 `SetProcessDpiAwarenessContext(-4)` |
| 用 `PrintWindow(hwnd, dc, 0)` | 部分 GPU 合成控件返回全黑 | flags=2，再不行 `--method PrintWindow-0` / `screen-bitblt` 并标注证据更弱 |
| 只比 size/mtime | 「没落盘」结论不成立 | 加 sha256 |
| 调 `open_output` / 打开目录按钮 | 真的拉起系统程序、弹资源管理器 | 只读 `output_path` 并 `os.path.exists` |
| 只看 stdout | 界面报错看不见 | 读 `log_text`，含「失败/错误/Error」的行单独挑出来 |

## 脚本

`scripts/drive_tk_app.py` —— 驱动 + 轮询 + 界面日志 + 文件指纹 + 截图，一次跑完：

```bash
python scripts/drive_tk_app.py \
  --app-dir "<project-root>/translator" --module app --class TranslatorApp \
  --flag=--offline --file "D:/tmp/qa/示例.docx" \
  --watch "<project-root>/translator/logs/app.log" --watch "<project-root>/translator/cache" \
  --shot "D:/tmp/qa/shot.png" --out-dir "D:/tmp/qa" --timeout 180
```

输出行为 `DRIVE verdict=… elapsed=… log_lines=… output_exists=…`、
`FORENSICS changed|before|after …`、`UI_LOG_BEGIN/END`。
退出码 0=通过，2=超时/应用报错/截图空白，3=起不来。

```bash
python scripts/capture_window.py --title 翻译工具 --out shot.png --pid 4321
```

`--restore` 用于被最小化的窗口；`--hwnd` 优先（在驱动脚本里用
`root.winfo_pathname(root.winfo_id())` 取客户区句柄，别用带边框的 WM 帧）。

## 收尾与红线

- 测试文档复制到临时目录再喂给 app：译文写在源文件旁边，会污染用户真实文件。
- 结束必须 `root.destroy()`，并确认没有残留 `pythonw`/窗口进程。
- `--offline` 这类开关常在模块顶层 monkeypatch `socket`，同一进程后续任何联网都会失败；
  需要联网的后续步骤另起进程。
- 报告里区分「界面日志显示成功」与「文件确实存在」，两者都要有。
