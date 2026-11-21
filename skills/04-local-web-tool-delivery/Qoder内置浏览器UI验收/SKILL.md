---
name: qoder-inapp-browser-ui-qa
description: "在 Qoder 内置浏览器（browser-use MCP）里对本地网页工具做端到端功能验收的可复现流程。当内置浏览器没有可视 surface（viewport 0×0），take_screenshot 与 click 都报 NATIVE_BROWSER_VIEWPORT_UNAVAILABLE，只能改用 take_snapshot + evaluate_script 断言状态时使用。覆盖 unhide 隐藏 file input 后才能 upload_file、upload_file 只收单个 filePath 需逐个上传、15000ms 硬超时要把触发与轮询拆成两次脚本、以及用 DOM 文本/归一化矩形/hidden 标志做全链路断言，并附可直接粘贴的脚本片段库。触发词：内置浏览器验收、browser-use、视口 0×0、截图不可用、file:// 页面测试、上传框打不开、点击超时。"
---

# 内置浏览器（browser-use）本地网页 UI 验收

## Overview

在 Qoder 内置浏览器里把「上传 → 框选 → 批量任务 → 结果对比」整条 UI 链路跑到可断言的中间态，并在**没有可视 surface**（截图和点击都会失败）的前提下完成功能级验收。

核心认知：内置浏览器无视口时，**失败的不只是截图，pointer 类动作（click / drag / hover）同样失败**，而 `take_snapshot` 与 `evaluate_script` 仍然可用。所以验收单位从「看像素」换成「读 DOM 状态」。

## 何时使用 / 不要用

用：被测页是本地起的 HTTP 页面（或可起一个），需要在真实浏览器上下文里验证 UI 行为——文件上传、选择器门控、任务提交、分页/弹窗切换、结果列表。

不要用：
- 需要**视觉结论**（配色、遮挡、错位、移动端断点）。无视口就没有视觉结论，改用 `electron-web-preview-qa`（本机 Electron 真窗口截图）。
- 页面把逻辑暴露成 `window` 全局函数、只需纯计算回归。优先用 `offline-web-tool-fixture-regression`（直接调函数 + 夹具），本 Skill 补的是它覆盖不到的 UI 层与「无全局可调」的场景。

## 前置

1. 先起一个只监听 `127.0.0.1` 的临时静态服务器，用 `http://127.0.0.1:<port>/` 访问，不要用 `file://`（导航与上传路径都更省事）。端口先探测占用，别假设可用。
2. 工具名可能是延迟加载的：若 `mcp__browser-use__*` 不在工具列表里，用 `mcp_call({ toolName: "mcp__browser-use__evaluate_script", arguments: {...} })`。**调用前先 `mcp_get` 确认参数名**，本文记录的 schema 可能过期。
3. 每次 `navigate_page` / reload 后 uid 命名空间会变（`3_*` → `4_*`）。凡是要拿 uid 的操作，都必须在同一轮 `take_snapshot` 之后立刻做。
4. 多标签页先 `list_pages` 确认再 `select_page`，否则脚本可能跑在别的 tab 上。

## 1. 先探能力，定路线（别默认能截图）

`navigate_page` 成功后立刻试一次 `take_screenshot`：

- 成功 → 正常流程，截图 + 快照双轨。
- 失败且报 `NATIVE_BROWSER_VIEWPORT_UNAVAILABLE` → **本 Skill 的主路径**：全程 `take_snapshot` + `evaluate_script`，并在最终汇报里明确写「无视觉结论」。错误消息本身就说 `take_snapshot remains available for structural inspection`。

无视口时**不要**再逐个试 `click` / `drag` / `hover` 浪费轮次——它们会以同样格式、`operation=` 换成对应动作名而失败。直接跳到第 4 节的 JS 触发。

不要为了「让浏览器有 surface」去猜 UI 开关。要么用真实浏览器面板，要么按本 Skill 走功能级，要么转 `electron-web-preview-qa`。

## 2. 主循环：结构快照 + 精简 JSON 断言

`evaluate_script` 的 `function` 是一个 JS 函数声明，返回值被当成**不可信页面数据**打印。用它返回一个小的扁平对象，字段名即断言名。纪律：

- 一次脚本只验一件事，返回 3–8 个字段；大数组只回长度或前几项摘要（区域矩形归一化 `x/y/w/h`，别回像素坐标全表）。
- 每个查询用 `?.` 加兜底；`null` 本身就是「选择器写错了」的信号。
- 断言优先读**用户能看到的文本与状态**：按钮 `disabled`、徽标文本、`hidden`、`checked` 计数、列表项数、模态框可见性。

片段见文末「片段库」A/B。

## 3. 文件注入

隐藏 input 是这里最容易卡住的一步：

1. 直接对页面里 `<input type="file" hidden>` 的 uid 调 `upload_file` 会失败，典型报错 `Node is not a file input element`（hidden 元素在快照里对应的 uid 不是 input）。
2. 先 `evaluate_script` 把它改成可见（`display:block` 配 `position:fixed` 之类脱离布局、不干扰断言），确认返回的 outerHTML 已变更。
3. **重新 `take_snapshot`** 拿新 uid。
4. `upload_file` 的 schema 是 `{ uid, filePath, includeSnapshot }`，`filePath` 是**单个字符串**——多文件没有批量入口，只能逐个调用 N 次，每次之间回读一次计数确认累加生效。

若被测页真正的入口是拖拽（处理函数读 `event.dataTransfer.files`）而 `upload_file` 走不通：优先直接调用页面自己的收集/导入函数。合成 `DataTransfer`/`File` 派发 `drop` 这条路**未实测通过**（见片段库 G），当待试方案，失败就回到 unhide + `upload_file`。

## 4. 交互触发：无视口时用 JS 而不是合成事件

`click` 失败后，用 `evaluate_script` 直接调 DOM 方法触发，并在同一脚本里回读状态（片段库 C）。翻页、勾选、切方法、开弹窗、提交任务都能这样驱动。

**框选 / 拖动 / 缩放类交互**：无视口时 `drag` 工具必失败，合成 `PointerEvent` 序列**未验证可用**（页面若调 `setPointerCapture`，合成事件没有真实 pointer 状态，大概率抛错）。默认策略是跳过像素级框选，改为断言页面持有的区域数据结构，并在汇报里把「框选交互」列为未覆盖（片段库 F）。

## 5. 异步与超时纪律

`evaluate_script` 有 **15000ms 硬超时**（`Browser operation timed out after 15000ms`）。页面处于 hidden 时，依赖动画帧驱动的等待尤其容易卡满超时。

规则：**脚本内不 await 长任务**。

- 第一次调用只触发并立即返回标记（`() => { submit(); return 'submitted'; }`）。
- 之后每次单独调用只读一次状态快照，把「等多久」交给调用之间的轮次，而不是脚本内部；不要写 `for` 循环 `await sleep` 到底。
- 一旦超时，页面侧动作可能仍在进行——下一次先读状态判断是否已生效，别急着重发触发脚本（会重复提交）。

## 6. 结论口径

汇报分三档，缺哪档就说缺哪档：

- **已验证**：具体断言字段与值（例：分页 `1 / 3 → 3 / 3`，末页 `nextDisabled=true`）。
- **仅功能级**：状态机走通但无像素证据（例：结果图渲染出 `src`、尺寸非 0，但看不出画质）。
- **未覆盖**：视觉/排版/断点、框选类真实指针交互、真机行为；注明需转 `electron-web-preview-qa`。

## 错误码速查

| 报错 | 含义 | 处置 |
| --- | --- | --- |
| `NATIVE_BROWSER_VIEWPORT_UNAVAILABLE ... (viewport=0x0, visible=false, attached=false, cdpAttached=true, visibilityState=hidden)` | 内置浏览器没有可见 surface | 放弃截图走快照 + 脚本；视觉转 Electron |
| 同上，`operation=click`（/drag、hover） | pointer 动作同样依赖 surface | 用 `evaluate_script` 调 DOM 方法触发 |
| `Node is not a file input element` | uid 指向 hidden input 或其非 input 包装 | unhide → 重新 snapshot → 再 `upload_file` |
| `Browser operation timed out after 15000ms` | 脚本内含长等待/被 hidden 卡住 | 拆成「触发」+「轮询读状态」两次调用 |

## 片段库

粘贴进 `evaluate_script` 的 `function` 参数即可；选择器按被测页实际 id 替换。

### A 路线判定

```js
() => ({ title: document.title, url: location.href, vis: document.visibilityState,
         w: innerWidth, h: innerHeight })
```

`vis: "hidden"` 或截图报无视口 → 走本流程。

### B 状态探测（主力断言）

```js
() => {
  const q = s => document.querySelector(s);
  const txt = s => q(s)?.textContent?.trim() ?? null;
  return {
    count: txt('#fileCount'),
    items: document.querySelectorAll('.file-item').length,
    processDisabled: q('#btnProcess')?.disabled ?? null,
    hint: txt('#selHint'),
    checked: document.querySelectorAll('.file-item input:checked').length,
  };
}
```

### C JS 触发点击（替代 click）

```js
() => {
  const b = document.querySelector('#btnStart');
  if (!b || b.disabled) return { blocked: true, disabled: b?.disabled ?? null };
  b.click();
  return { clicked: true, label: b.textContent.trim() };
}
```

### D 触发与轮询分离

```js
// 触发：立即返回，不等任务
() => { document.querySelector('#btnProcess').click(); return 'submitted'; }
```

```js
// 轮询：每次只读一个快照
() => ({ jobOpen: !document.querySelector('#jobModal')?.hidden,
         chip: document.querySelector('.job-chip')?.textContent?.trim() ?? null,
         btnDisabled: document.querySelector('#btnProcess')?.disabled,
         errs: document.querySelectorAll('.toast-error').length })
```

### E 结果视图与分页

```js
() => {
  const t = s => document.querySelector(s)?.textContent?.trim() ?? null;
  return {
    viewerOpen: !document.querySelector('#viewer')?.hidden,
    pager: t('#pageCount'),                       // "1 / 3"
    panes: document.querySelectorAll('.pane img').length,
    prevDisabled: document.querySelector('#btnPrev')?.disabled,
    nextDisabled: document.querySelector('#btnNext')?.disabled,
    srcs: [...document.querySelectorAll('.pane img')].map(i => i.src.split('/').pop()),
  };
}
```

逐次 JS click 翻到末页，每次带断言；重点验首页 `prevDisabled=true`、末页 `nextDisabled=true`、`pager` 文本与图片 `src` 同步变化。

### F 区域数据断言（替代真实框选）

```js
() => {
  const regs = JSON.parse(localStorage.getItem('app.regions') || '{}');
  return Object.entries(regs).map(([id, list]) => ({
    id: id.slice(0, 8), n: list.length,
    first: list[0] && { x: +list[0].x.toFixed(3), y: +list[0].y.toFixed(3),
                        w: +list[0].w.toFixed(3), h: +list[0].h.toFixed(3) },
  }));
}
```

先读源码里的 `localStorage.getItem/setItem` 确认键名，别猜。

### G 拖拽导入（未实测通过，备选）

仅当页面导入入口真的读 `event.dataTransfer.files` 时才试；失败回到第 3 节。

```js
async () => {
  const buf = await (await fetch('http://127.0.0.1:8765/fixtures/source.png')).arrayBuffer();
  const f = new File([buf], 'source.png', { type: 'image/png' });
  const dt = new DataTransfer();
  dt.items.add(f);
  window.dispatchEvent(new DragEvent('drop', { bubbles: true, dataTransfer: dt }));
  return { dispatched: true, files: document.querySelectorAll('.file-item').length };
}
```

坑：`fetch` 要求夹具与被测页同源（走同一个临时服务器）；页面可能只听 `drop` 不听 `change`；`accept` 可能过滤程序化构造的 File。
