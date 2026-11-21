# 可直接粘贴的片段

来源为已交付并跑通端到端验收的 Windows tkinter 工具（Python 3.13 + Tk 8.6 + tkinterdnd2 0.6.4，
`.venv` 随包分发，双击 bat 启动）。按项目改名后即可用。

## 1. 启动顺序（模块顶层 → main）

模式开关在模块顶层求值，`--offline` 这类开关常在这里 monkeypatch `socket`，因此同进程后续任何
联网都会失败；需要联网的自检步骤另起进程。

```python
import ctypes, sys

OFFLINE = "--offline" in sys.argv[1:]

def _enable_dpi_awareness() -> float:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    try:
        dpi = ctypes.windll.user32.GetDpiForSystem()
    except Exception:
        dpi = 96
    return max(1.0, dpi / 96.0)

def main() -> None:
    app = TranslatorApp()      # 构造里设 DPI → 建 root → tk scaling → 建 UI → 起泵
    app.root.mainloop()

if __name__ == "__main__":
    main()
```

## 2. root 与缩放

```python
class TranslatorApp:
    def __init__(self) -> None:
        self.scale = _enable_dpi_awareness()
        self.dnd_ready = False
        if TkinterDnD is not None:
            try:
                self.root = TkinterDnD.Tk()
                self.dnd_ready = True
            except Exception:
                self.root = tk.Tk()
        else:
            self.root = tk.Tk()
        self.root.tk.call("tk", "scaling", self.scale * 96 / 72)   # dpi / 72

        self.events: queue.Queue = queue.Queue()
        self.stop_event: threading.Event | None = None
        self.worker_thread: threading.Thread | None = None
        self.src_path: str | None = None
        self.output_path: str | None = None
        self.busy = False
        self.drop_hover = False

        self._setup_window()
        self._setup_style()
        self._build_ui()
        self._bind_events()
        self._pump_events()          # 必须启动，否则线程投的事件永远不落界面

    def px(self, value: float) -> int:
        return max(1, int(round(value * self.scale)))
```

## 3. 窗口尺寸夹进屏幕

```python
    def _setup_window(self) -> None:
        self.root.title("文档翻译工具")
        self.root.configure(bg=BG)
        if ICON_PATH.exists():
            try:
                self.root.iconbitmap(default=str(ICON_PATH))
            except tk.TclError:
                pass
        width, height = self.px(660), self.px(660)
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        width = min(width, screen_w - self.px(40))
        height = min(height, screen_h - self.px(80))
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2 - self.px(12))
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.minsize(self.px(600), self.px(620))
```

## 4. 圆角矩形（Canvas 无原语）

`smooth=True` 的多边形近似圆角；半径取高度一半即胶囊形。

```python
def _canvas_round_rect(canvas, x1, y1, x2, y2, radius, **kwargs):
    points = [
        x1 + radius, y1, x2 - radius, y1, x2, y1,
        x2, y1 + radius, x2, y2 - radius, x2, y2,
        x2 - radius, y2, x1 + radius, y2, x1, y2,
        x1, y2 - radius, x1, y1 + radius, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)
```

拖放区在 `<Configure>` 上重画（宽度随窗口变），基线值仍走 `px()`：

```python
    def _draw_dropzone(self, _event=None) -> None:
        canvas = self.drop
        canvas.delete("all")
        width, height = canvas.winfo_width(), canvas.winfo_height()
        if width <= 1 or height <= 1:          # 首次 Configure 前是 1，画了会报错
            return
        edge = self.px(2)
        hover = self.drop_hover and not self.busy
        _canvas_round_rect(canvas, edge, edge, width - edge, height - edge,
                           self.px(14), fill="#f8fbff" if hover else CARD,
                           outline=ACCENT if hover else BORDER, width=self.px(1))
        cx = width / 2
        icon_y = height * 0.29
        r = self.px(21)
        canvas.create_oval(cx - r, icon_y - r, cx + r, icon_y + r, fill=ACCENT_SOFT, outline="")
```

## 5. 自绘开关（替代 Checkbutton 指示器）

```python
class ToggleSwitch(tk.Frame):
    def __init__(self, master, text: str, value: bool, px, bg: str) -> None:
        super().__init__(master, bg=bg)
        self._px = px
        self._value = value
        self._enabled = True
        self._track_w, self._track_h = px(38), px(22)
        self._canvas = tk.Canvas(self, width=self._track_w, height=self._track_h,
                                 bg=bg, highlightthickness=0, cursor="hand2")
        self._canvas.pack(side="left")
        self._label = tk.Label(self, text=text, font=(FONT, 9), fg=TEXT, bg=bg, cursor="hand2")
        self._label.pack(side="left", padx=(px(8), 0))
        for widget in (self, self._canvas, self._label):    # 三处都绑，点文字才有效
            widget.bind("<Button-1>", self._on_click)
        self._draw()

    def get(self) -> bool:
        return self._value

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        cursor = "hand2" if enabled else "arrow"
        for widget in (self, self._canvas):
            widget.configure(cursor=cursor)
        self._label.configure(cursor=cursor, fg=TEXT if enabled else "#9aa8ba")
        self._draw()

    def _on_click(self, _event=None) -> None:
        if not self._enabled:
            return
        self._value = not self._value
        self._draw()

    def _draw(self) -> None:
        c, w, h = self._canvas, self._track_w, self._track_h
        c.delete("all")
        if not self._enabled:
            track, knob = "#e2e8f0", "#f8fafc"
        elif self._value:
            track, knob = ACCENT, "#ffffff"
        else:
            track, knob = "#c3cfdd", "#ffffff"
        _canvas_round_rect(c, 0, 0, w, h, h / 2, fill=track, outline=track)
        pad = self._px(3)
        d = h - pad * 2
        left = w - pad - d if self._value else pad
        c.create_oval(left, pad, left + d, pad + d, fill=knob, outline="")
```

## 6. 拖拽接收与路径解析

```python
    def _bind_events(self) -> None:
        self.drop.bind("<Configure>", self._draw_dropzone)
        self.drop.bind("<Button-1>", lambda event: self.choose_file())
        self.drop.bind("<Enter>", self._on_drop_hover)
        self.drop.bind("<Leave>", self._on_drop_leave)
        if self.dnd_ready:
            try:
                self.drop.drop_target_register(DND_FILES)
                self.drop.dnd_bind("<<DropEnter>>", self._on_drop_hover)
                self.drop.dnd_bind("<<DropLeave>>", self._on_drop_leave)
                self.drop.dnd_bind("<<Drop>>", self._on_drop)
            except Exception:
                self.dnd_ready = False
                logger.exception("拖放功能初始化失败")
        self.root.bind("<Control-o>", lambda event: self.choose_file())
        self.root.bind("<Escape>", lambda event: self.cancel_translation())
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_drop(self, event) -> None:
        self.drop_hover = False
        try:
            items = list(self.root.tk.splitlist(event.data))   # 含空格/括号的路径靠它
        except Exception:
            items = [str(event.data)]
        self._accept_paths(items)
        self._draw_dropzone()
```

`_accept_paths` 里在入口就把关：非文件、多文件、扩展名不在白名单分别给出人话提示，
别让 worker 抛栈；`busy` 时拒绝并提示「正在翻译，请稍候」。

## 7. 线程 → 队列 → 界面

worker 侧只有 `emit_log` / `_queue_progress` / 终态 `events.put`，不碰控件。

```python
    def start_translation(self) -> None:
        if self.busy or not self.src_path:
            return
        if not os.path.isfile(self.src_path):
            self._show_failure("文件不存在，请重新选择。")
            return
        ocr_enabled = self.ocr_switch.get()
        self.busy = True
        self.output_path = None
        self.stop_event = threading.Event()          # 每次新建，并作为参数传进线程
        self.progress.stop()
        self.progress.configure(mode="indeterminate")
        self.progress.start(14)
        self._set_status("正在准备文档，首次需加载本地模型…", TEXT)
        self._draw_dropzone()
        self._refresh_buttons()
        self.worker_thread = threading.Thread(
            target=self._run_translation,
            args=(self.src_path, ocr_enabled, self.stop_event),
            daemon=True,
        )
        self.worker_thread.start()

    def _run_translation(self, src_path, ocr_enabled, stop_event) -> None:
        try:
            check_cancel(stop_event)
            output = translate_word(src_path, translator,
                                    progress=self._queue_progress, log=self.emit_log)
            self.events.put(("done", output))
        except CancelledError:
            self.events.put(("cancelled",))
        except TranslationError as exc:
            self.events.put(("error", str(exc)))
        except Exception as exc:                      # 兜底：界面必须收到反馈
            logger.exception("翻译过程出现异常")
            detail = "".join(traceback.format_exception_only(type(exc), exc)).strip()
            self.events.put(("error", f"程序出现意外问题：{detail}"))

    def _queue_progress(self, done, total, message: str) -> None:
        self.events.put(("progress", done, total, message))

    def emit_log(self, message: str) -> None:
        logger.info(message)
        self.events.put(("log", message))

    def _pump_events(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "log":
                    self._append_log(event[1], event[2] if len(event) > 2 else "info")
                elif kind == "progress":
                    self._on_progress(event[1], event[2], event[3])
                elif kind == "done":
                    self._on_done(event[1])
                elif kind == "error":
                    self._on_error(event[1])
                elif kind == "cancelled":
                    self._on_cancelled()
        except queue.Empty:
            pass
        try:
            if self.root.winfo_exists():
                self.root.after(80, self._pump_events)
        except tk.TclError:
            pass
```

取消、进度条切换与终态：

```python
    def cancel_translation(self) -> None:
        if not self.busy or self.stop_event is None:
            return
        self.stop_event.set()
        self.cancel_btn.configure(state="disabled")
        self._set_status("正在取消，请稍候…", MUTED)
        self._append_log("已请求取消，将在当前段落或页面结束后停止。", "muted")

    def _on_progress(self, done, total, message: str) -> None:
        if total:
            if str(self.progress.cget("mode")) != "determinate":
                self.progress.stop()
                self.progress.configure(mode="determinate")
            self.progress.configure(maximum=total, value=done)
            self.percent_label.configure(text=f"{int(done / total * 100)}%")
        if message:
            self._set_status(message, TEXT)

    def _on_done(self, output: str) -> None:
        self.output_path = output
        self.busy = False
        self.stop_event = None
        self.progress.stop()
        self.progress.configure(mode="determinate", maximum=100, value=100)
        self.percent_label.configure(text="100%")
        self._draw_dropzone()
        self._refresh_buttons()

    def _on_close(self) -> None:
        if self.busy:
            if not messagebox.askyesno("退出", "任务还在进行中，现在退出会丢失本次结果。确定退出吗？",
                                       parent=self.root):
                return
            if self.stop_event is not None:
                self.stop_event.set()
        try:
            self.root.destroy()
        except tk.TclError:
            pass
```

## 8. clam 扁平按钮样式

四个边框色必须一起设，`style.map()` 补 `disabled/pressed/active`，否则禁用态仍留渐变边。

```python
    def _setup_style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Accent.TButton", background=ACCENT, foreground="#ffffff",
            bordercolor=ACCENT, lightcolor=ACCENT, darkcolor=ACCENT, focuscolor=ACCENT,
            font=(FONT, 10, "bold"), padding=(self.px(18), self.px(9)), relief="flat",
        )
        style.map(
            "Accent.TButton",
            background=[("disabled", "#b7c5d6"), ("pressed", "#102c4a"), ("active", ACCENT_HOVER)],
            foreground=[("disabled", "#f4f7fb")],
            bordercolor=[("disabled", "#b7c5d6")],
            lightcolor=[("disabled", "#b7c5d6")],
            darkcolor=[("disabled", "#b7c5d6")],
        )
        style.configure("Tool.TCheckbutton", background=BG, foreground=TEXT)
        style.map("Tool.TCheckbutton", background=[("active", BG)],
                  foreground=[("disabled", "#9aa8ba")])
```

需要真正好看的勾选态时，沿用第 5 节的 Canvas 自绘，而不是继续调 `TCheckbutton`。

## 9. 启动器模板

GUI 启动（无黑框），带运行时与资源自检：

```bat
@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Runtime not found. Please keep the .venv folder next to this file.
    pause
    exit /b 1
)
if not exist "models\xxx\model.bin" (
    echo Offline model not found. Please keep the models folder next to this file.
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "%~dp0app.py" --offline
```

一次性安装/下载（要看得见输出，用 `python.exe` + `pause` + `errorlevel` 分支）：

```bat
@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo [X] 找不到 .venv\Scripts\python.exe，请先确认本工具已完整解压。
    pause
    exit /b 1
)
echo 正在检查依赖…
".venv\Scripts\python.exe" fetch_multilingual_model.py
if errorlevel 1 (
    echo.
    echo [X] 安装未完成，请检查网络后重新运行本脚本。
) else (
    echo.
    echo [OK] 已就绪。
)
pause
endlocal
```

## 10. 打包前自检命令

在**将要分发的那个 venv** 里跑，别用系统 Python：

```bash
".venv/Scripts/python.exe" -c "import tkinterdnd2, tkinter; r=tkinterdnd2.TkinterDnD.Tk(); print('dnd ok'); r.destroy()"
".venv/Scripts/python.exe" -c "import ctypes; print(ctypes.windll.user32.GetDpiForSystem())"
```

第一条抛异常 = 该 venv 的 Tcl/Tk 与 tkinterdnd2 不匹配，此时界面必须走第 6 节的点击降级路径，
并把降级提示写进交付说明，不要默默没有拖拽。venv 不可跨机搬迁路径：换目录后重建 venv 再
`pip install`，只分发源码 + bat + 依赖清单。
