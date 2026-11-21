> 上游参考资料：其中原作者的机器状态、固定数值、DSH 路径与审批习惯不代表当前环境。执行以本目录 SKILL.md、当前项目规则及用户授权为准。

# 中文排版

中英混排的坑和英文完全不同。这一份只讲中文界面/正文。

## 字体栈

```css
/* 正文：优先系统字体，加载快、渲染稳 */
font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
             "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei",
             "Source Han Sans SC", "Noto Sans CJK SC", sans-serif;

/* 等宽：代码块 */
font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo,
             Consolas, "Liberation Mono", monospace;

/* 数字/英文优先：让英文和数字用西文字体，中文回退 */
font-family: "Inter", -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
```

**不要**为了「好看」去 `@import` 一个 10MB 的中文字体。思源黑体全量约 16MB，网页上等于自杀。真要自定义字体，用 `font-display: swap` + 只加载用到的字重，或用 `unicode-range` 分片。

## 字号与行高

中文的字面比英文大，同样 `16px`，中文看起来更挤。

| 用途 | 字号 | 行高 |
| --- | --- | --- |
| 正文 | 16px（最小 14px） | 1.7（中文比英文需要更松） |
| 次要说明 | 14px | 1.6 |
| 小标签 | 12px | 1.5 |
| 段落标题 | 20px | 1.4 |
| 页面标题 | 28–32px | 1.3 |

**中文行高 1.7 不是可选项**。用英文习惯的 1.5，中文读起来会挤成一团。这是最快暴露「模板改的」的地方。

## 字重

中文字体字重档位少，且很多系统只有 Regular(400) 和 Bold(700)。

- 正文 400
- 强调/小标题 500（如果字体有）或 600
- **大标题不要用 700+**，中文粗体在屏幕上容易糊成一团黑块。标题靠字号和留白，不靠粗细。
- 不要用 300（细体）做中文正文，低分屏会断笔画。

## 中英混排空格

中文和英文/数字之间加一个空格，这是中文排版的硬规矩：

```
✗ 支持PDF和Word格式
✓ 支持 PDF 和 Word 格式

✗ 共3个文件
✓ 共 3 个文件

✗ 使用GitHub Actions部署
✓ 使用 GitHub Actions 部署
```

例外：中文标点前后不加空格；百分号紧贴数字（`50%`）。

## 标点

- 中文正文用全角标点：`，。；：？！「」（）`
- **不要**用英文标点混进中文句子（`,` `.` `:` 在中文里看着很怪）
- 引号：中文用 `「」` 或 `""`，不要用 `""`（直角引号在简中排版里更干净，但 `""` 也可以，别混用）
- 省略号用 `……`（六个点），不是 `...`
- 破折号用 `——`（两个），不是 `--`

## 数字

```css
/* 表格、列表里的数字必须等宽，否则列不对齐 */
font-variant-numeric: tabular-nums;
```

- 阿拉伯数字用半角：`123`，不要 `１２３`
- 百分比：`50%`（无空格）
- 金额：`¥99` 或 `99 元`，全文统一
- 日期：`2024-01-15` 或 `2024 年 1 月 15 日`，全文统一，不要两种混着

## 对齐

- 中文正文**左对齐**，绝不两端对齐（`text-align: justify` 会让中文词间距忽大忽小）
- 标题可以居中（短），长标题左对齐
- 表格里的文字左对齐，数字右对齐
- 不要用 `text-align: center` 排超过两行的中文

## 断行

```css
/* 避免标点出现在行首 */
line-break: strict;
word-break: normal;
overflow-wrap: break-word;   /* 长英文/URL 才断 */
```

CSS 的 `line-break: strict` 能避免「，」出现在行首（中文排版禁忌）。支持的浏览器有限，但加了没坏处。

## 竖排 / 特殊效果

除非做展示型设计（骨架 D），别用。中文竖排（`writing-mode: vertical-rl`）在普通界面上是灾难。

## 一个最小可用的中文正文样式

```css
.prose {
  max-width: 68ch;
  font-size: 16px;
  line-height: 1.75;
  color: #1f2328;
  letter-spacing: 0.01em;   /* 中文加一点点字距更透气，0.01em 就够 */
  text-align: left;
  text-wrap: pretty;        /* 现代浏览器：避免孤字成行 */
}

.prose p { margin: 0 0 1.2em; }
.prose h2 { font-size: 20px; line-height: 1.4; margin: 2.4em 0 0.8em; font-weight: 600; }
.prose code {
  font-size: 0.9em;
  padding: 0.1em 0.35em;
  border-radius: 4px;
  background: #f6f8fa;
  border: 1px solid #d1d9e0;
}
```

## 常见翻车

| 现象 | 原因 | 修法 |
| --- | --- | --- |
| 中文看起来「糊」 | 用了 `font-weight: 300` 或系统没这个字重 | 改 400 |
| 一段话挤成方块 | 行高 1.5 以下 | 改 1.7 |
| 英文和中文粘在一起 | 没加空格 | 手动加，或用 `text-spacing`（兼容差，别指望） |
| 数字列不对齐 | 没用 `tabular-nums` | 加 |
| 标题黑成一团 | 中文 700 + 小字号 | 字号加大、字重降到 600 |
| 行末标点跑到行首 | 没设 `line-break` | 加 `line-break: strict` |
| 长 URL 撑破布局 | 没有 `overflow-wrap` | 加 `overflow-wrap: break-word` |
