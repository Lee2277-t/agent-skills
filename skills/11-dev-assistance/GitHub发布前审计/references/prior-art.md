> 上游参考资料：其中原作者的机器状态、固定数值、DSH 路径与审批习惯不代表当前环境。执行以本目录 SKILL.md、当前项目规则及用户授权为准。

# 上游调研：GitHub 上已有的同类技能

调研方式：`api.github.com` 搜索 + 直接读 `SKILL.md`（`raw.githubusercontent.com` 在本机不可达，改走 contents API）。

## 已存在的相关技能

| 仓库 / 技能 | 它做什么 | 我们借了什么 | 我们没借什么 |
| --- | --- | --- | --- |
| `joeseesun/qiaomu-...`（发布类） | 从本地到 GitHub 的一键发布流程 | 「先审计再上传」的两段式结构 | 它依赖 `gh` CLI，本机没有 |
| `anthropics/skills` 的 `brand-guidelines` / `artifacts-builder` | 产物规范与文档规范 | README 首屏必须给证据（截图/链接）的思路 | 与发布无关 |
| `github/awesome-copilot` 里的 `release` 类 prompt | Release notes 生成 | 「资产命名带版本和平台」 | 它只管文案不管安全 |
| 各类 `git-workflow` 技能 | commit message 规范 | 类型前缀（feat/fix/docs/chore） | 我们不做完整 git 工作流教学 |
| `gitleaks` / `detect-secrets` | 密钥扫描 | 正则表的设计（前缀锚定、长度放宽） | 需要装二进制，本机没有；改用零依赖 Python |

## 结论：为什么还要自己写

现有技能分两类，都不合用：

1. **重度依赖 `gh` CLI**：本机没装，装了也要 `gh auth login` 走浏览器。技能必须能在「只有 git + curl」的环境跑。
2. **只管流程不管安全**：它们假设你已经在 `.gitignore` 里排干净了。而用户真正的痛点是「我怕把没用的文件和隐私信息传上去」—— 所以审计必须是**第一步、硬阻断、可复现**，不能是「记得检查一下」。

所以我们做的是：**一个只读审计器 + 三档判定 + 一套在无 gh 环境可执行的发布手册**。审计器是核心，文档是配套。

## 可以借鉴但没做的

- 用 `trufflehog` 做熵检测（抓无格式密钥）：本机没装，且误报率高，暂不做。
- 自动生成 Release notes（`conventional-changelog`）：价值不大，用户写一句「修了什么」更清楚。
- winget / Homebrew 分发：属于「发布之后」，且需要额外 PR 流程，不默认做。用户要时再提。
