---
name: windows-local-web-tool-delivery
description: "在用户要求 Windows 双击运行且需要本地后端时，建立回环地址服务、单实例入口和可验收交付包。纯静态工具不强制增加 Python 服务，端口与认证按实际接口设计。"
agent_created: true
---

# 本机「双击即用」本地网页工具交付

Windows + Python 本地服务 + 浏览器 UI，交付给不懂命令行的用户。以下六步是在 `<project-root>\watermark-remover`（净印）从零跑通并稳定运行的实现，逐步照抄即可，不必重新设计。

完整可粘贴实现见同目录：
- `references/launcher.bat` — 已验证的启动器模板（只在开头多了一行 `rem` 编码提示，逻辑逐字同原文件）
- `references/server-bootstrap.py` — 端口、单实例、token 守卫、安全头、崩溃落盘

> 先判断是否需要后端。已有可运行项目优先修复和复用；本文固定端口区间、服务层与认证示例只适用于相应架构，不要求纯静态工具改成服务端应用。旧项目路径不作为复制来源。

## 先判断该不该用本 Skill

- **用**：工具需要后端（图像处理、视频、文件批量读写、本机目录访问），进程常驻，浏览器只是 UI。
- **不用**：纯 `file://` 打开的静态页、无后端 → 走 `win-offline-web-tool-regression-package` 或 `offline-web-tool-fixture-regression`（它们管回归与打包，本 Skill 管服务与启动器）。
- **不用**：套了 Electron 壳 → 走 `electron-windows-bootstrap` / `electron-desktop-pet-mvp`。
- 本 Skill 全部内容默认 Windows + Python venv + werkzeug；换栈时只借思路，别硬套端口号和话术。

## 硬性前提

- **只绑 `127.0.0.1`**，任何情况下不写 `0.0.0.0`。数据不出本机是这类工具唯一的隐私承诺。
- **绝不假设 8765 空闲**——本机该端口常被其他项目占用，必须「先扫再用」。
- `work/`、`成品/` 一律落在**工具自身目录**下（相对 `__file__`），不写用户主目录、不写 `%TEMP%`：用户要能自己找到成品。
- 覆盖用户已在用的成品目录或交付 zip 前先确认，那是成品不是中间产物。

## 1. 目录结构

```
工具目录/
  server.py              # 入口，werkzeug make_server
  requirements.txt
  templates/index.html   # 含 <meta name="app-token" content="{{ app_token }}">
  static/app.js
  remover/               # 业务模块
  work/                  # 运行时：runtime.json / tool.log / uploads/<sid>/ / zips/
  成品/                  # 面向用户的输出，中文名
  启动XXX工具.bat
```

路径全部由 `BASE_DIR = Path(__file__).resolve().parent` 派生；启动器会 `cd /d "%~dp0"`，但**不要依赖 CWD**。

## 2. 端口与单实例（最容易漏的一段）

三个函数各司其职，缺一不可：

- `choose_port()`：`for port in range(8765, 8786)`，用 `socket.bind(("127.0.0.1", port))` 试探，`OSError` 就 `continue`；扫不到就抛中文错「端口 8765-8785 都被占用，请关闭其他程序后重试」。
- `find_existing_instance()`：读 `work/runtime.json` 拿 port，`urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1.2)`，**只有响应里 `payload.get("app") == "<你的标识>"` 才算本机实例**。这一步是防呆关键：端口被别的项目占用时 health 必然不匹配，于是自动退回扫描下一个端口。整段包 `except Exception: return None`。
- `remove_runtime_file()`：**先校验 `int(data.get("pid", -1)) == os.getpid()` 再删**。不校验就会发生「新实例启动时把老实例的 runtime 删了」，两实例并存且互相抢浏览器。注册方式是 `atexit.register(remove_runtime_file)` **加上** `serve_forever()` 的 `finally` 双保险。

`main()` 顺序：建目录 → 清理旧文件 → `find_existing_instance()`；**命中就 `webbrowser.open()` 然后 `return`**，绝不报错退出——用户双击第二次只应该看到浏览器，这正是单实例的可见收益。

开浏览器用 `threading.Timer(0.7, ...)`，不要 `app.run()` 自带的方式；并提供 `JINGYIN_NO_BROWSER` 式的环境变量开关（`os.environ.get("XXX_NO_BROWSER") != "1"` 才开），自动化 QA 时不弹窗。

## 3. 安全模型（token + sid 两层）

```python
APP_TOKEN = secrets.token_urlsafe(32)   # 每进程随机，不落盘

@app.before_request
def prepare_request():
    if "sid" not in session:
        session["sid"] = uuid.uuid4().hex
    if request.path.startswith("/api/") and request.method in ("POST", "PUT", "PATCH", "DELETE"):
        token = request.headers.get("X-App-Token", "")
        if not secrets.compare_digest(token, APP_TOKEN):
            return jsonify({"error": "页面校验失败，请刷新后重试"}), 403
```

- 页面渲染时注入：`render_template("index.html", app_token=APP_TOKEN)` → `<meta name="app-token">` → JS 读进常量，**fetch 与 XHR 两条路都要带**（上传用 XHR 才有进度；`if (method !== 'GET' && method !== 'HEAD') headers['X-App-Token'] = TOKEN`）。
- 用 `compare_digest`，不用 `==`。
- GET 不校验：健康检查、页面、缩略图要能被浏览器直接取。
- **副作用必须写进 UI 话术**：token 每次重启即失效，用户旧页面点按钮会 403，所以错误文案直接给「请刷新后重试」。
- **sid 隔离**：上传落 `UPLOAD_ROOT / sid / item_id`；job 记 `session_id`，取别人的 job 一律 404（`if not job or job.get("session_id") != session["sid"]`）。单实例 + 多标签页共用一个服务时，靠这个互不串台。
- `after_request` 安全头：`/api/*` 加 `Cache-Control: no-store`，全站 `X-Content-Type-Options: nosniff`、`X-Frame-Options: DENY`、`Referrer-Policy: no-referrer`。

## 4. 成品交付

- 输出根目录用中文：`OUTPUT_ROOT = BASE_DIR / "成品"`，每次任务一个子文件夹。
- ZIP 端点（`GET`，浏览器直接下载）：`allowZip64=True`；**视频用 `ZIP_STORED`（再压也是白费 CPU），图片用 `ZIP_DEFLATED`**；`download_name` 起中文名 + 时间戳，如 `去水印结果_20261021_204723.zip`。任务未完成返回 409 中文提示。
- 打开文件夹端点（`POST`，受 token 守护）：Windows 用 `os.startfile(str(path))`，不要用 `explorer` 命令行（参数转义坑多且退出码不可靠）；非 nt 分支留 `xdg-open`。失败时把**绝对路径回显给用户**让其手动前往，别只报「失败」。
- 前端两个按钮配套：「下载 ZIP」+「打开文件夹」，非技术用户第二个往往更常用。

## 5. 启动器 .bat

六条规则全是踩出来的，逐条别改：

1. 存 **UTF-8 无 BOM**，行尾 **CRLF**，第 3 行立刻 `chcp 65001 >nul`，中文提示才不乱码。
2. 起进程用 `powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process ... -WindowStyle Hidden"`。**cmd 自带的 `start "" "程序"` 在 MSYS 拉起的 `cmd //c` 下会永久挂起且不启动进程**。
3. 等待用 `ping -n 5 127.0.0.1 >nul`，**不要用 `timeout /t`**——会被 coreutils 的 `timeout.exe` 抢先解析（报 `invalid time interval '/t'`）。
4. 用 **`pythonw.exe`**（无控制台窗闪），崩溃信息只能靠服务自己落盘（见第 6 步）。
5. 判成功用**文件信号**而非端口探测：`if not exist "%~dp0work\runtime.json"` 则报错 + `pause` + `exit /b 1`，并把「把 `work\tool.log` 最后几行发给开发者」写进提示——这是远程排查的唯一入口。
6. 前置检查 `.venv\Scripts\pythonw.exe` 缺失时，打印 `python -m venv .venv` + `pip install -r requirements.txt` 两条命令后 `pause` 退出。

## 6. 生命周期与崩溃落盘

- `__main__` 外层包 `try/except`：失败时 `mkdir` work → 把 `traceback.format_exc()` 追加写 `work/tool.log` → 有 stderr 再打一份 → `raise`。pythonw 下没这一步就永远拿不到堆栈。
- `/api/shutdown`：先查本 sid 是否还有 `queued`/`running` 任务，有则 409「还有文件正在处理，请等待完成后再关闭」；再 `SERVER_HOLDER["server"].shutdown()`。
- 启动时清理：`work/` 下超过 7 天的文件删除；半成品（如 `*.part.mp4`）超 12 小时删除。跳过单个文件用 `continue`，别整体失败。
- 日志 `app.logger.info` 记 `listening on http://127.0.0.1:<port>`，端口可被追溯。

## 验证清单

改完必须真跑，静态检查不算验收：

1. 双击 bat → 浏览器自动打开且 `work/runtime.json` 生成；**再双击一次 → 只多开一个浏览器标签，任务管理器里 pythonw 仍只有一个**。
2. `curl http://127.0.0.1:<port>/api/health` 返回你的 `app` 标识。
3. 不带 token `POST` 任一 `/api/*` → 403；带对 → 2xx。
4. 手工占掉 8765 再启动 → 服务落到 8766 且 UI 正常（验端口回退）。
5. bat 文件字节校验：无 BOM（头三字节非 `EF BB BF`）、含 `0D 0A`、无 `start ""`、无 `timeout /t`。
6. 「打开文件夹」真弹出资源管理器；ZIP 解出的文件名不是乱码。

从 Git Bash 驱动 bat 时另有环境坑（`> NUL` 被路径转换破坏、`taskkill /PID` 被转换、`.ps1` 无 BOM 中文乱码），见记忆 `win-batch-launcher-env`；验证时逐项插桩 `echo MARK`，别整跑猜哪段没执行——本项目 `start` 版就是连挂三次才这么定位到的。
