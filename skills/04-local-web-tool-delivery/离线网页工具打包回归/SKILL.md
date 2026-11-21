---
name: win-offline-web-tool-regression-package
description: "回归并重新打包 Windows 离线网页工具，核对中文路径、实际导出与 ZIP 条目内容。复用当前可用的测试和运行环境，只清理由本次启动的进程，明确未验证的交互。"
---

# Windows 离线网页工具回归与打包

与 `offline-web-tool-fixture-regression`（夹具回归、Node 脚本）和 `electron-web-preview-qa`（Electron 截图质检）共用前提，本 Skill 负责 Windows 执行层：中文路径编码、Python zipfile 校验、端口与进程卫生、交付汇报口径。夹具/断言模板优先复用前者。

## 硬性前提

- 数据不出本机：只绑 `127.0.0.1`，夹具一律合成公司名 + 合成金额，真实底稿绝不进夹具目录。
- 夹具、报告、临时解包目录只写 `%TEMP%`，不得进被测项目目录，更不得进交付包。
- 先明确目标交付包与源目录，保留可恢复旧版；用户已授权重打该包时直接执行，目标不明或会覆盖无关成品时再确认。

## 流程

### 1. 建可测面（先探测，别假设）

普通脚本的顶层函数或 `var` 可能成为 `window` 属性；顶层 `let`/`const` 不会自动成为 `window` 属性，模块和闭包中的绑定也不可据此访问。先探测项目真实暴露的测试入口；`window.__reconDebug` 只是某次项目使用过的显式钩子，不是通用约定。
被模块/闭包封装时不要硬套本流程：改用 DOM + `DataTransfer` 造 `File` 驱动导入入口，或退回 `browser-use__upload_file` 真点选择器。
每个 evaluate 片段开头先 `typeof window.xxx === 'function'` 探测再调用。

### 2. 造夹具

用被测项目自带的 `vendor/xlsx.full.min.js` 在 Node 里生成，不要新装依赖。必须覆盖：合并单元格续行、仅表名含方向、表头上方标题行、带方向列、方向列留空、负数、GBK/CSV、合计行、纯文件名推断。
用 `browser-use__evaluate_script` 里的 `fetch` 取字节再 `new File([buf], name, {lastModified})` 喂给导入函数，全程不点文件选择器。

### 3. 起两个服务，端口先探测再用

```bash
python <skill-dir>/scripts/cors-server.py <fixturesDir> --port 0
# READY http://127.0.0.1:<port>/ 才是真端口
```

工具本体另起 `python -m http.server <port> --bind 127.0.0.1`（会话实测 4399）。**每个夹具 URL 先 GET 断言 200 再进第 4 步**：服务器根目录就是夹具目录，URL 只写文件名（多一层前缀必 404），中文文件名要 `encodeURI`。
不要假定任何固定端口可用；优先使用 `--port 0` 并读取实际监听地址。撞端口时**换端口，绝不结束别人的 PID**。
`file://` 页面跨源取夹具必须带 `Access-Control-Allow-Origin: *`，这是 CORS 服务器存在的唯一理由；个别浏览器会整体禁掉 `file://` 的网络请求，此时把夹具 base64 内联进脚本，或把页面也放到 HTTP 上跑同源。

### 4. evaluate_script 数值回归

链路：`fetch 夹具 → 造 File → 导入函数 → 计算/对账函数 → 读 state 断言 → buildExportWorkbook() → XLSX.utils.sheet_to_json(wb.Sheets['汇总页名']) 回读列头、行数、金额与说明行`。

- 断言只回传精简指标（笔数、分组净额、跳过原因分布、承上行数、公司名归属、导出的 sheet 名与列数），**不要 `JSON.stringify(state)` 全量返回**，会撑爆上下文。
- 期望值从夹具定义反推；改动前跑一遍留基线，改动后要求逐条对齐（会话即靠这条对齐发现「记录数与上一版一致」）。
- 拆成多次小脚本执行：一处语法写错整段报废且报错常被吞，重跑比调试便宜。
- 只校验合并单元格/文本金额时，用**带显式方向列**的简单夹具，别让方向推断和负数重分类两个逻辑互相掩盖。
- 劫持 `XLSX.writeFile` 能证明工作簿内容与文件名，**不能证明真实下载动作**；报告里写「未验证」，不要说「导出已实测」。

### 5. Electron 真窗口补视觉与交互

功能全绿不等于页面可用，最后一段交给 `electron-web-preview-qa`：桌面 1280×860 + 移动 390×844，读 `report.json` 核对实际视口、横向溢出、console 报错。
复制/剪贴板类按钮必须在真窗口里点：先 `win.focus(); win.webContents.focus()` 再 `executeJavaScript` 里 `element.click()`，并给 5s 超时（失焦时 clipboard 会挂起约 2 分钟）；以按钮文案变成「已复制」+ toast 作为成功证据。
优先使用被测项目已有的 Electron，或当前已验证可用的浏览器验收入口；不要依赖其他项目的固定 runtime 路径。需要新依赖时按既有授权和项目版本安装，并隔离本次 userData。

### 6. 重打包与往返校验

```bash
powershell -NoProfile -Command "Compress-Archive -Path '<srcDir>\*' -DestinationPath '<out>.zip' -Force"
python <skill-dir>/scripts/zipcheck.py "<out>.zip" "<srcDir>"
```

`zipcheck.py` 校验条目名、CRC，并直接读取归档成员与源文件逐项比较 MD5，不解压归档。支持单一顶层包装目录；stdout 打 ASCII 摘要（`RESULT PASS|FAIL`），中文详情写 UTF-8 报告。对 `.git`、`node_modules` 等默认排除项不做内容核对，这不等于整个源目录无差异。
`OK n MISSING n DIFF n EXTRA n` 里任何非零的 MISSING/DIFF/EXTRA 都算失败——文件在包里但内容旧，是最难被发现的一类。

- **禁用 Git Bash `unzip` 判定包体**：Info-ZIP 把 `Compress-Archive` 写的 UTF-8 条目名解码成乱码并警告 backslash 分隔符，那是读法问题，不是包坏了。
- PowerShell 5.1 读取含中文的脚本时注意 UTF-8 BOM；PowerShell 7 的默认编码不同。访问被拒还可能来自真实权限问题，先查具体路径和错误，不把所有异常都归因于编码。

### 7. 收尾与汇报

开工先记录已存在的 electron/python PID 清单，结束只停自己启动的 PID：

```bash
powershell -NoProfile -Command "Stop-Process -Id <pid>,<pid> -Force"
```

禁止 `taskkill /IM electron.exe`、按端口或窗口标题批量结束、误杀桌宠主进程；`taskkill /PID` 在 Git Bash 里还会被 MSYS 路径转换（`/PID` → `C:/.../git/PID`），一律走 `Stop-Process`。
最后确认端口释放（`netstat -ano | grep :<port>`）、`%TEMP%` 夹具目录不残留进交付包，并汇报：改了哪些文件、哪些场景实测通过、哪些只校验了逻辑未校验动作（真实下载、真实 Excel 打开）、zip 校验结果与字节数。

## 常见故障

| 现象 | 原因 | 处理 |
|---|---|---|
| `New-Item ... 访问被拒绝` / `UnauthorizedAccessException` | `.ps1` 无 BOM，中文路径被按 ANSI 读成乱码 | 改用 Python，或脚本内只用 `$env:TEMP` 等 ASCII 路径 |
| `unzip` 列表条目名乱码 + backslash 警告 | Info-ZIP 未读 UTF-8 标志位 | 用 `zipcheck.py`；别据此判定 zip 坏了 |
| `invalid time interval '/t'` | coreutils `timeout.exe` 抢了 `timeout /t` | 等待用 `ping -n N 127.0.0.1 >nul` |
| `.bat` 里 `start ""` 永久挂起 | MSYS 拉起的 `cmd //c` 下 start 不返回 | 改 `Start-Process -WindowStyle Hidden` |
| 404 但文件确实在夹具目录 | URL 多了一层前缀 / 中文未编码 | 根即夹具目录，只写文件名并用 `encodeURI` 或按段 `encodeURIComponent` |
| `Address already in use` / 拿到别人的页面 | 端口被其它项目占用 | 换端口，绝不结束陌生 PID |
| Electron 启动即 exit 127 | 从 bash 传自定义 `--url` 等开关 | 默认值写进脚本，只传 `--out`；加 `ELECTRON_ENABLE_LOGGING=1` 并重定向 stdout 到文件 |
| 终端中文乱码看不到结论 | Windows 代码页 | 以 UTF-8 报告文件 / `report.json` 为准，用 Read 读 |

完整环境坑与实测记录见 [references/pitfalls.md](references/pitfalls.md)。

## Resources

- [scripts/cors-server.py](scripts/cors-server.py) — 只绑 127.0.0.1、带 CORS 头的一次性夹具服务器，自动选空闲端口并自超时退出。
- [scripts/zipcheck.py](scripts/zipcheck.py) — zip 条目名 + CRC + 归档成员逐文件 MD5 校验，ASCII 摘要走 stdout、中文详情走 UTF-8 报告。
- [references/pitfalls.md](references/pitfalls.md) — Git Bash / PowerShell / 端口 / Electron 的本机坑速查与判读规则。
