---
name: electron-windows-bootstrap
description: "诊断 Windows Electron 项目的 Node/npm、二进制下载与窗口启动问题。优先复用项目兼容的版本和运行时，只有缺失时才准备便携环境；不负责生产安装包与签名。"
---

# Electron Windows Bootstrap

## Overview

在 Windows 上不依赖系统 Node/npm、不修改 PATH、不需要管理员权限，从零安装并启动 Electron 项目，再用环境变量开关执行截图与模拟点击自检。

历史实测基线（不代表当前推荐版本）：Windows + 便携 Node 24 + Electron 44.9.3（其 `engines.node` 要求 `>=22.12.0`）。其他版本按同样流程，以项目 `package.json` 为准。

## 何时使用

- `node`/`npm` 不在 PATH，`npm install` 报“不是内部或外部命令”。
- `npm install electron` 成功，但 `node_modules/electron/dist/electron.exe` 不存在。
- Qoder 等宿主只提供 Electron 运行时，没有独立 npm。
- 需要无人值守确认窗口渲染、点击交互、透明背景。
- 需要给朋友一个不依赖系统 Node 的开发版启动器。

不要用于：打包安装包、代码签名、macOS/Linux、生产分发。打包使用 electron-builder 或 Electron Forge。

## 硬性规则

- 使用项目自己的 `node_modules/electron/dist/electron.exe`。Qoder 自带 Electron 只是宿主运行时，版本和 ABI 可能不同，不能替代项目依赖。
- 优先复用兼容的现有运行时；需隔离便携环境时放项目 `.dev/`。PATH 与安装范围按用户要求和现有约定处理。
- 先核对实际 Electron 包的安装方式；仅在二进制缺失且该版本需要时执行相应安装器，不对已有可用依赖重复安装。
- 不能为了绕过下载失败而关闭 checksum。失败就报告并换镜像重试。
- `.dev/` 只用于开发，分发和打包时排除。

## 流程

### 1. 诊断

```bash
pwd
where.exe node 2>/dev/null || echo "node: missing"
where.exe npm 2>/dev/null || echo "npm: missing"
test -f package.json && cat package.json
test -f node_modules/electron/dist/electron.exe && echo "electron: present" || echo "electron: missing"
```

读取 `node_modules/electron/package.json` 的 `version` 与 `engines.node`。项目没有 `package.json` 时创建最小版本，`main` 指向真实入口：

```json
{
  "name": "my-electron-app",
  "version": "0.1.0",
  "private": true,
  "main": "main.js",
  "scripts": { "start": "electron ." },
  "devDependencies": { "electron": "44.9.3" }
}
```

固定精确版本便于复现；升级前先确认新版本是否仍需要手动执行 `install.js`。

### 2. 便携 Node

先检查系统或项目 Node 是否满足本项目依赖的 engines；满足时直接复用。需要便携环境才用自带脚本，按目标版本与可信下载源设置参数。以下为隔离环境示例，不是所有项目的固定版本要求。Git Bash：

```bash
SKILL_DIR="<当前SKILL.md所在目录>"
powershell.exe -NoProfile -ExecutionPolicy Bypass \
  -File "$(cygpath -w "$SKILL_DIR/scripts/bootstrap-node.ps1")" \
  -Dest ".dev/node"
```

PowerShell 等价：

```powershell
& "<当前SKILL.md所在目录>\scripts\bootstrap-node.ps1" -Dest ".dev\node"
```

脚本从 npmmirror 解析最新 Node 24 win-x64，下载并校验 `SHASUMS256.txt`，解压后运行 `node -v` 和 npm 自检，输出 `NODE_OK version=... npm=... dest=...`。

可用参数：`-Version 24`、`-Version v24.18.0`、`-Force`、`-Mirror <url>`。SHA256 校验始终开启。

确认：

```bash
.dev/node/node.exe -v
.dev/node/node.exe .dev/node/node_modules/npm/bin/npm-cli.js -v
```

不要把 `.dev/node` 加进 PATH，后续都显式调用。

### 3. 安装依赖

用便携 Node 的 `npm-cli.js`，避开 `.cmd` 和 PATH 问题：

```bash
NODE=".dev/node/node.exe"
NPM=".dev/node/node_modules/npm/bin/npm-cli.js"
"$NODE" "$NPM" install --registry=https://registry.npmmirror.com --no-audit --no-fund
```

成功标准是 `node_modules/electron/package.json` 存在且版本正确，不是命令退出码为 0。公司网络限制镜像时换回 `https://registry.npmjs.org` 重试，不要混用两个 registry 生成的 lockfile。

### 4. 补齐 Electron 二进制

如果实际包没有可用的 dist 二进制，先按所安装版本的说明检查安装状态，再跑校验脚本：

```bash
NODE=".dev/node/node.exe"
SKILL_DIR="<当前SKILL.md所在目录>"
# 官方源慢或失败时，取消下一行注释，或给脚本传 --mirror=<url>
# export ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/
"$NODE" "$(cygpath -w "$SKILL_DIR/scripts/ensure-electron.cjs")" .
```

PowerShell：

```powershell
# $env:ELECTRON_MIRROR = "https://npmmirror.com/mirrors/electron/"   # 可选
& .dev\node\node.exe "$env:USERPROFILE\.qoder-cn\skills\electron-windows-bootstrap\scripts\ensure-electron.cjs" .
```

脚本依次检查 `dist/version`、`path.txt`、`dist/electron.exe`；缺失时用当前 Node 运行 `node_modules/electron/install.js`，安装后复检。成功输出 `ELECTRON_OK version=... exe=...`，失败输出 `ELECTRON_FAIL reason=...` 并以非 0 退出。

手动等价命令（仅在需要时）：

```bash
"$NODE" node_modules/electron/install.js
```

`install.js` 自带 checksums 校验，不要设置 `electron_use_remote_checksums` 之类的开关跳过。

### 5. 启动器

把 `assets/launcher.cmd` 复制到项目根目录并按需改名（如 `启动应用.cmd`）。它检查 `dist/electron.exe`，`cd /d "%~dp0"` 后直接启动，不依赖系统 Node/npm。

```bash
cp "$SKILL_DIR/assets/launcher.cmd" "./启动应用.cmd"
```

保留模板里的存在性检查和 `cd /d`；缺一不可，否则从桌面或资源管理器双击时工作目录不对。

### 6. 截图与点击自检

按 `references/smoke-test.md` 在主进程加入环境变量开关。最小验证：

```bash
rm -f .dev/smoke-result.json
SMOKE_TEST=1 "./node_modules/electron/dist/electron.exe" . > .dev/smoke.log 2>&1
echo "exit=$?"
cat .dev/smoke-result.json
```

Windows GUI 进程从 shell 立即返回时，改用 PowerShell 等待：

```powershell
$env:SMOKE_TEST = "1"
$p = Start-Process -FilePath ".\node_modules\electron\dist\electron.exe" -ArgumentList "." `
  -PassThru -Wait -RedirectStandardOutput ".dev\smoke.out" -RedirectStandardError ".dev\smoke.err"
$p.ExitCode
```

通过条件：退出码 0；结果文件 `ok: true`；`smoke-before.png` 与 `smoke-after.png` 存在；透明窗口的 alpha 透明像素比例大于 0；点击后的状态字段符合预期；日志出现 `SMOKE_OK`，没有 `SMOKE_FAIL`。

只能自动验证渲染和程序化点击。以下必须让真人确认：真实拖拽、鼠标穿透、置顶层级、托盘、多屏、开机自启。

### 7. 汇报

给出 Node/npm 路径与版本、Electron 版本、启动器路径、自检产物路径、失败原因（如有）。明确列出未自动验证的交互，不要把“截图通过”说成“功能全部通过”。

## 常见坑

- `npm install` 成功不等于 Electron 可运行，必须检查 `dist/electron.exe`。
- Electron 44.9.3 没有 postinstall；补齐二进制前 `npm start` 只会报找不到 Electron。
- 当前目录不对会导致应用入口找不到；启动器要 `cd /d "%~dp0"`。
- 单实例锁会让自检进程直接退出。自检时先关闭正在运行的实例，或在 `SMOKE_TEST` 下跳过 `requestSingleInstanceLock` 并使用临时 `userData`。
- 透明窗口截图在图片查看器里常显示白底，这是预览背景；用 alpha 像素判断透明度，不要用肉眼。
- GUI 进程的控制台输出在 Windows 上可能不落盘；以结果 JSON 和退出码为准。
- `.dev/node` 解压后体积很大且包含开发工具；不要提交、不要打包进发行物。
- 使用第三方镜像时保留 checksum 校验并固定版本；正式分发前用官方源复装一次。

## 资源

- `scripts/bootstrap-node.ps1`：下载、校验、解压便携 Node 24。
- `scripts/ensure-electron.cjs`：检查并补齐 Electron 二进制。
- `references/smoke-test.md`：环境变量开关、截图、模拟点击、alpha 与结果文件模板。
- `assets/launcher.cmd`：开发版启动器模板。
