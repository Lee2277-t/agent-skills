# 单文件架构

## 1. 目录骨架

```text
项目/
  web/
    index.html          # 唯一页面骨架；底部一串 <script src> 就是加载顺序
    css/app.css
    js/core.js          # 命名空间 + 通用工具（无 DOM 顶层）
    js/engine-*.js      # 各领域引擎，挂到 PT.<domain>
    js/app.js           # 全部界面接线
    vendor/             # pdf-lib / pdf.js / JSZip（随产物分发，不要改）
  build_single.py       # 内联成单文件
  分页工具-网页版.html    # 产物，不手改
  desktop/              # Electron 壳 + CLI + 启动器
  tests/                # 回归、夹具生成器、独立裁判
```

`web/` 是唯一真源；单文件、桌面版、命令行都从它派生。

## 2. 构建脚本的四道自检

```python
html = read(web/index.html).replace(
    '<meta name="pt-inline" content="0">',
    '<meta name="pt-inline" content="1">')          # 1. 标记位翻转

css = read(web/css/app.css)
html = re.sub(r'<link rel="stylesheet" href="css/app\.css">',
              lambda m: '<style>\n' + css + '\n</style>', html)

def inline_script(m):
    code = safe_js(read(path))                       # 2. 转义 </script>
    return '<script>\n/* ==== ' + src + ' ==== */\n' + code + '\n</script>'

html = re.sub(r'<script src="([^"]+)"></script>', inline_script, html)

if re.findall(r'<script src="[^"]+"|<link rel="stylesheet"', html):
    raise SystemExit('仍有未内联的外部引用')          # 3. 内联后再扫一遍
size = os.path.getsize(OUT)
if size > 9 * 1024 * 1024:
    print('⚠ 单文件超过 9MB')                        # 4. 体积告警
```

配套规则：

- `safe_js` 把 `</script>` 替换成 `<\/script>`，否则内联代码会提前截断页面。
- 每个内联块加 `/* ==== 源文件路径 ==== */` 注释，产物里仍能定位来源。
- 缺少源文件时**直接失败**，不要跳过——静默缺文件会造出一个「看起来能用」的残废产物。
- 产物不提交手改；改了就下次构建丢失。

## 3. 加载顺序契约

`index.html` 底部的 `<script src>` 顺序、CLI 的 `eval` 列表，是同一份契约的两处副本：

```javascript
// index.html（顺序即依赖顺序）
core.js → pdf-crypt.js → engine-pdf.js → engine-docx.js → engine-pptx.js
→ engine-validate.js → app.js
```

```javascript
// desktop/cli.cjs
const EVAL_FILES = ['web/js/core.js', 'web/js/pdf-crypt.js', 'web/js/engine-pdf.js'];
```

- `PT` 由 `core.js` 建；后续文件只往上挂 `PT.pdf` / `PT.crypt`。
- 依赖外部库的代码在**函数内**取 `global.PDFLib`，不要在顶层解引用。
- 新增文件必须同时改这两处；只改一处的典型症状是「网页好用、命令行 undefined」。
- `module.exports = PT.pdf` 只能出现在最后一个引擎文件里，否则 Node 侧拿到的是半成品。

## 4. 引擎必须能脱离 DOM 运行

命令行在 Node 里 eval 同一批文件，因此：

- **顶层**不许出现 `document` / `window` / `navigator`；
- 需要全局对象时：`(function (global) { ... })(typeof window !== 'undefined' ? window : globalThis)`；
- 函数体内可以有 DOM 调用（如保存文件用的 `downloadBlob`），只要 CLI 从不调用它；
- 新增共享模块同理：顶层只做定义，不做副作用。

判断方法：`ELECTRON_RUN_AS_NODE=1 electron.exe -e "require('./web/js/engine-pdf.js')"`，能 require 成功且不抛 `document is not defined` 才算过。

## 5. 双形态差异

| 形态 | 加载什么 | 何时生效 | 交付时 |
|---|---|---|---|
| 桌面版 | `pt://app/` → 直接读 `web/` | 改 `web/` 立即生效，**无需构建** | 随包带 `web/` |
| 单文件 | 内联后的 HTML | 必须重新 `build_single.py` | 只交付这一个文件 |

验收必须两条路各走一次：桌面版绿了不代表单文件绿（顺序、内联转义、worker 路径都可能不同）。

`file://` 下 pdf.js 的 worker 必须内联，并靠 `meta[name=pt-inline]=1` 让代码知道「我在单文件里」，从而走内联 worker 分支。这是单文件能在断网 `file://` 下渲染 PDF 的前提。

## 6. 构建后验收清单

1. 字节数与上一版对比，异常增大先查是不是重复内联。
2. `grep -c "pt-inline\" content=\"1\"" ` 命中 1 次。
3. 无 `<script src=`、无 `<link rel="stylesheet"`、无 `https://` 资源引用。
4. `file://` 双击打开，断网状态下：载入 PDF、预览、拆分、下载四项各做一次。
5. 桌面版再开一次（它读 `web/`，用于区分「构建问题」还是「代码问题」）。
