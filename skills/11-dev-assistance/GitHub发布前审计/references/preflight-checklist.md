> 上游参考资料：其中原作者的机器状态、固定数值、DSH 路径与审批习惯不代表当前环境。执行以本目录 SKILL.md、当前项目规则及用户授权为准。

# 上传前的合格线

审计器 `scripts/audit.py` 就按这份清单判定。三档：`BLOCK`（禁止上传）、`WARN`（需逐条确认）、`PASS`。

## BLOCK — 出现就必须停下

| 项 | 判据 | 为什么是硬阻断 |
| --- | --- | --- |
| 硬编码密钥 | 命中 `secret-patterns.md` 任一正则且不是占位符 | 一旦推到公开仓库，GitHub 的爬虫几秒内就会扫到；改代码删掉也还在历史里 |
| 隐私/凭据文件 | 文件名命中 `.env`、`*credential*`、`*token*`、`*令牌*`、`*秘钥*`、`*.pem`、`*.key`、`id_rsa`、`.git-credentials`、`whale-diary*.md` | 这类文件的存在本身就是泄漏 |
| 单文件 > 50 MB | `stat().st_size` | GitHub 单文件硬限 100 MB、仓库建议 < 1 GB；大文件应进 Release 资产 |
| 历史里出现过密钥 | `git log --all -p -40` 命中密钥正则 | **最容易被忽略的一条**：现在删了文件，历史里还在 |
| 历史里出现过隐私文件 | `git log --all --name-only` 命中文件名黑名单 | 同上 |

处理历史泄漏：

```bash
# 只有本地仓库、还没推过：直接重建历史
git checkout --orphan clean-main && git add -A && git commit -m "init"
git branch -D main && git branch -m main

# 已经推过：用 git filter-repo（本机没装，需用户同意后 pip install）
git filter-repo --path <敏感文件> --invert-paths
# 之后必须 force push，并提醒用户：任何 clone 过的人手上仍有旧历史
```

## WARN — 逐条确认才能继续

| 项 | 判据 | 处理建议 |
| --- | --- | --- |
| 垃圾被跟踪 | `node_modules/` `dist/` `build/` `__pycache__/` `.venv/` `coverage/` `*.log` `*.db` `*.pyc` | `git rm -r --cached <dir>` + 写进 `.gitignore` |
| 绝对路径含用户名 | `C:\Users\<name>` / `/home/<name>` | 换成 `~`、环境变量或相对路径 |
| 联系方式 | 邮箱、中国大陆手机号、18 位身份证 | 换 `noreply@` 或删掉；公开仓库会招垃圾邮件 |
| 缺 README | 没有 `README*` | 用 `scripts/make_readme.py` 生成骨架 |
| 缺 LICENSE | 没有 `LICENSE*` | 让用户选（MIT / Apache-2.0 / AGPL）；没许可证 = 别人不能用 |
| 缺 .gitignore | 没有 `.gitignore` | 从 `templates/gitignore` 起 |
| README 有占位符 | `TODO` `TBD` `FIXME` `待补充` `Lorem ipsum` | 补完再发；占位符会让仓库显得半成品 |
| 总量偏大 | 会进仓库 > 200 MB | 产物挪 Release，历史里的大文件用 LFS |

## 二进制与安装包怎么办

`.exe` `.msi` `.dmg` `.zip` 出现在**源码树**里是 WARN（该进 Release）；出现在 `release/` 或 `dist/assets/` 下视为 Release 资产，不告警。正确做法：

- 源码仓库只放源码 + 构建脚本。
- 安装包传到 **Releases**，文件名 `<app>-<version>-<platform>.<ext>`，正文列 sha256。
- 想让人 `winget install` 就再提一个 winget-pkgs PR（可选，别默认做）。

## 在线网页怎么办

两条路，按项目形态选：

| 形态 | 做法 |
| --- | --- |
| 纯静态（HTML/CSS/JS，无后端） | GitHub Pages：`Settings → Pages → Source: GitHub Actions`，用 `templates/pages.yml` |
| 有后端 / 需要 API key | Pages 只能放静态前端，后端另找地方（`qianwenai-deploy` 或任意 PaaS）；README 里明确写「网页版是演示，完整功能需本地安装」 |

Pages 的坑：仓库名不是 `<user>.github.io` 时，站点路径是 `https://<user>.github.io/<repo>/`，前端里所有绝对路径 `/assets/...` 都会 404 —— 必须用相对路径或在构建时注入 `base`。

## 审计器没覆盖的，人工看一眼

- 截图/录屏里有没有聊天窗口、邮箱、真名、桌面其他窗口。
- 配置文件里的内网 IP、公司域名、数据库名。
- `package.json` 的 `author`/`repository` 字段是不是别人的。
- 提交作者信息：`git log --format='%an <%ae>'` 里是不是有真实邮箱（可以改 `user.email` 用 GitHub 的 noreply 地址）。
