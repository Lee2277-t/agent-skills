> 上游参考资料：其中原作者的机器状态、固定数值、DSH 路径与审批习惯不代表当前环境。执行以本目录 SKILL.md、当前项目规则及用户授权为准。

# README 与 Pages：让别人一眼看懂、一键能用

README 不是文档，是**第一屏的销售页**。陌生人给你 15 秒。

## 结构模板（顺序别换）

```markdown
# <项目名>

一句话说清这是什么（≤ 20 字，不要形容词堆砌）

![截图](docs/screenshot.png)

<p>
  <a href="https://<user>.github.io/<repo>/"><img alt="在线试用" src="..."></a>
  <a href="https://github.com/<user>/<repo>/releases/latest"><img alt="下载" src="..."></a>
</p>

## 这是什么
3–5 行。解决什么问题、给谁用、怎么用（文字即可，不要长段背景）。

## 快速开始
### 在线版
直接点上面按钮。功能限制：<写清楚，别让人踩坑>

### 本地版
| 平台 | 下载 | 大小 | 校验 |
| --- | --- | --- | --- |
| Windows 10/11 x64 | [v1.2.0 Setup.exe](...) | 84 MB | `sha256: ab12…` |
| macOS (Apple Silicon) | [v1.2.0 .dmg](...) | 92 MB | `sha256: cd34…` |
| Linux x64 | [v1.2.0 .AppImage](...) | 78 MB | `sha256: ef56…` |

## 截图
2–4 张，每张下面一行说明它展示了什么功能。

## 用法
最小可用示例（命令或点击步骤），能复制粘贴就跑。

## 常见问题
3–5 条真实会被问到的。

## 开发
```bash
git clone ...
cd ...
<install>
<dev>
```

## 许可
MIT，见 [LICENSE](LICENSE)。
```

## 硬指标（审计器会查）

| 项 | 要求 |
| --- | --- |
| 首屏有截图 | 仓库根或 `docs/` 下有 `.png`/`.gif`/`.webp`，README 里引用 |
| 有在线/下载入口 | 至少一个可点链接：Pages 地址或 Releases 地址 |
| 无占位符 | `TODO` `TBD` `FIXME` `待补充` `Lorem ipsum` 一个都不许有 |
| 徽章 ≤ 4 | 多了就是噪音；只留构建状态、License、下载量这类真有信息的 |
| 下载表四列 | 平台 / 链接 / 大小 / sha256；缺一列别人不敢下 |
| 语言 | 中文项目中文 README，需要国际曝光再补 `README.en.md` 并在顶部互链 |

## 截图怎么拍

本机没有 playwright，用 Chrome headless（**`--screenshot` 路径必须用正斜杠**，反斜杠会被吃掉并报 `拒绝访问 (0x5)`）：

```bash
"/c/Program Files/Google/Chrome/Application/chrome.exe" \
  --headless=new --disable-gpu \
  --screenshot="%USERPROFILE%/repo/docs/screenshot.png" \
  --window-size=1280,800 \
  "file:///%USERPROFILE%/repo/index.html"
```

窗口宽度用 1280（GitHub README 正文约 880px，1280 截图缩放后仍清晰）。深色模式界面另拍一张，README 里用 `<picture>` 切换。

GIF 用 Windows 自带 `Snipping Tool` 录屏，或用 `ffmpeg` 从 mp4 转：

```bash
ffmpeg -i demo.mp4 -vf "fps=12,scale=800:-1:flags=lanczos" -loop 0 demo.gif
```

GIF 控制在 3 MB 内，否则 README 加载卡。

## GitHub Pages 三种源

| 源 | 适合 | 配置 |
| --- | --- | --- |
| GitHub Actions | 需要构建（Vite/Next/Astro） | `templates/pages.yml` 放进 `.github/workflows/` |
| Deploy from a branch | 纯静态、无构建 | Settings → Pages → Branch: `main` / `/docs` 或 `/` |
| 自定义 | 需要 404、重定向 | 仓库根加 `404.html` |

### 子路径的坑（最常见的 Pages 事故）

仓库名不是 `<user>.github.io` 时，站点在 `https://<user>.github.io/<repo>/` 下：

- HTML 里 `/assets/app.js` → 404，必须是 `./assets/app.js` 或 `assets/app.js`
- Vite：`base: '/<repo>/'`；Next：`basePath: '/<repo>'` + `assetPrefix`
- SPA 路由：Pages 不支持 rewrite，需要 `404.html` 做 fallback（把 `index.html` 复制成 `404.html`）
- 用 Actions 部署时记得上传 `dist` 而不是仓库根

### 私有仓库 + Pages

免费账号私有仓库不能开 Pages（Pro 可以）。要免费公开，仓库必须 public —— 这也是为什么上传前的审计不能省。

## 一个反例

```
# My Awesome Tool 🚀
这是一个基于 AI 的强大的革命性的工具，它可以...
（下面 40 行功能介绍，没有截图，没有下载链接，最后一行：TODO）
```

问题：形容词零信息、无截图、无入口、有 TODO。陌生人 3 秒关掉。

## 一个好例子的骨架

```
# bili-whale
让一个 AI 每天自己刷 B 站、写日记、只把最值得的 3 条分享给你。

[截图：日记页 + 设置页并排]

在线试用 · 下载 Windows 版

## 这是什么
...（3 行）

## 快速开始
（两张表：在线版限制 / 本地版下载）

## 它每天做什么
（编号列表 6 步，每步一行）

## 常见问题
（会不会乱发评论？—— 默认全 dry-run，写操作要 --go 才发）
```
