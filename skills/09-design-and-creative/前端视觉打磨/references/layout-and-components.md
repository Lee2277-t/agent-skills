> 2026-10-30 整理，来源见 [sources.md](sources.md)。响应式、性能、暗色模式与动效在 [layout-and-motion.md](layout-and-motion.md)，这里只补布局组合与组件状态。

# 布局与组件：审美落在细节上

## 一、间距用关系说话

- 档位：4 / 8 / 12 / 16 / 24 / 32 / 48 / 64 / 96。
- 同组元素 8–12，组之间 24–32，区块之间 64–96。
- **先给多再收**：Refactoring UI 建议一开始留白给足，再往下减。反过来（先挤后加）很难补出呼吸感。
- 相邻距离 = 关系亲密度。格式塔的 proximity：靠得近的自动被读成一组。
- 卡片内不要同时用 `padding` 和 `margin` 撑同一个间距；选一个，否则调起来相互打架。

## 二、内在布局（Every Layout）

核心思想：**让浏览器算，不写断点**。用 flex 的比例和最小宽度触发换行，而不是给每个屏幕宽度打补丁。

### Stack：垂直节奏

```css
.stack > * + * { margin-block-start: var(--stack-space, 1rem); }
```

`* + *` 不会给第一个元素加间距，容器上下边界保持干净。比在每个子元素上写 margin 更好维护。

### Cluster：自动换行的横排

```css
.cluster {
  display: flex;
  flex-wrap: wrap;
  gap: var(--gap, .75rem);
  align-items: center;
}
```

标签组、按钮组、面包屑、图标列表都用它。窄屏自动换行，不需要断点。

### Sidebar：侧栏 + 内容，窄了自动堆叠

```css
.with-sidebar {
  display: flex;
  flex-wrap: wrap;
  gap: 1.5rem;
}
.with-sidebar > .sidebar {
  flex-basis: 240px;
  flex-grow: 1;
}
.with-sidebar > .content {
  flex-basis: 0;
  flex-grow: 999;
  min-width: 50%;   /* 低于这个宽度就换行 */
}
```

内容区 `flex-grow: 999` 让它优先占满剩余空间；`min-width` 是换行阈值。没有 media query。

### Switcher：低于阈值就从横排变竖排

```css
.switcher {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
}
.switcher > * {
  flex-grow: 1;
  flex-basis: calc((40rem - 100%) * 999);
}
```

`* 999` 是个开关：容器比 40rem 宽时算出负值（不换行），比 40rem 窄时算出巨大正值（强制换行）。适合「两个卡片并排，窄屏叠起来」。

### Cover：首屏撑满，内容居中，底部贴底

```css
.cover {
  display: flex;
  flex-direction: column;
  min-height: 100svh;
  padding: 2rem;
}
.cover > * { margin-block: 1rem; }
.cover > :first-child:not(.cover-main) { margin-block-start: 0; }
.cover > :last-child:not(.cover-main)  { margin-block-end: 0; }
.cover > .cover-main { margin-block: auto; }
```

用 `100svh` 而不是 `100vh`，避免移动端地址栏收起时内容被截。

### Frame / Imposter / Icon

```css
/* 固定比例，内容裁切 */
.frame { aspect-ratio: 16 / 9; overflow: hidden; }
.frame > img { width: 100%; height: 100%; object-fit: cover; }

/* 铺满父容器并居中：空状态、遮罩、加载层 */
.imposter { position: absolute; inset: 0; display: grid; place-items: center; }

/* 图标与文字对齐 */
.with-icon { display: flex; align-items: center; gap: .5rem; }
.with-icon > svg { width: 1em; height: 1em; flex: none; }
```

### 防撑破

- 栅格用 `minmax(0, 1fr)`，不要裸 `1fr`。
- flex 子项加 `min-width: 0`（横向）或 `min-height: 0`（纵向）。
- 长 URL / 代码才用 `overflow-wrap: anywhere`；正文用 `overflow-wrap: break-word`。

## 三、对齐与光学校准

- 一个页面只保留 **1–2 条主对齐线**：左边缘，或标题的基线。
- **数学居中 ≠ 视觉居中**。圆形按钮、图标、带不对称留白的图形，通常要手动偏移 1–2px 才「看起来正」。
- 图标与文字：flex 居中看视觉重心，不要只信 bounding box；内联图标用 `vertical-align: -0.125em`。
- 卡片内边距可以轻微不对称（上 20 / 下 24），因为文字有下沉感；但同一组件必须一致。
- 表格：文字左对齐，数字右对齐，表头与列内容同对齐。
- 右对齐的数字列，表头也右对齐；否则第一眼会觉得表头错位。

## 四、密度：先决定给谁看

| 场景 | 密度 | 行高 | 间距 |
| --- | --- | --- | --- |
| 营销页 | 低 | 大 | 64–128 |
| 文档/说明 | 中 | 1.65–1.75 | 24–48 |
| 后台/表格 | 高 | 1.4–1.5 | 8–16，行高 40–44 |

不要在同一个页面混两种密度。后台用营销页的留白会显得空；营销页用后台的密度会显得挤。

## 五、组件状态：审美的一半在非默认态

默认态谁都会做，差距在 hover、focus、active、disabled、空、载入、错误。

### 按钮

- 三级：**主**（实色）、**次**（描边）、**三级**（纯文字）。同屏主按钮只有一个。
- `:active { transform: scale(.97); }`——按下有反馈，界面才像「在听」。
- hover 只改一件：背景或边框。不要同时放大 + 加深阴影 + 换边框色。
- disabled 要降对比但保持可读；不要只用 `opacity: .3`，那会让文字消失。
- 次要按钮不需要背景；不是每个按钮都值得一个色块。

### 焦点

```css
:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
  border-radius: 2px;
}
```

- 不要 `outline: none`。
- 用 `:focus-visible`：鼠标点击不显示，键盘 Tab 才显示。
- 深色背景上的焦点环要换亮色，否则看不见。

### 输入

- label 永远在输入框上方；**不要把 placeholder 当 label**，输入后提示就消失了。
- helper 文案在下方；出错时用错误文案替换 helper。
- 错误写「哪里错 + 怎么改」（例：「邮箱缺少 @」），不要只写「格式错误」。
- 输入框字号 ≥ 16px，否则 iOS Safari 会自动放大页面。
- 错误态三件套：边框 + 图标 + 文案，不只变色。

### 空 / 载入 / 错误

- **空状态**：一句说明 + 一个动作。「还没有项目。新建一个」比「暂无数据」有用。
- **载入**：骨架屏，尺寸和真实内容一致；不要用转圈盖住整页。
- **错误**：说清发生了什么 + 下一步。不要只显示「出错了」。
- 长列表：分页或虚拟滚动，不要一次渲染 1000 行再让浏览器卡住。

### 表格

- 行高 40–44；表头 sticky；数字右对齐 + `tabular-nums`。
- 斑马纹不如 1px 分隔线；hover 整行高亮。
- 列多时先冻结首列，再考虑横向滚动；不要让用户靠记忆对列。

### 弹层

- `transform-origin` 指向触发元素：下拉从按钮那一侧长出来，而不是从屏幕中心放大。
- 焦点进入弹层，Esc 关闭，关闭后焦点回到触发元素。
- 背景滚动锁；移动端底部抽屉用 `100dvh` + 安全区。
- 遮罩不要纯黑 60%；用与页面同色系的深色 + 透明度，观感更统一。

### Toast

- 动作完成后出现，位置固定（右下或顶部居中，二选一）。
- 破坏性操作给 Undo，而不是先弹二次确认。
- 不遮挡主操作和输入框；一次最多一条，排队显示。

### 图标

- 一套线性图标，线宽一致；尺寸只用 16 / 20 / 24。
- 装饰图标加 `aria-hidden="true"`；只有图标的按钮必须有 `aria-label`。
- 不用 emoji 当功能图标；表情符号的字形随系统变，永远对不齐。

## 六、交付前 12 项

1. 只有一个 `<h1>`，主操作只有一个。
2. 字阶 ≤ 5 档，圆角 ≤ 2 档，阴影 1 层。
3. 灰阶带色相，没有大面积纯黑纯白。
4. 正文对比度 ≥ 4.5:1。
5. 行宽 ≤ 75 字符（中文 ≤ 40 字）。
6. 间距只用档位值，没有 13px / 27px。
7. 窄屏 390px 无横向滚动。
8. 键盘 Tab 能看到焦点。
9. 图片有 `alt`、宽高、`loading="lazy"`。
10. 空、载入、错误三态都有。
11. 动效 ≤ 300ms，只动 `transform` / `opacity`，有 `prefers-reduced-motion` 降级。
12. 至少删掉了一件装饰。
