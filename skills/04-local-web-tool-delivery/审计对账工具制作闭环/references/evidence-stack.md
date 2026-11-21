# 六层证据栈：让「通过」可以被推翻

一个交付给非技术用户、结果要进审计底稿的工具，不能只说「测过了」。本项目把证据拆成六层，每层证明的东西不同，**任何一层都不能替另一层作证**。

## 总表

| 层 | 证明什么 | 不证明什么 | 何时必跑 |
|---|---|---|---|
| 1 语法检查 | 文件能被引擎解析 | 行为对不对 | 每次改完 JS |
| 2 golden 快照 | 每个夹具的认列/范围/记录/净额/配对/导出**逐字段**没变 | 没覆盖到的输入、指针操作 | 改业务口径、升版本前后 |
| 3 vm 沙箱断言 | 单条口径的边界（含只读性） | 真实点击、布局、打印 | 每次改对应模块 |
| 4 一命令全量回归 | 所有套件同时绿，且断言条数没缩水 | 同上 | 每轮收尾 |
| 5 真窗口 QA | 指针拖框、打印媒体、剪贴板、桌面/窄屏布局 | 业务口径的正确性 | 改交互/打印/布局 |
| 6 真实语料 + 交付包往返 | 真实底稿的识别质量、用户拿到的 zip 与源目录一致 | 用户是否真的会用 | 换版本、换认列规则 |

## 1. 语法检查

```bash
cd "<项目>" && ELECTRON_RUN_AS_NODE=1 "<app-dir> CN/Qoder CN.exe" --check assets/app.js
```

没有 node 在 PATH 时，用宿主自带的 Electron 以 Node 模式执行；**必须显式设 `ELECTRON_RUN_AS_NODE=1`**，否则 `Qoder CN.exe` 会按 GUI 启动。

## 2. golden 快照（算得对不对）

做法：把 `app.js` 装进 Node `vm` 沙箱，跑真实的「导入 → 认列 → 解析 → 归并 → 配对 → 取数核对 → 标准导出 + 分企业导出」，把结果写成**每个夹具一份 JSON**，再逐字段比对。

- 每个夹具定格：每张表的表头行、认出的列、取数范围、方向来源、是否猜的、笔数/跳过原因/重分类/净额、两套容差下的配对、导出工作簿的行内容。
- **条件性内容也要定格**：没有对应数据时该表不存在，有数据时列数、`!autofilter` 范围、金额格式都要断言。
- `--update` 重写黄金文件后**必须人工看 diff**：只应出现这次故意改的字段。若只有指纹变了而业务没变，先查是不是把版本号/环境字段塞进了规范 JSON。
- 固定环境变量：日期型账龄的基准日必须钉死（本项目 `state.ageBaseDate = '2026-10-31'`），否则黄金文件每天变红。
- 夹具一律合成（编造企业名 + 编造金额），真实底稿绝不进仓库。

**结果指纹设计**（若项目需要「同一批数据算出同一串码」）：对规范 JSON 做 SHA-256；所有列表用**码位排序**（不用 `localeCompare`，否则不同语言环境算出不同指纹）；刻意排除差异说明、签字信息、工具版本号——升版本不该换掉所有底稿的指纹。

## 3. vm 沙箱断言（单条口径的边界）

沙箱加载 `app.js` 后直接调顶层函数。四个必踩点：

- **顶层 `const`/`let` 不挂 `window`**：`state`、`colPick`、`els` 这类按名读得到，`window.state` 是 undefined。
- **控件 `els` 要打桩**：第二次 `runInContext` 给 `document.getElementById` 返回 stub，再补 `toast` 等节点。
- **要测点击委托，先 `cacheElements(); bindEvents();`**：`init()` 挂在 `DOMContentLoaded` 上，无头里不会自己触发；不绑就会得出「点了没反应」的假缺陷。
- **`printReport()` 要连 `setTimeout` 一起 stub**：8 秒兜底还原定时器会挂住事件循环，无头进程不退出，整套判超时。

断言纪律：

- 断言**结构**（列数、表头文字、`!autofilter` 范围、金额单元格格式），不能只断言「没抛异常」。
- 断言**只读性**：提示型操作前后，所有金额字段与结果指纹逐项相等。
- 断言**渲染后的 HTML**，不要用正则去源码里猜渲染结果；按 `class="x">` 切、以所属节点收尾，否则会被内层 `</span>` 截断。
- 期望值先跑再抄：不要手算；恒假断言（如 `notes or []`）要当场验红。

## 4. 一命令全量回归 + 条数闸门

```bash
cd "<项目>" && ELECTRON_RUN_AS_NODE=1 "<app-dir> CN/Qoder CN.exe" tests/run-all.cjs
# RUN_ALL suites=19 ok=19 bad=0 assertions=849/849
# RUN_ALL PASS
```

两个设计要点，缺一就会退化成空壳：

1. **每个套件在 runner 里写死期望条数**，实跑少了判 `SHRUNK`（有人删了一条断言但依然全绿，必须抓住）。
2. **汇总行解析要兼容两种写法**：多数套件打 `failures=N total=M`，个别打 `pass=P fail=Q total=M`，统一用 `/fail(?:ures)?=(\d+)\s+total=(\d+)/`。

控制台输出保持 ASCII（GBK 终端会把中文断言名打成乱码），逐套件明细写 UTF-8 报告 JSON。

## 5. 真窗口 QA（只有这里能测的东西）

指针拖框、打印媒体、剪贴板、真实点击、桌面/窄屏布局，在无 surface 的内嵌浏览器里全是假象，必须用真 Electron 窗口。

```bash
unset ELECTRON_RUN_AS_NODE && \
ELECTRON_ENABLE_LOGGING=1 "<electron.exe>" recon-qaN.cjs --out "<报告目录>" > qa.log 2>&1
```

- **`unset` 不是摆设**：会话环境常把 `ELECTRON_RUN_AS_NODE` 持久设成 1，不 unset 就会按纯 Node 跑、`require('electron')` 直接失败。
- **页面必须带 `?nocache=`**，否则断言到旧代码。
- **端口只认 marker 文件**，不写死；起服务前探测占用。
- **打印用 CDP 仿真**：桩掉 `window.print` 防弹框，`Emulation.setEmulatedMedia {media:'print'}` 后读 `getComputedStyle` 验隐藏/显示名单，验完清仿真；自动化里不会触发 `afterprint`，要手动 `dispatchEvent(new Event('afterprint'))` 验还原。
- **布局断言排除横滚容器内的元素**：明细/复制区本来就在 `overflow-x:auto` 里，只判 `documentElement.scrollWidth > clientWidth` 加根级溢出。
- **坐标每次现取**：`scrollIntoView` + `behavior:'instant'`，等滚动落定再取 `getBoundingClientRect()`；`scroll-behavior: smooth` 会让旧坐标失效。
- **点完重绘必须重新 `querySelector`**：整块重画的节点已脱离文档，旧引用读到的永远是点之前的值。
- **进程卫生**：只结束自己启动的 PID，`Stop-Process -Id` 前用 `Get-CimInstance Win32_Process` 核对命令行；绝不 `taskkill /IM electron.exe`。

## 6. 真实语料体检 + 交付包往返

**语料体检**（用户授权、只在本机、永不进仓库）：

- 跳过个人信息与大文件（本项目 `SKIP_RE` 含工资、汇报、副本、`~$`、doc/pdf/txt 等）。
- 报告字段写 `usable`（有企业列+金额列+方向+有行）、`sus`（可疑认列）、`noAmount`（整表无金额）；**不要用「自动勾选数」当识别质量指标**——改成默认零勾选后它恒为 0，旧基线会误导。
- 历史教训：把「单元格数字格式占比」塞进认列闸门，自动勾选从 19 张涨到 64 张，把分析列全勾进来。格式只能用于**事后判证据**，不能当准入闸门。

**交付包往返**：

```bash
python scripts/pack-offline.py "<输出 zip>"     # 白名单逐条 assert size>0，再回读 CRC/条目/字节
python <校验脚本>                                # 列出条目名 + testzip() + 解压逐文件 MD5
```

- 打包脚本是**白名单**：新增交付文件必须同时加进 `items`，否则包会静默缺文件；测试目录、交接稿、差距清单永不进包。
- PowerShell 5.1 的 `Compress-Archive` 没有 `-Exclude`，中文路径也不可靠：统一用 Python `zipfile`。
- Git Bash 的 `unzip` 看中文条目会乱码，**不代表包坏了**，用 Python `zipfile` 判定。

## 数字纪律

- 毫秒、字节、断言数、企业数只从报告 JSON 与磁盘取；文档里的数字要标版本与日期。
- 哈希值不写死：导出文件带时间戳，同一批数据两次导出必然不同；只断言「格式 64 位」「算出来的码 = 卡片上的码」。
- 「逻辑验证」与「真实交互验证」分开报告：劫持 `writeFile` 只能证明字节和文件名，不能证明浏览器真弹了保存框。
- 没测就写「没测」，不写成「通过」。
