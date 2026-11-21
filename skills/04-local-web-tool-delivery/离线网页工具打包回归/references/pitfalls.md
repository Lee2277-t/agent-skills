# 本机环境坑与判读规则

在 Windows + Qoder 自带 Git Bash（MSYS）+ PowerShell 5.1 这套组合上实测，适用于中文目录名的离线网页工具。

## 编码类

| 表现 | 真相 | 判读规则 |
|---|---|---|
| Git Bash `unzip -l` 条目名乱码 + `warning: ... appears to use backslashes as path separators` | `Compress-Archive` 写了 UTF-8 标志位，Info-ZIP 按 cp437 解 | 包可能是好的。改判 `python -c "import zipfile;print(zipfile.ZipFile(p).namelist())"` 或 `scripts/zipcheck.py` |
| PowerShell 跑 `.ps1` 报 `UnauthorizedAccessException` / `访问被拒绝`，出错行是 `New-Item -Path $tmp` | Write 工具存的 `.ps1` 是 UTF-8 无 BOM，PowerShell 5.1 按 ANSI 读，脚本里的中文路径变乱码 | 别给 `.ps1` 加中文路径。改用 Python（源码默认 UTF-8，中文路径正常），或脚本内只用 `$env:TEMP`、`[IO.Path]::GetTempPath()` |
| 终端里中文全乱码，看不出结论 | Windows 代码页 | 结论以 UTF-8 报告文件 / `report.json` 为准，用 Read 读；脚本 stdout 只打 ASCII 摘要 |
| `.bat` 里中文提示显示乱码 | UTF-8 无 BOM 且没切代码页 | `.bat` 存 UTF-8 无 BOM，首行后立刻 `chcp 65001 >nul`，行尾 CRLF |

## 参数被 MSYS 吃掉类

| 命令 | 后果 | 替代 |
|---|---|---|
| `taskkill /PID 123 /F` | `/PID` 被当路径转换，报 `无效参数 - C:/.../git/PID` | `powershell -NoProfile -Command "Stop-Process -Id 123,456 -Force"`，或写 `//PID` |
| `timeout /t 3` | coreutils 的 `timeout.exe` 抢先，报 `invalid time interval '/t'` | `ping -n 3 127.0.0.1 >nul` |
| `cmd //c "start "" x.exe"` | start 永久挂起且不启动进程（后续语句不执行） | `powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '...' -ArgumentList '...' -WorkingDirectory '...' -WindowStyle Hidden"` |
| `... > NUL` | MSYS 路径转换破坏重定向目标，报「系统找不到指定的路径」 | 重定向到绝对路径的真实文件 |
| `powershell -Command "... | ForEach-Object { $_.X }"` | `$_` 被 bash 展开吃掉 | 用 `Select-Object ... | Format-List`，或写成脚本文件 |

## 端口与进程

- 固定端口早晚会撞别的项目。本机已知占用：`127.0.0.1:8765` = 「净印·批量去水印」工作台。撞端口只换端口，**绝不结束陌生 PID**。
- 真端口只认服务器打印的 `READY http://127.0.0.1:<port>/` 行，不要假设传进去的就是监听端口。
- 开工先记录清单：`Get-CimInstance Win32_Process -Filter "Name='electron.exe'" | Select-Object ProcessId, CommandLine | Format-List`（python 同理换 `Name='python.exe'`）。收尾只 `Stop-Process` 自己启动的那几个 PID，并确认开始时已存在的 PID 还在。
- 禁止 `taskkill /IM electron.exe`、按端口/窗口标题批量结束。桌宠主进程通常是命令行含 `desktop-pet` 的 `electron.exe .`，属于用户正在用的东西。

## Electron 视觉段

- 内嵌浏览器报 `NATIVE_BROWSER_VIEWPORT_UNAVAILABLE ... viewport=0x0` 时，回退本机 Electron；保留报错作为回退依据。
- 从 bash 起 Electron 跑脚本，传自定义 `--url` 之类开关会让进程静默 exit 127。默认值写进脚本、命令行只传 `--out`；加 `ELECTRON_ENABLE_LOGGING=1` 并把 stdout 重定向到文件才看得到 `QA_*` 标记。
- 打包后的应用 exe 不能当 runtime；只有带 `resources/default_app.asar` 的 `node_modules/electron/dist/electron.exe` 可以。
- userData 必须隔离到本次 out 目录，复用别的项目的 profile 会撞单实例锁并污染用户数据。

## 判读边界（写进汇报）

- `evaluate_script` 调 `buildExportWorkbook()` + `sheet_to_json` 回读，证明的是工作簿结构与数值，不证明浏览器真的完成了下载动作。
- 截图与 `report.json` 证明的是布局，不证明业务数字；数字只认第 4 步的断言。
- 断言只核笔数、不核公司名归属与承上计数，会把算错分组的 bug 判成全绿通过。
