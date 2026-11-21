# WeChat Miniapp Engineering Skill

中文优先的微信小程序工程分析与上线助手，已从原 `wechat-miniapp-engineering-mcp` 迁移为自包含 Codex skill。

这个 skill 不要求普通用户配置 MCP 客户端。它内置一个轻量 CLI，把原 MCP 的 25 个工具、20 个资源、3 个提示词封装成可直接运行的本地能力，适合微信原生小程序、云开发、CloudBase、客户成片展示/私密相册、上线检查和小白友好工程拆解。

## 适合做什么

- 扫描本地微信小程序工程，解释页面、组件、tabBar、云函数、集合和业务模块。
- 从一个产品想法生成小程序工程蓝图、MVP 边界、页面、数据、云函数和上线步骤。
- 输出客户成片展示/私密相册类小程序的业务路线图。
- 做功能影响分析、相关上下文收集、Mermaid 依赖图和图谱统计。
- 生成 CloudBase/小程序上传审核/发布前预检清单。
- 做小程序专项安全快扫，并避免输出原始敏感值。

## 本地安装

从 GitHub 克隆后，将整个 skill 目录复制到 Codex skills 目录即可；不要为了使用本 skill 去配置 MCP 客户端。

```bash
git clone https://github.com/lychee20000105/wechat-miniapp-engineering-skill.git
mkdir -p ~/.codex/skills
cp -R wechat-miniapp-engineering-skill ~/.codex/skills/
```

之后在 Codex 中可以用 `$wechat-miniapp-engineering-skill` 触发。

## 快速验证

```bash
cd wechat-miniapp-engineering-skill
npm run validate
```

`npm run validate` 会依次执行语法检查、smoke test 和 quick_validate，避免漏跑任一验证步骤。

大项目扫描如果超过默认等待时间，可临时设置 `MINIAPP_ENGINEERING_TIMEOUT_MS=60000` 后再运行 CLI。

可单独检查增量索引健康状态：

```bash
npx --no-install miniapp-engineering index-status '{"projectPath":"/absolute/path/to/miniapp"}'
```

`index-status` 默认只读，不写 cache，只汇总文件 hash 变化和图谱缓存状态；需要更新本地 cache 时，显式传 `{"projectPath":"/absolute/path/to/miniapp","writeCache":true}`。

查看全部能力（在 skill 目录内可优先使用 npm binary，也可直接调用脚本）：

```bash
npx --no-install miniapp-engineering list-tools
npx --no-install miniapp-engineering list-resources
npx --no-install miniapp-engineering list-prompts
```

扫描一个小程序项目：

```bash
npx --no-install miniapp-engineering call-tool miniapp_inspect_project '{"projectPath":"/absolute/path/to/miniapp","includeReadme":true}'
npx --no-install miniapp-engineering call-tool miniapp_inspect_project @/absolute/path/to/args.json
```

当参数较长或包含中文时，建议用 `@/absolute/path/to/args.json` 读取本地 JSON 参数文件；`@file` 必须是绝对路径且小于 1 MiB。

做项目地图和安全快扫：

```bash
npx --no-install miniapp-engineering call-tool miniapp_project_map '{"projectPath":"/absolute/path/to/miniapp","format":"markdown","detail_level":"standard"}'
npx --no-install miniapp-engineering call-tool miniapp_security_quick_scan '{"projectPath":"/absolute/path/to/miniapp","maxFindings":80}'
```

## 项目结构

```text
SKILL.md                         # Codex skill 入口
agents/openai.yaml               # Codex UI 元数据
scripts/miniapp_engineering_cli.mjs
references/                      # 能力索引、工作流、安全发布说明
assets/mcp-server/               # 原 MCP 引擎与 demo fixture，作为 bundled engine
```

## 和旧 MCP 仓库的关系

旧 `wechat-miniapp-engineering-mcp` 的引擎、fixture、文档和 smoke test 已保留在 `assets/mcp-server/` 中，用于兼容和溯源。当前推荐路径是本 skill 的 CLI：普通用户运行 `scripts/miniapp_engineering_cli.mjs`，不需要手动写 MCP client 配置。

## 安全边界

- 默认只读扫描明确指定的小程序项目路径。
- 不发布、不部署、不写真实 CloudBase/Tencent 环境。
- 不保存 AppSecret、SecretKey、token、cookie、私钥或真实客户资料。
- 不把私有用户画像、真实日志、cache JSON、本机私密路径、客户素材或真实 AppID 写入公开文档。
- 安全快扫只输出路径、行号、规则、严重级别和修复方向，避免回显原始敏感值。

## License

MIT

## 版本档案 / Release History

本项目后续更新默认保留历史文案，不覆盖原始上传内容。每个有意义的版本都会优先通过以下位置叠加记录：

- GitHub Releases：https://github.com/lychee20000105/wechat-miniapp-engineering-skill/releases
- CHANGELOG.md
- docs/releases/

README 只保留当前版本入口和必要说明；历史版本细节按版本向上叠加，方便像 release 页面一样查看完整演进记录。
