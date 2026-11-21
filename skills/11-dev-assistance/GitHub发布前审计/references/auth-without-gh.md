> 上游参考资料：其中原作者的机器状态、固定数值、DSH 路径与审批习惯不代表当前环境。执行以本目录 SKILL.md、当前项目规则及用户授权为准。

# 没有 gh CLI 怎么发布

本机实测：`gh` 未安装、无 credential helper、无 `GITHUB_TOKEN`。所以下面全部走 `git` + `curl` + 浏览器。

## 一、先确认身份

```bash
git config --global user.name    # 没有就设
git config --global user.email   # 建议用 GitHub 的 noreply：<id>+<user>@users.noreply.github.com
git remote -v
```

`git log --format='%an <%ae>' | sort -u` 看一眼历史里的邮箱——**真实邮箱会永久留在公开提交里**，介意就重写历史或用 noreply 重新提交。

## 二、本机的 TLS 坑（必读）

裸 `git ls-remote https://github.com/...` 会失败：

```
fatal: unable to access '...': schannel: next InitializeSecurityContext failed:
CRYPT_E_NO_REVOCATION_CHECK (0x80092012)
```

原因：Windows schannel 吊销检查连不上 CA 的 CRL 服务器。实测可用的最小修法（只关吊销检查，不关证书校验）：

```bash
git -c http.sslBackend=schannel -c http.schannelCheckRevoke=false ls-remote <url>
```

三种写法都验证过：

| 写法 | 结果 |
| --- | --- |
| `git -c http.sslBackend=schannel -c http.schannelCheckRevoke=false` | ✅ 成功 |
| `GIT_SSL_NO_VERIFY=1`（仍用 schannel） | ✅ 可用，但完全跳过证书校验，不推荐 |
| `git -c http.sslBackend=openssl` | ❌ `SSL certificate OpenSSL verify result: unable to get local issuer certificate (20)` |

要长期免加参数：

```bash
git config --global http.schannelCheckRevoke false
```

（这只影响这台机器；换成 `GIT_SSL_NO_VERIFY` 会连证书都不验，别用。）

`curl` 访问 GitHub API 同理需要 `--ssl-no-revoke`：

```bash
curl --ssl-no-revoke -s "https://api.github.com/repos/<owner>/<repo>"
```

`raw.githubusercontent.com` 在本机**超时不可用**，取文件内容改走 API：

```bash
curl --ssl-no-revoke -s "https://api.github.com/repos/<owner>/<repo>/contents/<path>" \
  | python -c "import sys,json,base64;print(base64.b64decode(json.load(sys.stdin)['content']).decode())"
```

## 三、认证：PAT 走哪里

**铁律：令牌绝不写进 remote URL、不写进 `.git/config`、不回显、不进日志。**

### 方案 A：只在推送那一次用（推荐，零残留）

```bash
git -c credential.helper= push https://<user>:<token>@github.com/<user>/<repo>.git main
```

风险：命令行历史/进程列表会短暂出现令牌。所以更稳的是方案 B。

### 方案 B：临时 credential helper（读完即删）

```bash
export GIT_ASKPASS=/tmp/askpass.sh   # 内容：#!/bin/sh\necho "$GIT_TOKEN"
export GIT_TOKEN=<从文件读取，不 echo>
git push origin main
unset GIT_TOKEN
rm /tmp/askpass.sh
```

### 方案 C：让用户自己在浏览器里 push

最省事也最安全：让用户打开 GitHub Desktop / VS Code 的 Git 面板点推送。技能这边只负责审计和准备。

### 令牌从哪读

用户本机令牌在 `<token-file>`。**读它的时候不要在终端 `cat`**（会进会话记录），用脚本读进变量直接交给 git：

```python
import subprocess, pathlib
tok = pathlib.Path(r"<token-file>").read_text(encoding="utf-8").strip()
subprocess.run(["git", "push", "origin", "main"], env={**os.environ, "GIT_ASKPASS": ...})
```

## 四、建仓库（API）

有 PAT 就能纯命令行建：

```bash
curl --ssl-no-revoke -s -X POST https://api.github.com/user/repos \
  -H "Authorization: Bearer <token>" \
  -H "Accept: application/vnd.github+json" \
  -d '{"name":"<repo>","description":"...","private":false,"has_issues":true,"has_wiki":false,"license_template":"mit"}'
```

没 PAT：让用户在 `https://github.com/new` 点一下，**不要替用户填表**（浏览器自动化在本机不可用，也没有 gh）。

建完立刻确认：`curl --ssl-no-revoke -s https://api.github.com/repos/<owner>/<repo>` 返回 `"private": false` 才算真的公开。

## 五、发布 Release（安装包）

```bash
# 1. 建 tag（打 tag 前确认工作树干净）
git tag -a v1.2.0 -m "v1.2.0"
git push origin v1.2.0

# 2. 建 release
curl --ssl-no-revoke -s -X POST \
  https://api.github.com/repos/<owner>/<repo>/releases \
  -H "Authorization: Bearer <token>" \
  -d '{"tag_name":"v1.2.0","name":"v1.2.0","body":"<变更说明>","draft":false,"prerelease":false}'

# 3. 上传资产（upload_url 里 {?name,label} 要去掉）
curl --ssl-no-revoke -s -X POST \
  "https://uploads.github.com/repos/<owner>/<repo>/releases/<id>/assets?name=<file>" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/octet-stream" \
  --data-binary @"<file>"
```

资产命名：`<app>-<version>-<platform>.<ext>`，例如 `bili-whale-1.2.0-win-x64.exe`。别用 `setup.exe`、`latest.exe` 这种没有版本信息的名字。

上传后回读校验：

```bash
curl --ssl-no-revoke -s https://api.github.com/repos/<owner>/<repo>/releases/latest \
  | python -c "import sys,json;d=json.load(sys.stdin);[print(a['name'],a['size'],a['browser_download_url']) for a in d['assets']]"
```

再 `sha256sum <file>` 对一遍，把 sha256 写进 release 正文和 README 下载表。

## 六、推送前最后三件事

```bash
git status --porcelain          # 必须为空
git log --oneline -5            # 确认没有 "wip" "test" 这种提交
python <skill>/scripts/audit.py .   # 必须 PASS 或 WARN 已确认
```

`audit.py` 报 BLOCK 就不许推 —— 推上去再删，历史里还在。

## 七、万一推错了

| 情况 | 处理 |
| --- | --- |
| 推了含密钥的提交，还没人 clone | `git push --force` 覆盖；然后**立刻在 GitHub 上吊销那个密钥**（历史重写不等于密钥安全） |
| 已经被 clone/fork | 吊销密钥是唯一有效动作；历史重写只是止损 |
| 推了 60 MB 的二进制 | 用 `git filter-repo` 清历史后 force push，或直接删仓库重建（更快） |
| 私有仓库误设公开 | Settings → Danger Zone → Change visibility |

**吊销优先于清理。** 任何密钥一旦进过远程，就当它已经泄漏。
