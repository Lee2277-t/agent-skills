> 上游参考资料：其中原作者的机器状态、固定数值、DSH 路径与审批习惯不代表当前环境。执行以本目录 SKILL.md、当前项目规则及用户授权为准。

# 发布执行手册

按顺序走。每一步都有「做完的标志」，没达到就不许进下一步。

## 阶段 0：确认目标

先问清三件事，缺一件就停下来问：

1. **发哪个目录**？（用户说「我的工具」时，`ls` 出来的候选可能不止一个 —— 见 `SKILL.md` 的「先确定发什么」）
2. **仓库名和可见性**？（public / private；免费账号 private 不能开 Pages）
3. **要不要在线版**？（要 → 准备 Pages 或另找托管；不要 → README 里别放演示链接）

做完的标志：能一句话说出「把 `<路径>` 发到 `<owner>/<repo>`，public，带/不带 Pages」。

## 阶段 1：审计（只读，不改任何东西）

```bash
python "<skill-dir>\scripts\audit.py" "<项目路径>"
```

- `exit 0` PASS → 进阶段 2
- `exit 1` WARN → 把 WARN 表格原样贴给用户，逐条问「改还是确认接受」
- `exit 2` BLOCK → **停**。把 BLOCK 表格贴给用户，说清每条为什么要改，等用户修

不要自己动手改用户的代码。审计器只读，修复由用户决定（技能可以给命令，但不擅自 `git rm`）。

做完的标志：`report.md` 已写到项目根（`report.md` 和 `report.json` 两个文件，都由 `--write-report` 生成；**记得把这两个加进 `.gitignore`**），用户看过并说了「可以」。

## 阶段 2：补齐（用户点头后才动）

按需执行，每条都要先说「我要做什么」：

```bash
# 垃圾出索引
git rm -r --cached node_modules dist build __pycache__
# 补 .gitignore（用 templates/gitignore 起）
# 补 LICENSE（用户选许可证，别替他选 AGPL）
# 生成 README 骨架
python "<skill-dir>\scripts\make_readme.py" "<项目路径>" --name "<项目名>"
```

改完**重新审计**，直到 PASS 或只剩用户明确接受的 WARN。

做完的标志：第二次 `audit.py` 输出 PASS（或用户书面接受剩余 WARN）。

## 阶段 3：本地提交

```bash
git add -A
git status --porcelain        # 再看一眼，别把 .publish/ 之类的临时目录加进去
git commit -m "<类型>: <做了什么>"
```

`.publish/` 应该进 `.gitignore`（审计报告本身可能含密钥掩码，但没必要公开）。

做完的标志：`git status --porcelain` 为空。

## 阶段 4：建远程 + 推送

见 `references/auth-without-gh.md`。要点：

- 建仓库前先 `curl --ssl-no-revoke -s https://api.github.com/repos/<owner>/<repo>` 确认**不存在**（撞名会 422）
- 推送用一次性的凭证传递方式，令牌不落盘
- 推完 `git ls-remote origin` 确认远程有 `refs/heads/main`

做完的标志：远程分支存在，且 `curl` 拿到的 `private` 字段符合预期。

## 阶段 5：Release（有安装包才做）

见 `references/auth-without-gh.md` 第五节。要点：

- 先 `sha256sum` 记下校验值
- 资产名带版本和平台
- 传完回读 `releases/latest`，核对 `size` 和本地文件一致

做完的标志：`releases/latest` 里能看到资产，README 下载表的链接点得开。

## 阶段 6：Pages（有在线版才做）

1. `.github/workflows/pages.yml`（用 `templates/pages.yml`）
2. Settings → Pages → Source: GitHub Actions
3. 等 Actions 绿，`curl -I https://<user>.github.io/<repo>/` 应返回 200
4. **打开页面看一眼**（Chrome headless 截图），确认不是白屏、不是 404、资源没丢

做完的标志：截图里页面正常渲染。

## 阶段 7：回读复核（必做）

逐条核对，全绿才算交付：

| 检查 | 命令 / 动作 |
| --- | --- |
| 远程文件清单 | `curl --ssl-no-revoke -s "https://api.github.com/repos/<owner>/<repo>/contents/"` |
| 没有敏感文件 | 在远程清单里搜 `.env` `token` `credential` `秘钥` `令牌` |
| README 首屏 | 浏览器打开仓库首页，截图看有没有截图/下载链接 |
| Pages 可访问 | `curl -I` 200 + 截图 |
| Release 资产 | `releases/latest` 里 size 对得上 |
| 仓库可见性 | `private` 字段 |

## 失败怎么报

| 现象 | 大概率原因 | 下一步 |
| --- | --- | --- |
| `CRYPT_E_NO_REVOCATION_CHECK` | schannel 吊销检查 | 加 `-c http.schannelCheckRevoke=false` |
| `Authentication failed` | 令牌过期/无 repo 权限 | 让用户重发 PAT，勾 `repo` |
| `remote: Repository not found` | 仓库没建 / 名字错 / 无权限 | 先 `curl` 查存在性 |
| `422 already exists` | 撞名 | 换名，别硬建 |
| Pages 404 | 源分支/目录配错，或子路径问题 | 见 `readme-and-pages.md` 的子路径坑 |
| Actions 红 | 缺依赖锁文件 / Node 版本 | 看日志第一行报错，别猜 |

失败就**停在这一步**，把原始错误贴给用户。不要换姿势重试三次以上。
