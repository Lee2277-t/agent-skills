---
name: offline-web-tool-fixture-regression
description: "用合成文件验证本地网页工具的导入、计算和导出内容。适合已有可用测试入口或明确要求免选择器的任务；逻辑测试与真实上传下载分开报告，不强制改造应用暴露内部状态。"
---

# 本地工具页夹具回归

## Overview

对 `file://` 直开、纯前端解析（SheetJS 之类）的工具页做功能回归：不起后端、不点 UI、不产生真实下载，靠「临时 CORS 夹具服务器 + 页面上下文直接调函数 + 断言精简指标」完成，并在交付前用 md5 逐文件核对 zip 与源目录。

硬性前提：夹具与服务器全在本机，`127.0.0.1` 绑定，数据一律合成。真实底稿/客户资料绝不进夹具。

## 适用判定（先做，别默认能跑）

1. 先检查真实测试入口：普通脚本中的顶层函数或 `var` 可能挂在 `window`，但顶层 `const`/`let` 不会自动成为其属性。模块或闭包没有显式暴露入口时，使用当前宿主支持的 DOM/文件上传方式，不编造 `window.state` 或假定某个 browser MCP 已存在。
2. 导入入口是否吃 `ArrayBuffer`/`Blob`（而不是只吃 `input.files`）：只吃 File 对象时，用 `new File([buf], 'x.xlsx')` 现造。
3. 导出是否真的需要下载：把 `XLSX.writeFile`（或等价写盘调用）当唯一出口劫持即可捕获字节，无需真下载。

## 步骤

### 1. 起夹具通道

```bash
node <本技能目录>/scripts/serve-dir.cjs <fixturesDir> 8790
```

输出里 `READY http://127.0.0.1:<port>/` 才是真端口——端口占用（`BUSY ...`）在本机是常态，脚本会自动向上试。后续一律按 `READY` 行拼 URL，不要假设就是 8790。

`file://` 页面 `fetch http://127.0.0.1` 必带 `Access-Control-Allow-Origin`，直连本地文件路径不行，这就是这个服务器存在的唯一理由。

**每个夹具 URL 先发一次 HEAD/GET 断言 200 再进第 3 步。** 服务器根目录就是夹具目录，URL 只写文件名（多一层前缀就 404）；中文文件名在 `fetch` 里要 `encodeURI`。

### 2. 生成边界夹具

用 [references/fixture-and-assertions.md](references/fixture-and-assertions.md) 的生成脚本模板，直接 `require` 被测应用自带的 SheetJS（`<项目>/vendor/xlsx.full.min.js`），别新装依赖。必须覆盖的样本类型：合并单元格（企业名称留空续行）、仅表名含方向、表头上方带标题行、带方向列、方向列留空、负数、GBK/CSV、合计行、文件名推断。夹具是合成公司名 + 合成金额。

### 3. 免点击回归

在页面上下文用 `evaluate_script` 跑：`fetch 夹具 → 造 File → 调应用的导入函数 → 调对账/计算函数 → 读 state 断言`。

断言只回传精简指标（笔数、分组净额、跳过原因分布、承上行数、公司名归属），**不要 `JSON.stringify(state)` 全量返回**，大对象会把上下文撑爆。脚本拆成小步，每步先 `typeof window.xxx === 'function'` 探测再调；一处写错整段报废，重跑比调试便宜。

期望值从夹具定义反推，不要"跑出来多少就记多少"——那只是把 bug 固化成基线。

### 4. 导出闭环

劫持写文件函数捕获 workbook 与文件名 → 断言 sheet 名、列头、关键单元格 → 把同一批字节 `XLSX.read` 回灌、或直接再喂给第 3 步的导入函数，比对与页面结果一致。对"生成示例文件"这类功能，这一步是唯一能证明产物自洽的方式。

### 5. 交付包一致性

```bash
node scripts/verify-package-parity.cjs <package.zip> <srcDir>
```

解包到 `%TEMP%`，容忍 zip 顶层多一层同名目录，按相对路径逐个 md5 比对，输出 `OK/MISSING/DIFF/EXTRA` 与 `SOURCE_FILES/ZIP_FILES` 计数，跑完自动删临时目录。任何 `MISSING`/`DIFF` 都算失败——文件在包里但内容旧，是最难被发现的一类。

### 6. 收尾

杀掉服务器进程；夹具目录留在 `%TEMP%` 的测试区，不得进交付包，也不得写进被测项目目录。

## 已知坑（本轮实测）

- **端口冲突**：固定端口早晚会撞别的项目，靠 `READY` 行取真端口，或干脆传 0 让系统分配。
- **夹具 404**：URL 带了子目录前缀、中文文件名未编码、服务器根选错（根应是夹具目录，不是项目目录）。
- **`cleanCell` 的 trim**：这类工具普遍对单元格/整行做 `String(v).trim()`。手工拼接的 TSV 续行（首列留空 = 行首制表符）会被"丢弃前导空字段"的规则改写，续行变成一个新公司名。**断言必须查公司名归属与承上计数，只核笔数会全绿通过却算错分组。**
- **一次性写错的脚本**：`evaluate_script` 里箭头函数/构造器少写一个括号就整段失败，且失败信息可能被吞。宁可多跑两次小脚本。
- **file:// 的请求限制**：个别浏览器直接禁掉 `file://` 页面的网络请求。备选：把夹具内容 base64 内联进脚本，再还原成 `ArrayBuffer`；或把应用本身也放到 `127.0.0.1` 上跑同源。
- **没被覆盖的动作**：劫持 `writeFile` 证明了 workbook 内容与文件名，但没证明真实浏览器里的下载动作。报告时要把这条差异说清楚，不要说"导出已实测"。

## Resources

- [scripts/serve-dir.cjs](scripts/serve-dir.cjs) — 只绑 127.0.0.1、带 CORS 头的一次性夹具服务器。
- [scripts/verify-package-parity.cjs](scripts/verify-package-parity.cjs) — zip 解包 → 逐文件 md5 比对源目录 → 清理临时目录。
- [references/fixture-and-assertions.md](references/fixture-and-assertions.md) — 夹具生成脚本模板、`evaluate_script` 断言与导出劫持模板。
