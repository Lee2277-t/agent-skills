> 上游参考资料：其中原作者的机器状态、固定数值、DSH 路径与审批习惯不代表当前环境。执行以本目录 SKILL.md、当前项目规则及用户授权为准。

# 密钥正则表

`scripts/audit.py` 里的 `SECRET_PATTERNS` 就是这份表的实现，改一处必须改两处。

## 表

| code | 正则 | 覆盖什么 | 备注 |
| --- | --- | --- | --- |
| `github_pat` | `github_pat_[A-Za-z0-9_]{22,}` | GitHub 细粒度 PAT | 前缀 `github_pat_` 后面是 82 位 base62，长度放宽到 22 是为了抓截断的 |
| `github_tok` | `\bgh[pousr]_[A-Za-z0-9]{36}\b` | 经典 GitHub token（`ghp_` `gho_` `ghu_` `ghs_` `ghr_`） | 固定 36 位 |
| `aws_key` | `\bAKIA[0-9A-Z]{16}\b` | AWS Access Key ID | 密钥本身抓不到，但 ID 泄漏 = 账号暴露 |
| `private_key` | `-----BEGIN [A-Z ]*PRIVATE KEY-----` | PEM 私钥 | 同时覆盖 RSA/EC/OPENSSH |
| `bili_sessdata` | `SESSDATA=[A-Za-z0-9%]{25,}` | B 站登录 cookie | 本机场景专用；`SESSDATA=` 后短串是文档示例，放过 |
| `bili_jct` | `bili_jct=[0-9a-f]{28,}` | B 站 CSRF token | 固定 32 位 hex，放宽到 28 |
| `bearer` | `Bearer\s+[A-Za-z0-9._\-]{20,}` | HTTP Authorization 头 | 覆盖 JWT 与长 token |
| `generic_assign` | `(?i)\b(api[_-]?key\|apikey\|secret\|token\|passwd\|password\|access[_-]?key)\b\s*[:=]\s*["'][^"'\s]{16,}["']` | 硬编码的赋值 | 误报最多的一条，靠占位符白名单压 |
| `sk_key` | `\bsk-[A-Za-z0-9]{20,}\b` | OpenAI / Anthropic 风格 | |

## 占位符白名单（命中就放过）

```
${   {{   <ALLCAPS>   your_   xxx+   ...   placeholder   example   redacted
change_me   dummy   fake   test_key   env[   process.env   os.environ
```

同时检查命中位置**前 40 个字符**——`const token = "..."` 这种写法里占位符往往在等号左边。

## 为什么不用现成工具

本机实测：`gitleaks` / `trufflehog` / `detect-secrets` 全部未安装，装它们要么需要联网拉二进制、要么要 pip。一个纯正则的 Python 脚本零依赖、可审计、改起来快，对「个人项目发布前扫一遍」这个量级够用。

代价：抓不到高熵随机串（没有校验和、没有格式的密钥）。所以 `preflight-checklist.md` 末尾那几条人工检查不能省。

## 误报怎么处理

1. 先确认：把命中的值 `mask()` 之后看前后 6/4 位，能对上你认识的密钥就是真泄漏。
2. 确实是示例值（文档里的 `sk-xxxxxxxx`）：把值改成更明显的占位符，别去改正则。
3. 确实需要写进仓库的（比如公开的 demo key）：在 `PLACEHOLDER_RE` 里加词，或在该行加 `# nosecret` 注释并在脚本里支持跳过——**默认不支持注释跳过**，避免变成绕过口子。

## 扫描范围与代价

- 只扫文本扩展名（`TEXT_EXTS`），跳过图片/压缩包/二进制。
- 单文件 > 2 MB 跳过内容扫描（仍参与体积检查）。
- 默认最多扫 400 个文件，超了会报 `scan-truncated` WARN——大仓库请分批或调 `--limit`。
- 历史扫描只取最近 40 个提交（`-40`），更早的靠 `git log --all -p | grep` 手工兜底。
