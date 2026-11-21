> 上游参考资料：其中原作者的机器状态、固定数值、DSH 路径与审批习惯不代表当前环境。执行以本目录 SKILL.md、当前项目规则及用户授权为准。

# 技能维护手册

## 技能是怎么被发现的

DSH 只扫这几个根，**只认一层**：

| 优先级 | 根 | 说明 |
| --- | --- | --- |
| 100 | `<项目>/.dsh/skills` | 项目级 |
| 200 | `<项目>/.agents/skills` | 项目级 |
| 300 | 自定义 | 配置里指定 |
| 400 | `~/.dsh/skills` | 用户级（本机新建的技能在这） |
| 500 | `~/.agents/skills` | 用户级（qianwen-* 在这） |

发现规则：

- `<根>/<name>/SKILL.md` ✅
- `<根>/<name>.md` ✅
- `<根>/<a>/<b>/SKILL.md` ❌（嵌套不发现）
- frontmatter 必填 `name`（kebab-case）和 `description`

DSH 自带的 bundled 技能（`office` 系列）在安装目录的 `resources/runtime/office-skills/`，不在上面这些根里，由程序内部注册。

## 目录成本 vs 正文成本

| | 什么时候进上下文 | 多大 |
| --- | --- | --- |
| 目录（name + description） | **每次请求** | 每条最多 500 字，本机 16 个技能 ≈ 6430 字 |
| 正文（SKILL.md 全文） | 只有 `skill()` 加载时 | 本机最大 27977 字（`qianwen-usage`） |

所以：

- 想让**每次请求都便宜** → 停用技能（减少目录条目），或精简 description。
- 想让**单次任务便宜** → 少加载（正文才是大头）。

一次误加载 ≈ 四次全量目录。**选对比停用更值。**

## 停用 / 恢复

```bash
# 看现状
python scripts/park.py

# 预演（默认就是预演，--dry 可省略）
python scripts/park.py qianwen-payment

# 真挪
python scripts/park.py qianwen-payment --go

# 恢复
python scripts/park.py --restore qianwen-payment --go
```

挪到 `<dsh-home>\skills-parked\`（兄弟目录，不在扫描根里）。**内容一个字不动**，随时挪回。

挪完 DSH 会在下一次技能目录刷新时推送新的 catalog，不需要重启。

### 什么该停用

| 判据 | 说明 |
| --- | --- |
| 账本里 3 次以上全是 `useless` | description 写歪了，或技能本身不好用 |
| 账本里用 5 次以上，废用率过半 | 同上 |
| 职责和另一个技能重叠 | 留一个 |
| 装了 30 天，一次没用过 | 但**账本从今天才记**，所以这条要人工判断，不能自动 |

`park.py --all-unused` 只对**账本里有记录**的技能做推荐，没记录的会单独列出来提醒，不会自动停用。

### 什么不该停用

- 刚建的技能（还没机会用）
- 低频但关键的（`qianwen-ops-auth` 可能一年用两次，但那两次没它不行）
- `skill-router` 自己

## 账本

```bash
# 记一条（每次用完技能都记）
python scripts/ledger.py add repo-publish --task "上传工具到 GitHub" --outcome used

# 记一条「用了但没用上」
python scripts/ledger.py add qianwen-payment --task "试着查余额" --outcome useless

# 汇总
python scripts/ledger.py report

# 最近几条
python scripts/ledger.py tail -n 10
```

存在 `~/.dsh/skill-ledger.jsonl`，一行一个 JSON，追加写，坏一行不影响其他行。

**为什么必须自己记**：本机会话日志是 zstd 多帧（`~/.dsh/sessions/**/session.v4.jsonl.zstd`），Node 的 `zstdDecompressSync` 只能解首帧，统计不了历史加载记录。所以账本只能从建立那天起算。

## 新建技能

```
~/.dsh/skills/<name>/
├── SKILL.md           # 必须
├── references/*.md    # 按需，正文里指路
├── scripts/*.py       # 按需，可执行的检查/生成工具
└── templates/*        # 按需，可复制的文件
```

SKILL.md 的 frontmatter：

```yaml
---
name: my-skill          # kebab-case，和目录名一致
description: 一句话说清做什么 + TRIGGER when: … + DO NOT TRIGGER when: …
whenToUse: 可选，补充说明
---
```

**description 是唯一会被模型看到的触发依据。** 写不好就永远不会被选中。要点：

1. 先说**做什么**（一句话，具体）。
2. 列出用户可能说的**原话关键词**（中文口语 + 英文术语都列）。
3. 明确写 `DO NOT TRIGGER when:` —— 这比 TRIGGER 更能防止误加载。
4. 控制在 500 字内（超了会被截断，后面的 DO NOT TRIGGER 就看不见了）。

## 改技能后怎么验证

1. **目录刷新**：改完 SKILL.md，DSH 会推送新的 available-skills 清单。看到清单更新 = frontmatter 合法。
2. **打分验证**：`python scripts/scan.py --task "<用户可能说的话>"`，看目标技能是否排第一。
3. **负例验证**：`python scripts/scan.py --task "<不该触发的话>"`，看它是否**不出现**。
4. **脚本验证**：所有 `scripts/` 下的脚本都要在真实路径上跑一遍，不能只 `--help`。

## 已知坑

| 坑 | 现象 | 处理 |
| --- | --- | --- |
| description 超 500 字 | 尾部被截断，DO NOT TRIGGER 丢失 | 精简，或把 DO NOT 放前面 |
| 目录嵌套一层 | 技能不被发现 | 只能 `<根>/<name>/SKILL.md` |
| 中文名 | `name` 必须 kebab-case 英文 | 用拼音或英文 |
| Windows 控制台 GBK | 脚本输出中文乱码 | 脚本里 `sys.stdout.reconfigure(encoding="utf-8")` |
| 停用后想恢复 | 忘了停在哪 | `park.py` 无参数会列出已停用的 |
| 账本混入坏行 | `report` 跳过那行 | 正常，不会崩 |
