> 上游参考资料：其中原作者的机器状态、固定数值、DSH 路径与审批习惯不代表当前环境。执行以本目录 SKILL.md、当前项目规则及用户授权为准。

# CI 模板与自动化

`templates/` 下的文件按需拷到项目里。三个模板，各有明确适用条件，不要无脑全上。

## pages.yml —— 静态站点自动部署

适用：纯静态（HTML/CSS/JS）或带构建步骤的前端（Vite / Next / Astro / Vue）。

```yaml
name: Deploy to Pages
on:
  push:
    branches: [main]
  workflow_dispatch:
permissions:
  contents: read
  pages: write
  id-token: write
concurrency:
  group: pages
  cancel-in-progress: false
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm
      - run: npm ci
      - run: npm run build
      - uses: actions/configure-pages@v5
      - uses: actions/upload-pages-artifact@v3
        with:
          path: dist          # ← 改成你的产物目录；纯静态无构建就填 .
  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
```

要点：

- `permissions` 三项缺一不可，少 `pages: write` 会 403。
- `path: dist` 是**上传哪个目录**，不是仓库根。纯静态无构建的项目填 `.`。
- 子路径部署时构建要带 base：Vite `base: '/<repo>/'`，Next `basePath` + `assetPrefix`。忘了就全站 404。
- 首次运行后必须去 Settings → Pages 把 Source 设成 **GitHub Actions**，否则这个 workflow 白跑。

## release.yml —— 打 tag 自动出安装包

适用：Electron / Tauri / 打包成 exe 的桌面工具。

```yaml
name: Release
on:
  push:
    tags: ['v*']
permissions:
  contents: write
jobs:
  build:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 22, cache: npm }
      - run: npm ci
      - run: npm run build
      - run: npm run dist          # electron-builder / tauri build
      - uses: softprops/action-gh-release@v2
        with:
          files: |
            release/*.exe
            release/*.zip
          generate_release_notes: true
```

要点：

- `permissions: contents: write` 必须有，否则传资产 403。
- `generate_release_notes: true` 会自动列 PR，个人项目提交信息不规范时反而更乱 —— 建议手写 body。
- 资产文件名里带版本号（`<app>-<version>-win-x64.exe`），不要用 `setup.exe`。
- 上传前在 workflow 里跑一次 `audit.py` 是个好习惯，但**审计应该在推送前做**，CI 只是兜底。

## pre-commit —— 本地提交前拦截

适用：所有项目。本机已有范式可参考：`<workspace>\b站\dsh-bili-whale\.githooks\pre-commit`。

```bash
#!/bin/sh
# .githooks/pre-commit —— 装法：git config core.hooksPath .githooks
set -e
staged=$(git diff --cached --name-only --diff-filter=ACM)

# 1. 隐私文件名
echo "$staged" | grep -Ei '(^|/)(\.env|.*credential.*|.*token.*|.*令牌.*|.*秘钥.*|id_rsa|\.git-credentials)$' && {
  echo "✗ 暂存区里有隐私文件，先 git rm --cached"; exit 1; } || true

# 2. 大文件
git diff --cached --numstat | while read add del file; do
  size=$(git cat-file -s $(git rev-parse ":$file") 2>/dev/null || echo 0)
  [ "$size" -gt 52428800 ] && { echo "✗ $file 超过 50MB"; exit 1; }
done

# 3. 密钥
git diff --cached -U0 | grep -E '(github_pat_[A-Za-z0-9_]{22,}|gh[pousr]_[A-Za-z0-9]{36}|AKIA[0-9A-Z]{16}|SESSDATA=[A-Za-z0-9%]{25,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)' && {
  echo "✗ 暂存区里有密钥"; exit 1; } || true

echo "✓ pre-commit 通过"
```

**教训（来自 dsh-bili-whale 的真实 bug）**：模式必须锚到文件扩展名或路径边界。曾经用 `whale-(log|night|wake)` 想拦日记文件，结果误拦了源码 `whale-night.mjs`，正确写法是 `whale-night\.json$`。宽泛的模式会把人逼到 `--no-verify`，等于没有 hook。

## 什么时候不要上 CI

- 项目只有一个人、几周才发一次版 —— CI 的维护成本高于收益。
- 构建需要本机才能装的环境（特殊 SDK、许可证）。
- 还没想清楚产物目录 —— 先手动发一次，把步骤记下来，再自动化。

## 一个容易忘的点

`.github/workflows/` 里的 YAML 缩进错一个空格就是 `Invalid workflow file`，而且报错行号经常指向别处。改完先在本地用 `python -c "import yaml,sys;yaml.safe_load(open('.github/workflows/x.yml'))"` 验一遍语法。
