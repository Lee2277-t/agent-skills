---
name: windows-tkinter-desktop-tool
description: "将 Windows Tkinter 工具完善为可交付应用，处理 DPI、线程通信、可选拖放与启动反馈。沿用现有界面和分发约定，不因使用本技能强制增加依赖或重绘全部控件。"
---

# Windows tkinter 桌面工具交付

## Overview

把「能跑的 tkinter 脚本」变成「非技术同事双击即用、高 DPI 不糊、拖拽可用、不闪退」的成品。
顺序敏感项集中在启动前三行；其余是线程模型与降级策略。

## 何时用 / 不用

- 用：Windows 上 tkinter 桌面小工具（文件拖入 → 处理 → 产出文件），需要 `.bat` 双击交付。
- 不用：网页/浏览器工具、Electron 应用；tkinter 的端到端验收与窗口截图（用
  `tkinter-gui-headless-e2e-qa`，本 skill 只保证代码「可被驱动」）。

## 1. 铁律：DPI 感知必须早于 `Tk()`

`SetProcessDpiAwareness` 是**每进程一次、不可回退**的调用，且必须在任何 Tk 窗口创建之前，
否则系统已按 96 DPI 虚拟化，之后再设只报 `E_ACCESSDENIED` 且被 `except: pass` 静默吞掉。

```python
def _enable_dpi_awareness() -> float:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)   # 系统级感知；失败会被静默吞掉
    except Exception:
        pass
    try:
        dpi = ctypes.windll.user32.GetDpiForSystem()
    except Exception:
        dpi = 96
    return max(1.0, dpi / 96.0)

# __init__ 第一句就取 scale，再建 root，紧接着校准字体
self.scale = _enable_dpi_awareness()
self.root = tk.Tk()
self.root.tk.call("tk", "scaling", self.scale * 96 / 72)   # = dpi / 72
```

症状对照：

| 现象 | 根因 |
| --- | --- |
| 字和边框发虚、整体偏小到左上角 | DPI 没设或设晚于 `Tk()` |
| 125%/150% 下控件挤在一起、文字被截断 | 布局尺寸是硬编码像素，没走 `px()` |
| 字号看起来对但行高/padding 不协调 | 缺 `tk scaling` 调用 |

感知级别选 `1`（system-aware）即可满足本应用。但同一次调用会影响**整个进程**，若另起脚本要按
`GetWindowRect` 量窗口（截图验收），`1` 拿到的是虚拟化坐标，那种进程自己改用 per-monitor
（`2` / `SetProcessDpiAwarenessContext(-4)`），别指望改本应用的级别。

## 2. 两套缩放，各管一半

`px()` 管我们自己画的几何量，`tk scaling` 管 Tk 自己的字体度量；只做一套会半糊半乱。

```python
def px(self, value: float) -> int:
    return max(1, int(round(value * self.scale)))
```

把 `px()` 当构造函数唯一的尺寸入口：`geometry`、`minsize`、`padx/pady`、`trigwidth`、
Canvas 的圆心/半径/边距/`width=` 一律 `self.px(...)`，基线值按 96 DPI 设计稿写。
窗口尺寸要夹到屏幕内（`winfo_screenwidth() - px(40)`），150% 缩放下的 660×660 会顶出屏幕。

## 3. 拖拽：可用是运气，降级是责任

`tkinterdnd2` 要装进随工具一起打包的那个 venv，且需要带 Tk 库的 CPython；换机器就可能失败。
所以**两段都要 try/except**，用 `dnd_ready` 标志分叉，并永远保留点击选文件：

```python
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except Exception:
    DND_FILES = None
    TkinterDnD = None

self.dnd_ready = False
if TkinterDnD is not None:
    try:
        self.root = TkinterDnD.Tk()
        self.dnd_ready = True
    except Exception:
        self.root = tk.Tk()
else:
    self.root = tk.Tk()

# 建完 UI 后
self.drop.bind("<Button-1>", lambda e: self.choose_file())     # 降级路径，必须留
if self.dnd_ready:
    try:
        self.drop.drop_target_register(DND_FILES)
        self.drop.dnd_bind("<<DropEnter>>", self._on_drop_hover)
        self.drop.dnd_bind("<<DropLeave>>", self._on_drop_leave)
        self.drop.dnd_bind("<<Drop>>", self._on_drop)
    except Exception:
        self.dnd_ready = False
        logger.exception("拖放功能初始化失败")
```

- 路径解析用 `list(self.root.tk.splitlist(event.data))`，**不要** `event.data.split()`：
  Windows 路径含空格和括号（`(1)`、`Program Files`）会被切碎；`splitlist` 失败才退回单值。
- 高亮态 `hover` 由 `<<DropEnter>>/<<DropLeave>>` 与 `<Enter>/<Leave>` 共同驱动，且 `busy` 时
  强制不高亮，否则拖进来却在处理中，视觉在骗人。
- 拖入的可能是目录、多文件、无扩展名文件：在入口一次性校验 `os.path.isfile` + 白名单扩展名，
  给出「一次一个文件」这类明确提示，别让 worker 抛栈。

## 4. 线程模型：worker 只投队列

子线程调用任何 `widget.configure()/delete()` 会随机崩溃或 TclError。固定这套：
`queue.Queue` + 单一 `after()` 泵 + `threading.Event` 取消。

```python
self.events: queue.Queue = queue.Queue()

def _pump_events(self) -> None:
    try:
        while True:
            event = self.events.get_nowait()
            kind = event[0]
            if kind == "log": ...
            elif kind == "progress": ...
            elif kind == "done": ...
            elif kind == "error": ...
            elif kind == "cancelled": ...
    except queue.Empty:
        pass
    try:
        if self.root.winfo_exists():
            self.root.after(80, self._pump_events)
    except tk.TclError:
        pass
```

要点（照抄可省一整天）：

- 泵在 `__init__` 末尾启动一次，之后自续期；`winfo_exists()` + `TclError` 双保险，
  否则关窗瞬间 `after` 回调炸栈。
- 线程侧只有三个写入口：`emit_log(msg)` 投 `("log", msg)`、`_queue_progress()` 投
  `("progress", done, total, msg)`、收尾投 `("done"|"error"|"cancelled", ...)`。
  日志方法同时 `logger.info` 一次，界面与文件日志同源。
- `stop_event` 在启动时**新建并作为参数传给线程**（`args=(path, ocr, stop_event)`），
  别让线程读 `self.stop_event`，否则下一次任务会读到被覆盖的新对象。
- 取消在段落/页边界检查（`check_cancel(stop_event)`），点取消先 `configure(state="disabled")`
  并写「正在取消，请稍候…」——用户需要知道这是异步的。
- 每个终态（done/error/cancelled）都必须重置 `busy`、`stop_event=None`、`progress.stop()`
  并重绘，漏一个就永久卡在忙态。
- 首帧到真正开工之间常有秒级开销（导入模型、OCR 引擎）：先置 `mode="indeterminate"` +
  `start(14)` 并写明「首次需加载本地模型」，拿到 `total` 再切 `determinate`；
  不给反馈会被当成卡死。
- `daemon=True`，配合 `protocol("WM_DELETE_WINDOW", ...)`：`busy` 时先确认再 `stop_event.set()`，
  避免关窗留下孤儿子进程。

## 5. 主题与自绘控件

`style.theme_use("clam")`（`try/except TclError`）是唯一肯老实吃 `background`/`relief` 的常见主题。
扁平按钮要把 `bordercolor/lightcolor/darkcolor/focuscolor` 全设成同一个色，并在 `style.map()`
里给 `disabled/pressed/active`，不然禁用态仍留渐变边框。

需要「开关」样式时别改 Checkbutton 指示器（`clam` 下指示器形状改不动、成品观感差），
直接用 Canvas 自绘：`tk.Frame` 装 `tk.Canvas`（轨道）+ `tk.Label`（文案）。

- `<Button-1>` 要绑在 Frame、Canvas、Label **三个**上，只绑轨道会导致点文字无效。
- 每次状态变化 `canvas.delete("all")` 后整块重画；`set_enabled()` 里同步换 cursor 和文字颜色。
- Canvas 没有圆角矩形，用 12 点 `create_polygon(..., smooth=True)` 近似；圆角半径取高度一半。
- 尺寸同样走 `px()`，轨道 38×22、滑块内缩 3 是实测协调的起点值。

## 6. 双击交付的启动器

随工具打包一个 `.venv`，启动器只做「存在性自检 + 脱离终端启动」：

```bat
@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Runtime not found. Please keep the .venv folder next to this file.
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "%~dp0app.py" --offline
```

- GUI 用 `pythonw.exe`（无黑框）；安装/下载类脚本用 `python.exe` + 末尾 `pause`，让用户看得见结果。
- `start` 的第一个 `""` 是窗口标题，省掉它带空格的路径会被当成标题。
- 目标脚本传 `"%~dp0app.py"` 绝对路径：`start` 之后的 CWD 不可信。
- bat 正文尽量只用 ASCII 提示词；要中文则 UTF-8 无 BOM + 首行后 `chcp 65001 >nul`，且 CRLF。
- 从 Git Bash 里 `cmd //c "X.bat"` 时 `start ""` 会**永久挂起**（MSYS 环境已知坑）。
  这是自测方式问题，不是 bat 问题；双击仍是 `start`，脚本内自测改 `powershell Start-Process`。
  详见记忆 `win-batch-launcher-env`。
- 按模式分多个 bat（普通/保密/安装依赖），文件名用用户语言，别让用户改命令行。

## 7. 交付时顺手留出「可驱动面」

验收脚本靠名字找入口，所以写代码时就固定这几样，公开且无副作用：
`set_file(path)` 或 `choose_file()`、`start_translation()`、`cancel_translation()`、
布尔 `busy`、`output_path`、界面日志用 `tk.Text`（读取用 `get("1.0", "end-1c")`）。
窗口标题取稳定字符串，供按标题找句柄。之后直接交给 `tkinter-gui-headless-e2e-qa` 跑无人值守验收。

## 反模式

| 做法 | 后果 |
| --- | --- |
| 建完窗口再设 DPI | 全程被 96 DPI 虚拟化，缩放全废 |
| 只改 `tk scaling` 不缩自己的坐标 | 字体对了，Canvas 画布与 padding 仍是小图 |
| `event.data.split()` 解析拖入路径 | 含空格目录被切成多个假文件 |
| worker 里 `self.label.configure(...)` | 偶发 TclError / 整个进程闪退 |
| 泵里不判 `winfo_exists()` | 关窗瞬间报一大段 TclError 栈 |
| 拖拽不做降级、不装 tkinterdnd2 就 `import` 崩 | 换机器直接起不来，且没人知道为什么 |
| 交付 zip 不带 `.venv` 或带指向原机器的绝对路径 venv | venv 不可移植，双击只会闪一下 |
| 保密模式下把完整路径写进界面日志 | 界面即泄露；只 `os.path.basename()`，日志文件在该模式直接不写 |

## Resources

- `references/recipes.md` —— 可直接粘贴的完整片段：DPI 引导、`px()` 布局、拖拽桥接、
  队列泵与取消状态机、`ToggleSwitch` 与圆角矩形、扁平 ttk 样式、启动器模板、venv 自检命令。
