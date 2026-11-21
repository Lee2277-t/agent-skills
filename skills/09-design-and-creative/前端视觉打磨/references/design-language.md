> 上游参考资料：其中原作者的机器状态、固定数值、DSH 路径与审批习惯不代表当前环境。执行以本目录 SKILL.md、当前项目规则及用户授权为准。

# 四套设计骨架

定约束时从这里选**一套**，写下它的 token 值，然后全站只用这些值。混用两套就是新的 AI 味。

每套都给了：适用场景、色板、字阶、间距、圆角阴影、一个最小 CSS token 块。

---

## A. 文档型（Document）

**适合**：工具说明页、README 站、博客、文档、设置面板。最安全，最不容易露馅。
**参考气质**：GitHub Docs、Stripe Docs、Linear Docs。

```css
:root {
  --bg:        #ffffff;
  --bg-subtle: #f6f8fa;
  --fg:        #1f2328;
  --fg-muted:  #59636e;
  --border:    #d1d9e0;
  --accent:    #0969da;
  --radius:    6px;
  --shadow:    0 1px 3px rgba(31,35,40,.08);
}
```

| 项 | 值 |
| --- | --- |
| 字号 | 32 / 20 / 16 / 14（4 档） |
| 行高 | 标题 1.25，正文 1.65 |
| 正文宽度 | `max-width: 68ch` |
| 间距 | 4 / 8 / 12 / 16 / 24 / 32 / 48 / 64 |
| 圆角 | 只有 6px |
| 阴影 | 只有一层，透明度 0.08 |
| 字重 | 400 正文，600 标题，不用 700 |

**特点**：靠留白和字重做层级，几乎不用颜色。最耐看，也最难做错。

---

## B. 产品型（Product）

**适合**：SaaS 落地页、工具官网、需要展示功能的产品页。
**参考气质**：Linear、Vercel、Raycast。

```css
:root {
  --bg:        #0b0b0c;   /* 或亮色 #fafafa */
  --surface:   #141416;
  --fg:        #ededed;
  --fg-muted:  #8f8f96;
  --border:    #26262a;
  --accent:    #5b8def;   /* 只用一个强调色 */
  --radius:    10px;
  --shadow:    0 1px 2px rgba(0,0,0,.3);
}
```

| 项 | 值 |
| --- | --- |
| 字号 | 56 / 28 / 17 / 15（4 档，首屏标题可以很大） |
| 行高 | 标题 1.1，正文 1.6 |
| 间距 | 8 的倍数：8 / 16 / 24 / 40 / 64 / 96 / 128 |
| 圆角 | 10px（小元素 6px） |
| 阴影 | 极克制，靠边框区分层次 |
| 强调色用量 | 全屏不超过 3 处 |

**特点**：大留白 + 大标题 + 少量高饱和点缀。**必须有真实截图**，否则就是空壳。

---

## C. 仪表盘型（Dashboard）

**适合**：后台、数据面板、监控、管理工具。
**参考气质**：Grafana（克制版）、GitHub Insights、Linear 的 issue 列表。

```css
:root {
  --bg:        #ffffff;
  --surface:   #ffffff;
  --surface-2: #f6f8fa;
  --fg:        #1f2328;
  --fg-muted:  #59636e;
  --border:    #d8dee4;
  --accent:    #1f6feb;
  --ok:        #1a7f37;
  --warn:      #9a6700;
  --danger:    #cf222e;
  --radius:    6px;
}
```

| 项 | 值 |
| --- | --- |
| 字号 | 24 / 16 / 14 / 12（数据表格用 13px） |
| 行高 | 表格行 40px 固定高 |
| 间距 | 4 / 8 / 16 / 24 |
| 圆角 | 6px，表格单元格 0 |
| 数字 | `font-variant-numeric: tabular-nums`（必须！否则列不对齐） |

**特点**：密度高，靠分隔线和留白区分，不靠卡片阴影。**不要**给每个数字都套一个彩色卡片——这是 AI 味重灾区。

---

## D. 展示型（Editorial）

**适合**：作品集、活动页、介绍单页、需要「有设计感」的场合。
**参考气质**：个人作品集、Awwwards 上的克制案例。

```css
:root {
  --bg:     #faf9f7;   /* 暖白，不是纯白 */
  --fg:     #14120f;
  --fg-muted: #6b655c;
  --accent: #c2410c;   /* 一个暖色，用量极少 */
  --radius: 2px;       /* 几乎不圆角 */
  --serif:  "Noto Serif SC", Georgia, serif;
  --sans:   "Inter", "PingFang SC", sans-serif;
}
```

| 项 | 值 |
| --- | --- |
| 字号 | 72 / 36 / 20 / 16 / 14（可以 5 档，因为层级更丰富） |
| 字体 | 标题衬线 + 正文无衬线（中文标题可用思源宋体） |
| 间距 | 非线性：16 / 32 / 72 / 144（大留白是主角） |
| 圆角 | 0–2px |
| 装饰 | 最多 1 条细线或 1 个大号序号 |

**特点**：靠字体对比和大留白。**风险最高**——做不好就是「用力过猛」。中文排版尤其难，见 `typography-cn.md`。

---

## 怎么选

| 你的项目 | 选 |
| --- | --- |
| 别人要看懂怎么用 | A |
| 要让人觉得「这东西不错」 | B |
| 要装数据、要长时间盯着看 | C |
| 要展示审美（作品集/个人站） | D |

拿不准就选 **A**。A 最不容易翻车，而且改造成 B/C 很容易（换色板 + 调字号）。

---

## token 落地

选定后，把 token 写进**一个地方**（`tokens.css` / `:root` / tailwind config），其他地方一律引用变量。硬编码色值超过 12 个，`audit_ui.py` 会报。

```css
/* tokens.css —— 全站唯一真相 */
:root {
  /* 颜色：3 个 + 灰阶 4 档 */
  --accent: #0969da;
  --ok: #1a7f37;
  --danger: #cf222e;
  --fg: #1f2328;
  --fg-muted: #59636e;
  --border: #d1d9e0;
  --bg: #ffffff;
  --bg-subtle: #f6f8fa;

  /* 字阶：4 档 */
  --text-xl: 2rem;      /* 32 */
  --text-lg: 1.25rem;   /* 20 */
  --text-md: 1rem;      /* 16 */
  --text-sm: 0.875rem;  /* 14 */

  /* 间距：8 的倍数 */
  --s1: 4px; --s2: 8px; --s3: 12px; --s4: 16px;
  --s5: 24px; --s6: 32px; --s7: 48px; --s8: 64px;

  /* 圆角阴影：各 1 档 */
  --radius: 6px;
  --shadow: 0 1px 3px rgba(31,35,40,.08);
}
```

深色模式只改颜色变量，不动其他：

```css
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0d1117;
    --bg-subtle: #161b22;
    --fg: #e6edf3;
    --fg-muted: #8b949e;
    --border: #30363d;
    --shadow: 0 1px 3px rgba(0,0,0,.4);
  }
}
```
