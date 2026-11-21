---
name: electron-desktop-pet-mvp
description: "Build and verify a minimal runnable Electron desktop pet or transparent always-on-top desktop widget on Windows: bootstrap a portable Node when npm is missing, create a transparent click-through window with region hit-testing, implement main-process dragging with persisted position, add SVG idle animation, and verify automatically with capturePage alpha checks and sendInputEvent. Use when creating a desktop pet MVP, adding transparent or click-through desktop widgets, debugging Electron transparency/mouse pass-through, or installing Electron when npm is unavailable. 中文触发：从零做桌宠、桌面宠物最小版、透明置顶窗口、鼠标穿透、Electron 桌宠、便携 Node 安装 Electron。"
---

# Electron Desktop Pet MVP

## 目标

在 Windows 上从空目录做出可运行的桌宠最小版：透明置顶窗口、宠物区域拦截鼠标而其余区域穿透、拖拽并记住位置、SVG 待机动画，以及能真实跑通的截图/点击自检。

本 Skill 只负责技术骨架。角色外形、名字、性格和台词先用占位内容，需要完整角色设计时使用 `desktop-pet-character-design`。

## 何时使用

- 用户要从零做 Windows 桌宠或桌面宠物最小版。
- 要做透明、置顶、指定区域可点击、其余区域穿透的 Electron 桌面小组件。
- 机器上没有 Node/npm，仍要安装和运行 Electron。
- 需要自动验证透明窗口是否真的透明、点击是否真的生效。

不适用：打包安装包、代码签名、自动更新、AI 对话、最终角色美术、macOS/Linux 专项适配。

## 验收标准

- 窗口无边框、背景透明、始终置顶、不占任务栏。
- 鼠标在宠物命中区被拦截，在窗口透明区域可直接操作桌面。
- 左键有可见反馈，拖拽可移动，重启后恢复上次位置。
- 自检输出 `SMOKE_PASS`、退出码 0，四角 alpha 接近 0，宠物区域存在不透明像素，合成点击后状态断言为真。
- 真实拖拽手感、系统级穿透、置顶层级和多显示器行为必须由人确认，不能只凭截图宣称通过。

## 环境与依赖

先检查 `node`/`npm` 和项目内 `node_modules/electron/dist/electron.exe`。不要因为 Qoder 自带 Electron 就直接拿来运行项目，版本和 ABI 可能不同。

缺失依赖时优先使用同目录的 `electron-windows-bootstrap` Skill，它提供：

- `../electron-windows-bootstrap/scripts/bootstrap-node.ps1`：下载、校验、解压便携 Node 到项目 `.dev/node`。
- `../electron-windows-bootstrap/scripts/ensure-electron.cjs`：检查并在缺失时运行 `install.js` 补齐 Electron 二进制。

本 Skill 的 `scripts/bootstrap-windows.ps1` 是面向桌宠项目的薄封装，默认调用上述脚本；没有该 Skill 时按 `references/electron-pet-mvp.md` 的 fallback 命令处理。

硬性要求：

- 不修改系统 PATH，不装全局包；所有命令显式使用 `.dev/node/node.exe` 和项目内 Electron。
- Electron 44 的 npm 包不会再自动下载 `dist`；`npm install` 成功后仍必须运行 `node_modules/electron/install.js`。
- 下载便携 Node 前必须取得用户确认，使用固定版本并校验 SHA256；脚本仅在带 `-AcceptDownload` 时联网。

## 搭建流程

### 1. 检查并引导环境

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/bootstrap-windows.ps1 -ProjectDir . -CheckOnly
```

只读检查应输出 `PET_ENV_OK`。缺少 Node 或 Electron 时，向用户说明将下载的版本和来源，得到同意后再去掉 `-CheckOnly` 并加 `-AcceptDownload`。

### 2. 建最小骨架

以 `references/electron-pet-mvp.md` 的代码为基线创建 `main.js`、`preload.js`、`src/index.html`、`src/renderer.js`、`src/style.css`。不要覆盖已有应用；目标目录非空时先确认。

安全默认值：`contextIsolation: true`、`nodeIntegration: false`、只加载本地文件、页面带 CSP、IPC 只暴露明确的白名单方法。

### 3. 透明置顶窗口

窗口参数至少包含：

```js
{
  width: 280, height: 320,
  transparent: true, frame: false,
  alwaysOnTop: true, skipTaskbar: true,
  hasShadow: false, show: false,
  backgroundColor: '#00000000'
}
```

加载完成后用 `showInactive()` 显示，避免抢焦点。单实例锁避免重复启动；自检模式要跳过单实例锁并使用临时 `userData`，防止与正在运行的桌宠互相退出或覆盖位置。

### 4. 命中区与鼠标穿透

启动时先：

```js
win.setIgnoreMouseEvents(true, { forward: true });
```

渲染层在 `mousemove` 时判断指针是否落在宠物命中区，通过 preload IPC 通知主进程切换：

```js
win.setIgnoreMouseEvents(shouldIgnore, { forward: true });
```

MVP 推荐 `#pet { pointer-events: none; }` 配合 `#pet svg * { pointer-events: visiblePainted; }`，让透明像素不拦截桌面。若改用整个元素盒作为命中区，必须在交付时说明透明角落也会挡住鼠标。

拖拽期间主进程必须忽略 `set-ignore`，保持窗口可交互；拖拽结束后再按命中区恢复。

### 5. 拖拽与位置记忆

- `pointerdown` 记录按下点；移动超过约 4px 才开始拖拽，避免点击被误判为拖拽。
- 拖拽由主进程以约 16ms 轮询 `screen.getCursorScreenPoint()` 并 `setPosition()`，不要依赖渲染层持续收到 mousemove。
- 位置写入 `app.getPath('userData')/pet-state.json`；读取时校验数字、检查与所有显示器工作区的交集，启动和拖动时按工作区钳制。
- 如果使用 `setPointerCapture`，必须 `try/catch`；合成点击或没有活动指针时会抛错。

### 6. 待机动画与反馈

用 SVG + CSS `transform`/`opacity` 实现呼吸、眨眼、摇尾；不要用逐帧大图。点击反馈用独立的 class 触发一次性动画，动画结束后移除该 class，让呼吸动画恢复。窗口内所有装饰元素设 `pointer-events: none`，避免意外拦截。

### 7. 自动冒烟验证

把 `scripts/smoke-test.cjs` 复制到应用的 `scripts/` 下，在 `app.whenReady()` 创建窗口后接入：

```js
if (process.env.PET_SMOKE === '1') {
  require('./scripts/smoke-test.cjs').installSmokeTest({
    app,
    getWindow: () => win,
    options: {
      outputDir: path.join(__dirname, '.dev'),
      cleanupUserData: true
    }
  });
}
```

用 PowerShell 等待 GUI 进程结束，避免 Git Bash 提前返回：

```powershell
New-Item -ItemType Directory -Force .dev | Out-Null
$env:PET_SMOKE = '1'
$p = Start-Process -FilePath ".\node_modules\electron\dist\electron.exe" -ArgumentList "." `
  -PassThru -Wait -RedirectStandardOutput ".dev\smoke.out" -RedirectStandardError ".dev\smoke.err"
$p.ExitCode
Get-Content .dev\smoke-report.json
```

通过条件：退出码 0；报告 `ok: true`；四角 alpha 不超过 16；宠物选择器框内 alpha>16 的像素比例不低于 5%；点击后 DOM 断言为真；`errors.console`、`errors.renderGone`、`errors.failedLoad` 均为空。

`capturePage()` 返回物理像素，而 `sendInputEvent()` 使用逻辑 DIP。高 DPI 下必须按 `win.getContentSize()` 归一化截图后再采样，否则点击坐标会偏移。脚本已处理这一点，改写时不要退回到直接用截图尺寸。

预览 PNG 在图片查看器里可能显示白底，这是查看器的合成结果；透明与否只看 alpha 数值。

### 8. 人工验收与汇报

让用户实际确认：拖拽手感、透明区域能否点到桌面、置顶层级、关闭后重启位置是否恢复、多显示器是否跑到屏幕外。

汇报时分开列出“自动已验证”和“仍需人工确认”，附主进程、渲染层、启动器、自检报告和预览图路径。没有亲手确认的项目不要写“已通过”。

## 硬性规则

- 不覆盖已有项目或同名 Skill；先检查目标目录。
- 不修改系统 PATH，不使用全局 npm 包，不用 Qoder 宿主 Electron 替代项目依赖。
- 不为了绕过下载失败关闭校验和；失败就报告并换镜像重试。
- 不在渲染层启用 Node 集成；不加载远程页面。
- 不在冒烟失败时退化成“截图看起来正常”；以 alpha、断言、退出码和报告为准。
- 不自动删除非临时 `userData`；清理逻辑只允许处理名称含 `smoke` 的临时目录。

## 常见坑

| 现象 | 原因与处理 |
| --- | --- |
| `npm` 不是内部或外部命令 | Node/npm 不在 PATH；用便携 Node 的显式路径，不改 PATH。 |
| `npm install` 成功但 Electron 起不来 | Electron 44 未下载 `dist`；运行 `install.js` 或 `ensure-electron.cjs`。 |
| 自检刚启动就退出 | 已有实例持有单实例锁；自检模式跳过锁并使用临时 `userData`。 |
| 截图预览是白底 | 查看器合成背景；读取 `toBitmap()` 的 alpha 判断透明。 |
| 点击自检无效 | 高 DPI 坐标错位，或点击落在透明像素；按内容尺寸归一化并用不透明像素定位。 |
| `setPointerCapture` 报错 | 合成事件/无活动指针；调用处 `try/catch`。 |
| 拖拽时鼠标穿透或卡住 | 拖拽期间被 `set-ignore` 覆盖；主进程在拖拽中拒绝切换并保持可交互。 |
| 点击一次后不再呼吸 | 一次性动画 class 覆盖了常驻动画；动画结束移除 class。 |

## 资源

- `scripts/smoke-test.cjs`：桌宠专用自检模块，负责 alpha 采样、DPI 归一化、不透明像素点击、DOM 断言、错误收集与报告。
- `scripts/bootstrap-windows.ps1`：复用 `electron-windows-bootstrap` 的 Node/Electron 引导，并提供只读检查。
- `references/electron-pet-mvp.md`：完整最小代码骨架、主进程/渲染层接线、fallback 安装命令和验收清单。

相关 Skill：`electron-windows-bootstrap`（环境安装与通用自检）、`desktop-pet-character-design`（角色外形与动作设计）。
