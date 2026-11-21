> 上游参考资料：其中原作者的机器状态、固定数值、DSH 路径与审批习惯不代表当前环境。执行以本目录 SKILL.md、当前项目规则及用户授权为准。

# 布局、响应式、动效

## 布局

### 容器

```css
.container {
  width: 100%;
  max-width: 1120px;          /* 页面容器 */
  margin-inline: auto;
  padding-inline: max(16px, 4vw);   /* 窄屏不贴边，宽屏不无限撑 */
}

.prose { max-width: 68ch; }   /* 正文，中文约 34 字/行 */
```

68ch 是正文舒适上限。超过这个宽度，眼睛回到行首会找错行。

### 栅格

不要为了栅格引入整套框架。三种就够：

```css
/* 1. 自动填充（卡片网格）—— 最常用，不用写断点 */
.grid-auto {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
}

/* 2. 两栏（侧边栏 + 内容） */
.layout-sidebar {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr);   /* minmax(0,1fr) 防止内容撑破 */
  gap: 32px;
}
@media (max-width: 900px) {
  .layout-sidebar { grid-template-columns: 1fr; }
}

/* 3. 堆叠（最基础） */
.stack > * + * { margin-top: 16px; }
```

`minmax(0, 1fr)` 里的 `0` 很重要 —— 用 `1fr` 时，长内容（代码块、URL、表格）会把栅格撑破，这是最常见的布局 bug。

### 断点

只留两个：

```css
@media (max-width: 900px) { /* 平板：侧栏收起 */ }
@media (max-width: 640px)  { /* 手机：单列 */ }
```

三个以上断点说明布局本身有问题（依赖断点打补丁）。优先用 `auto-fill` + `minmax` 让它自己适应。

### flex 的常见错

```css
/* ✗ 长内容不收缩，撑破容器 */
.row { display: flex; }
.row .text { flex: 1; }

/* ✓ 加 min-width: 0 */
.row .text { flex: 1; min-width: 0; }
```

同理 grid 子项要 `min-width: 0` 或 `min-height: 0`。

### 粘性元素

```css
.sticky-header {
  position: sticky;
  top: 0;
  z-index: 10;
  background: var(--bg);        /* 必须有不透明背景，否则内容会透出来 */
  border-bottom: 1px solid var(--border);
}
```

`position: sticky` 失效的三个原因：祖先有 `overflow: hidden`；父元素高度不够；没设 `top`。

---

## 响应式

### 移动端必须先想

- 触控目标 ≥ 44×44px（Apple HIG）/ 48×48（Material）。`audit_ui.py` 会查。
- 输入框字号 ≥ 16px，否则 iOS Safari 会自动放大页面。
- 不要用 `:hover` 做关键交互（手机上没有 hover）。
- 不要 `position: fixed` 底部工具栏 + 软键盘，键盘弹出会遮挡。

### 安全区

```css
padding-bottom: env(safe-area-inset-bottom, 0);
```

有刘海/手势条的机型需要。

### 视口

```html
<meta name="viewport" content="width=device-width, initial-scale=1">
```

不要加 `user-scalable=no`（无障碍问题，且 iOS 会忽略）。

### 图片

```html
<img src="x.png" alt="说明" width="800" height="500" loading="lazy" decoding="async">
```

`width`/`height` 必填，否则加载时页面会跳。`aspect-ratio` 也可以：

```css
img { max-width: 100%; height: auto; aspect-ratio: 16 / 9; object-fit: cover; }
```

---

## 动效

### 时长

| 用途 | 时长 |
| --- | --- |
| 颜色/背景变化 | 120–150ms |
| 位移/缩放 | 150–200ms |
| 展开/收起 | 200–250ms |
| 进出场（首屏） | 250–400ms |
| 页面转场 | 300–400ms |

超过 500ms 的交互反馈会让人觉得「卡」。

### 缓动

```css
/* 交互反馈：快进慢出，感觉「跟手」 */
--ease-out: cubic-bezier(0.16, 1, 0.3, 1);

/* 进出场：稍微带回弹 */
--ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1);

/* 标准 */
--ease: cubic-bezier(0.4, 0, 0.2, 1);
```

**不要用 `ease-in-out` 做交互反馈**，它两头慢，感觉黏。`ease-in-out` 只适合「出现又消失」的对称动画。

### 只动这两个属性

```css
/* ✓ GPU 加速 */
transition: transform 150ms var(--ease-out), opacity 150ms var(--ease-out);

/* ✗ 触发重排，卡 */
transition: all 300ms;
transition: width 300ms, height 300ms, top 300ms;
```

`transition: all` 是性能杀手，也是「改了 A 结果 B 也动了」的根源。

### 七条容易见效的细节

1. **按压反馈**：`:active { transform: scale(.97) }`。按钮要像在听。
2. **不要从 `scale(0)` 进场**：从 0.9–0.95 开始，元素才像有实体，不像凭空出现。
3. **后续提示免延迟**：第一个 tooltip 延迟 300–500ms 防误触；同一组里后续的直接出现，不再动画。
4. **进场用 `ease-out`**：起步快，感觉响应快；`ease-in` 起步慢，同样时长会显得拖。
5. **origin-aware**：弹层 `transform-origin` 指向触发按钮，从它那一侧长出来，不要从屏幕中心放大。
6. **高频交互不加动画**：一天要看几十次的列表、菜单，动画会从「愉悦」变成「变慢」。加动效前先问它一天出现几次。
7. **兜底用轻微模糊**：缓动和时长都调过还是别扭，给状态切换加 2px `filter: blur()`，能糊掉两个状态之间的硬切。

内置缓动通常不够有劲，可以自定更强的 `ease-out`；曲线库见 [sources.md](sources.md) 里的 easings.co。

### 无障碍

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

必加。有些用户会因为动效头晕/恶心。

### 首屏进场的正确做法

```css
/* 只做一次，只动 opacity + translateY，只动首屏 */
@keyframes rise {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: none; }
}
.hero > * {
  animation: rise 400ms var(--ease-out) both;
}
.hero > *:nth-child(2) { animation-delay: 60ms; }
.hero > *:nth-child(3) { animation-delay: 120ms; }
```

延迟最多 3 级，再多就感觉慢。

---

## 性能

改美观时最容易顺手搞坏性能。三条底线：

1. **不要给滚动容器加 `backdrop-filter`** —— 每帧都在重算模糊，滚动掉帧。
2. **不要用 `box-shadow` 做 hover 的持续动画** —— 阴影重绘很贵。用 `opacity` 叠一层伪元素代替。
3. **字体不要阻塞渲染** —— `font-display: swap`，或直接用系统字体。

---

## 暗色模式

```css
:root {
  color-scheme: light dark;   /* 让表单控件、滚动条跟着变 */
}
@media (prefers-color-scheme: dark) {
  :root { /* 只改颜色变量 */ }
}
```

要点：

- 深色背景用 `#0d1117`，不用纯黑 `#000`（纯黑在 OLED 上会让白色文字发光刺眼）
- 深色模式下的阴影几乎看不见，改用边框区分层次
- 深色模式下图片要降亮度：`filter: brightness(0.85)`
- 不要用 `filter: invert()` 整体反色

---

## 打印

如果页面会被打印（发票、报告、文档），加一段：

```css
@media print {
  nav, footer, .no-print { display: none; }
  a[href]::after { content: " (" attr(href) ")"; }  /* 打印出来知道链接去哪 */
  body { color: #000; background: #fff; }
}
```
