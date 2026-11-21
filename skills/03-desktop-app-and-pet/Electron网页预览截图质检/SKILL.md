---
name: electron-web-preview-qa
description: "当内嵌浏览器预览或截图工具不可用（如 viewport 0×0、截图空白/过期、无法交互）时，用本机已有 Electron 搭建一次性网页质检环境：隔离 userData、可见前台窗口、capturePage 截图、executeJavaScript 采集布局指标与触发弹窗，并按 390×844 复验移动端。适用于本地静态页/网页的截图验收、横向溢出与遮挡排查、部署前 UI 回归，以及必须按精确命令行结束 QA 进程而非结束所有 electron.exe 的场景。"
---

# Electron 网页预览质检

## 用途

当内嵌浏览器或预览工具的截图不可用时，在 Windows 上用本机已有 Electron 启动一个独立的 QA 窗口，完成桌面/移动端截图、布局指标采集、弹窗点击与安全清理。

## 何时使用

- 内嵌浏览器截图报 `NATIVE_BROWSER_VIEWPORT_UNAVAILABLE`（viewport 0×0、visible=false），或得到空白/过期截图。
- 需要给本地网页、静态站点或站点草稿做视觉验收、横向溢出/遮挡排查、弹窗与移动端回归。
- 需要在不影响用户正在运行的桌宠或其他 Electron 应用的前提下完成检查。

不要用：浏览器自动化工具正常工作时；真机测试；替代发布流程。

## 前置检查

1. 先调用可用的内嵌浏览器/截图工具，并保留失败信息。只有它不可用时才回退。
2. 找可运行任意脚本的 Electron 发行版，例如 npm 安装的 `<project>/node_modules/electron/dist/electron.exe`。打包后的应用 exe 不能当 runtime 用。没有就询问用户，不要自行下载。
3. 运行 `electron.exe --version` 记录版本。本流程已在 Electron 44.9.3 验证。
4. 启动本地服务器（如需要），确认返回 200；记录服务器任务/进程，稍后只停用它。

## 不可省略的规则

- **隔离 profile**：在 `app.whenReady()` 之前执行
  `app.setPath('userData', path.join(outDir, 'userdata'))`。
  不要复用桌宠的 `%APPDATA%\desktop-pet`，否则会触发单实例锁、缓存“拒绝访问”并污染用户数据。
- **窗口必须真实可见**：`show: true`、`useContentSize: true`、`offscreen: false`，位置在主屏工作区内。
  隐藏、最小化、移出屏幕会导致 `capturePage()` 返回陈旧画面或抛 `UnknownVizError`。
- **截图前等待稳定**：`loadURL` 完成后等待 `document.fonts.ready`、图片完成、两帧 rAF，再加 settle 延时；不要只等固定时间。
- **截当前视口**：`capturePage()` 只截可见视口。需要页尾/区块时先滚动再截，不要声称已截全页。
- **以实际视口为准**：记录 `innerWidth/innerHeight/clientWidth/clientHeight/DPR` 与截图像素尺寸。
  请求的窗口尺寸可能被屏幕工作区裁切；滚动条会使 clientWidth 小于窗口宽度（390 窗口常见 376）。
- **横向溢出要有双重证据**：先看 `documentElement.scrollWidth > clientWidth`，再看越界元素。
  装饰性绝对定位元素越界但 `scrollWidth` 正常，不是布局溢出；可用 `--ignore-selector` 排除。
- **点击用页面内 JS**：`executeJavaScript` 中 `element.scrollIntoView(...); element.click()`。
  点击前 `win.focus(); win.webContents.focus();`。
- **复制类按钮要小心**：窗口失焦时点击“复制”会让 clipboard 挂起约 2 分钟。先聚焦；不需要验证剪贴板就跳过；必须验证时给点击加超时。
- **只结束自己的进程**：按命令行唯一脚本路径或 qa.pid 定位 PID，禁止 `taskkill /IM electron.exe`。
- **中文输出读文件**：Windows 控制台可能乱码，以 `<out>/report.json` 为准，不要依据终端里的中文判断。

## 运行脚本

脚本：`<skill-dir>/scripts/electron-qa.cjs`

```bash
"<path-to-electron.exe>" \
  "<skill-dir>/scripts/electron-qa.cjs" \
  --url "http://127.0.0.1:4371/" \
  --out ".qa/run-1" \
  --width 1280 --height 900 --settle 800 \
  --check title=#main-title \
  --shot work=#work --shot about=#about \
  --click details=[data-open="dialog-details"] \
  --mobile --mobile-width 390 --mobile-height 844 \
  --mobile-shot work=#work \
  --mobile-click details=[data-open="dialog-details"] \
  --ignore-selector ".decorative-ring" \
  --timeout 60000
```

参数：
- `--url`：http(s)、file 路径或 data URL。
- `--out`：输出目录；脚本会自动建目录，并写入 `qa.pid`、`qa-meta.json`、`report.json` 和截图。
- `--width/--height`：桌面内容尺寸，默认 1280×900。
- `--settle`：稳定后的额外等待毫秒，默认 800。
- `--shot name=selector`：滚动到区块并截图 `section-<name>.png`；可重复。`--scroll-offset` 默认 24，给吸顶导航留空间。
- `--click name=selector`：点击并截图 `click-<name>.png`；可重复。只在非复制按钮上使用。
- `--check name=selector`：在指标里记录元素数量、矩形、可见性、文本；可重复。
- `--ignore-selector`：溢出检测时忽略的选择器；可重复。
- `--mobile`：桌面流程后改成 390×844 并重新加载，再截图/采集。
- `--mobile-only`：跳过桌面流程，直接按移动尺寸打开；移动端卡住时用它单独重跑。
- `--mobile-shot`、`--mobile-click`：移动端专用，格式同上。
- `--timeout`：硬超时毫秒，默认 60000；超时会 `QA_TIMEOUT` 并退出。

输出文件：

```
<out>/qa.pid
<out>/qa-meta.json
<out>/report.json
<out>/desktop-top.png
<out>/section-<name>.png
<out>/click-<name>.png
<out>/mobile-top.png
<out>/mobile-section-<name>.png
<out>/mobile-click-<name>.png
<out>/userdata/
```

脚本会打印 ASCII 标记：`QA_PID`、`QA_STEP`、`QA_RESULT <report.json>`、`QA_SUMMARY {...}`，失败时 `QA_FAILED` 或 `QA_TIMEOUT`。**用 Read 读 report.json 和截图**；不要依赖终端里可能乱码的中文。

## 标准流程

1. 记录内嵌浏览器失败信息；确认需要回退。
2. 找 Electron、查版本；用主屏工作区决定桌面尺寸。请求尺寸超过工作区就调小，或接受实际值并写进报告。
3. 启动本地服务器并确认 200；如果页面用 `fetch`/ES module，优先 HTTP，不要用 `file://`。
4. 桌面阶段：首屏截图 → 指标 → 滚动区块截图 → 点击弹窗截图 → 看 console error。
5. 移动阶段：加 `--mobile` 或单独 `--mobile-only`；390×844 下重新加载并重复关键检查。移动端卡住时只重跑移动端，不动桌宠。
6. 审阅：用 Read 看截图，用 report.json 核对实际视口、溢出、破图、console error。横向溢出结论必须有“根因元素 + 截图”。
7. 清理：正常退出后确认无残留 QA 进程；异常时按 qa.pid/命令行精确结束。记录开始时已有的 Electron PID，结束后确认它们仍在。
8. 汇报：截图路径、实际视口、发现的问题、未验证项。不要把截图上传到第三方。

## 进程清理（Windows）

开始前记录已有 Electron 进程，避免误杀：

```powershell
Get-CimInstance Win32_Process -Filter "Name='electron.exe'" |
  Select-Object ProcessId, CommandLine | Format-List
```

正常结束后脚本会自己退出。若卡住，先读 `<out>/qa.pid`，再核对命令行：

```powershell
$qaPid = [int](Get-Content "<out>\qa.pid")
Get-CimInstance Win32_Process -Filter "ProcessId=$qaPid" |
  Select-Object ProcessId, CommandLine | Format-List
```

只有确认 `CommandLine` 包含 `electron-qa.cjs` 且包含本次 `<out>` 路径时，才结束该 PID：

```powershell
taskkill.exe /PID $qaPid /T /F
```

禁止：

- `taskkill /IM electron.exe`
- 按端口、窗口标题或模糊名称批量结束
- 结束桌宠主进程（通常是 `electron.exe .`，命令行含 `desktop-pet`）

若没有 qa.pid，按唯一脚本路径过滤，但仍只结束核对后的 PID：

```powershell
Get-CimInstance Win32_Process -Filter "Name='electron.exe'" |
  Where-Object { $_.CommandLine -like '*electron-qa.cjs*' -and $_.CommandLine -like '*<out>*' } |
  Select-Object ProcessId, CommandLine | Format-List
```

服务器也要只停自己启动的 task/PID，不要按端口杀进程。

## 常见故障

| 现象 | 原因 | 处理 |
|---|---|---|
| `NATIVE_BROWSER_VIEWPORT_UNAVAILABLE ... viewport=0x0` | 内嵌浏览器没有可见 surface | 回退到 Electron；保留错误作为回退依据 |
| `QA_FAILED [Error: UnknownVizError]` | 窗口隐藏、最小化或移出屏幕 | `show:true`、放回工作区、`offscreen:false`、恢复最小化 |
| 连续截图一样/陈旧 | 窗口不可见或未重绘 | 保持可见；比较 report 里的 hash、尺寸和 mtime |
| 点到复制后卡约 2 分钟 | 窗口失焦时 clipboard 挂起 | 先聚焦；跳过复制；给点击 5s 超时并中止后续 |
| `overflowing: ["decorative-ring"]` 但 `scrollWidth == vw` | 装饰元素被裁切/浮在视口外 | 只按根滚动溢出判定；用 `--ignore-selector` |
| 请求 1280×1000，实际 vw 1233、高 758 | 屏幕工作区裁切 + 滚动条 | 以实际指标为准；缩小请求尺寸 |
| 390 窗口的 clientWidth 是 376 | 桌面滚动条占宽 | 报告真实值；确需 390 CSS px 时注入隐藏滚动条 CSS 并注明 |
| `Unable to move the cache: 拒绝访问` | 复用了桌宠 userData | 隔离 userData 到 `<out>/userdata` |
| 终端中文乱码 | Windows 代码页 | 读 report.json，不看终端 JSON |
| `'console-message' arguments are deprecated` | Electron 44 新事件签名 | 用事件对象的 `level/message` |
| console 里 `Electron Security Warning` | Electron 自带 CSP 警告 | 过滤掉，别当页面错误 |
| 弹窗点击无效 | 选择器错/被遮挡/需要真实指针 | 先验证 `querySelector`；必要时用项目专用探针或 `sendInputEvent` |
| 看得到首屏，看不到页尾 | `capturePage` 只截视口 | 用 `--shot` 滚动后截图 |
| 字体不对 | 字体未加载或回退 | 等 `document.fonts.ready`，检查 `fonts`/`bodyFont` |
| `file://` 页面 fetch 失败 | CORS/模块限制 | 启本地 HTTP 服务器 |

## 已验证基线

Windows + Electron 44.9.3 上实测：

- 桌面请求 1280×1000 被屏幕裁到约 1248×758，实际 `clientWidth` 1233。
- 390×844 移动窗口实际 `clientWidth` 376（滚动条），截图按 DPR 2 输出 782×1690。
- 内嵌浏览器报 viewport 0×0 后，Electron `capturePage` + `executeJavaScript` 能完成桌面和移动端截图；桌宠进程必须保持运行。
