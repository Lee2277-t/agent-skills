# 证据流水线

目标：任何一句「已经好了」都能被一条命令推翻或证实。人看日志不算证据，脚本产出的 JSON 才算。

## 1. 四层证据

| 层 | 谁写 | 断言什么 | 本项目的量 |
|---|---|---|---|
| 引擎用例 | 直接调 `PT.*` | 产物的**结构**：页数、`/Rotate`、`/V`、字节数 | 17 例 |
| 命令行断言 | CLI 子进程 | 退出码、报告字段名、`files[].ok` | 298 条 |
| 界面宿主 | 隐藏 Electron 窗口 | 真实 DOM 流程 + 结果 JSON | 33 项测试里过半 |
| 独立裁判 | PyMuPDF | 从外部打开产物反查 | 每轮都用 |

要点：

- **结构断言 > 无异常断言**。`await split(...)` 不抛只说明没崩；必须再读回产物核对页数与顺序。
- **裁判不能是同一套代码**。用 pdf-lib 写、再用 pdf-lib 读，只能证明「自洽」，不能证明「合法」。
- **源文件不变**是独立断言项：所有命令跑完，输入文件的 sha256 必须与跑之前相同。

## 2. 夹具：只生成，不手改

- 每类样本一个生成脚本（`tests/make_*.py`），产物落在 `fixtures/`。**不要手工修改二进制夹具**，否则无法复现、也无法解释为什么这条断言是那样。
- 夹具覆盖「边界」而不是「典型」：空页、单页、跨页书签、整页扫描图、旋转 90/180/270、带 `/NeedAppearances` 的表单、加密件、损坏件。
- 夹具内容一律合成（假公司名、假金额、假正文），真实作品不进测试目录。

## 3. TAG 单行协议（界面层最省事的做法）

约定：每个界面模式跑完，往 stdout 打**一行** `TAG {json}`，前缀全大写。

```python
TAG_RE = re.compile(r"^([A-Z][A-Z_]{2,})\s+(\{.*\})")

def _last_tag(out, tag):
    found = None
    for line in out.splitlines():
        m = TAG_RE.match(line.strip())
        if m and m.group(1) == tag:
            found = json.loads(m.group(2))   # 后出现的覆盖前面的
    return found
```

- **取最后一条**：同一标签可能先打中间态，最后一条才是结论。
- **判定看 `ok:true`**，不是看进程退出码（GUI 宿主退出码不可靠）。
- 人看的日志随便打，只有 TAG 行参与判定，互不干扰。
- 缺标签 = 失败，报「没看到 SPLIT 行」，不要静默当通过。

## 4. CASES 单一入口

回归脚本里只有一张表是权威用例清单：

```python
CASES = [
    ("build",  "重建单文件",        case_build,  "build"),
    ("engine", "引擎 17 例",        case_engine, "engine"),
    ...
]
```

- 新增测试**必须**进表，否则永远不会跑（这是最常见的「写了测试但没人跑」）。
- `--list` 打印表，`--build` 先构建再全跑，支持只跑指定几项。
- 每项记录 `ok` 与 `ms`，最后写 `tests/regress-report.json`，顶层 `ok` 是所有项的与。

## 5. 报告是数字的唯一来源

```json
// tests/regress-report.json
{ "ok": true, "results": [ { "name": "build", "ok": true, "ms": 84 }, ... ] }

// tests/cli-report.json
{ "ok": true, "cases": 298, "failed": [] }
```

- 文档里写「416.6 秒」，就必须等于 `sum(r.ms)`；写「298 条断言」，就必须等于 `cases`。
- 汇总用 `scripts/summarize-reports.py`，不要手算。
- 字段名一旦被断言引用就不能改名（本项目 298 条断言钉住了 `files[].fill.needAfter`、`verify.left`、`planned[]` 等）。重构时字段名属于行为契约。

## 6. 数字纪律

1. **先跑再抄**：任何毫秒/字节/条数，先跑命令，再写进文档。
2. **每轮收尾前 `grep -n "末次实测"`**，把所有「末次实测」逐个核对；本项目审计时正是这样抓到两处还停在上一轮（400.9 秒 vs 416.6 秒）。
3. **不许写区间凑数**：写「165–590 秒抖动」时必须确认两端都真的出现过。
4. **区分验证强度**：逻辑验证写「逻辑验证」，真点过写「真窗口点击」。劫持下载函数只能证明字节与文件名。

## 7. 环境坑（Windows + 中文路径）

| 现象 | 原因 | 处理 |
|---|---|---|
| 输出 GBK 报错 | 控制台默认 GBK | `PYTHONIOENCODING=utf-8`，或 `python -X utf8` |
| `node cli.cjs` 失败 | 本机没装 Node | 用 Electron 的 Node 模式：`ELECTRON_RUN_AS_NODE=1 electron.exe cli.cjs` |
| GUI 测试起不来 | 环境里残留 `ELECTRON_RUN_AS_NODE` | 跑界面前 `unset`；回归脚本在子进程环境里主动 pop 掉 |
| `.ps1` 中文乱码 | 无 BOM | 存 UTF-8 **带 BOM** |
| `.bat` 执行异常 | 非 ASCII / LF | 纯 ASCII + CRLF，改完核头三字节 |
| 中文路径下脚本找不到文件 | 反斜杠转义 | 统一 `os.path` / 正斜杠，不要手拼字符串 |
| 长任务超时 | 全量回归可达数分钟 | 单项超时给足（本项目 900 秒），别用默认 120 秒 |

## 8. 用脚本汇总

```bash
python scripts/summarize-reports.py tests/regress-report.json tests/cli-report.json
```

输出形如：

```text
regress  ok=true  cases=34  sum_ms=438339  (438.3 s)
cli      ok=true  cases=298 failed=0
ALL OK
```

任一报告 `ok` 为假则退出码 1 —— 可以直接接到收尾流程里当门禁。
