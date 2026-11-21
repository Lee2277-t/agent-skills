---
name: free-bing-translation-pipeline
description: "排查或维护已有的免 Key 在线翻译链路，检查分片、缓存、降级与返回完整性。包含历史非官方接口经验，运行前确认可用性与文本外发范围；不承诺持续免费或稳定，也不用于离线保密模式。"
---

# 免 Key 免费翻译通道

## Overview

历史免 Key 在线翻译链路（当前可用性、额度与服务条款需另行核对），三级通道：**Edge 免凭据接口**（最快、无需抓页面凭据）→ 微软网页翻译接口 `ttranslatev3` → MyMemory 兜底，配好分片、批量、熔断、缓存四件套。本文只讲这套链路里**不写下来一定会踩**的约束和数字。

历史参考实现（不随本技能提供、不保证当前存在）：`<project-root>/translator/core/translator.py`（tkinter 翻译工具在用，`EdgeEngine` / `BingEngine` / `MyMemoryEngine` 三级降级 + `_batch_pass` 批量回退）。本 Skill 自带的 `scripts/free_translate.py` 是可独立运行的同一份协议（不含 Edge 通道）。

## 适用边界

- **不要用于涉密/保密文档。** 正文会发到第三方服务器，且对方会留日志。涉密场景是离线模型（CTranslate2 + OPUS-MT / NLLB）的地盘。
- 这是**非官方接口**，微软随时可改页面结构或参数。失效特征与降级见「失效排查」，不要当成稳定依赖写进对外 SLA。
- MyMemory 是对社区翻译记忆做统计的引擎，质量明显低于主通道，只作为"别整体失败"的兜底，结果需人工复核。
- 文本预过滤（哪些段落该翻、URL/邮箱/版本号跳过、标题词条表）属于调用方的事，本 Skill 只管传输层与缓存。

## 关键数字

| 项 | 值 | 记不住会怎样 |
|---|---|---|
| Edge 单段上限 | 4000 字符（实测 10k+ 也收，但别赌） | 超长被截断 |
| Edge 批量上限 | 6000 字符 **且** 40 段 | 500 段会被服务器**掐断连接**（不是报错） |
| 主通道（网页接口）单段上限 | 900 字符 | 超长直接 HTTP 400 |
| 兜底通道单段上限 | 450 字符 | 超长被截断，译文缺尾 |
| 网页接口批量上限 | 820 字符 **且** 10 段 | 超一项即失去批量收益（逐段请求） |
| 每段 sentinel 预留 | 28 字符（仅网页接口需要） | 打包后总长越界，整批退回逐段 |
| token 主动续期 | 2400 秒（仅网页接口） | 卡在 40 分钟后开始 401/返回异常 |
| 兜底段间限速 | 0.08 秒 | 连发触发额度限流 |
| 熔断阈值 | 单段连续 3 次 / 批量连续 2 次（每个通道各自计数） | 主通道挂了还逐段硬撞 |

实测吞吐对比（同一批 32 段，冷缓存）：**Edge 2.0 秒**，网页接口 20～28 秒，差约 10 倍。能走 Edge 就别走网页接口。

## 通道一 · Edge 免凭据接口（优先）

```
POST https://edge.microsoft.com/translate/translatetext?from=&to=zh-Hans&isEnterpriseClient=false
Content-Type: application/json
body: ["段落1", "段落2", ...]          ← JSON 字符串数组，不是对象数组
```

- **不需要抓页面、不需要 token/cookie**，省掉网页接口那套 IG/data-iid/AbusePreventionHelper 凭据流程，也就没有 40 分钟续期和精简页问题。
- `from=` 只能留空（自动判定，逐段独立判定，混合语种一批过去没问题）或填 **ISO 码**；填 `english`、`auto`、`auto-detect` 一律 400。
- body 必须是**字符串数组**。传 `[{"text": "..."}]` 会 400（服务端要 `System.String[]`）。
- 响应是**与输入等长的数组**，每段取 `payload[i]["translations"][0]["text"]`；`detectedLanguage.language` 可拿来做语种校验。
- 校验四条，任一不满足整批降级到下一通道：① 返回是 list；② 长度 == 输入段数；③ 每段 `text` 非空；④ 没有把原文整行回显（见「回显检测」）。
- 长段用 `split_for_api(text, 4000)` 切片后**按顺序**发，结果 `"".join()` 拼接。批量时若某段 > 4000，单独走 `translate()`，别混进数组（混进去位置会错位）。
- 用 `http.client.HTTPSConnection` 保持 keep-alive；任何异常先关连接再重试 1 次（间隔 0.6 秒），第二次仍失败即整批降级。

## 通道二 · 微软网页翻译接口

### 1. 取凭据（每 40 分钟一次）

GET `{host}/translator`，从返回的 HTML 里正则抓三样：

```python
ig = re.search(r'IG:"([^"]+)"', page)                       # 会话 GUID
iid = re.search(r'data-iid="([^"]+)"', page)                 # 组件实例 id
info = re.search(r"params_AbusePreventionHelper\s*=\s*(\[[^\]]+\])", page)
values = json.loads(info.group(1))   # values[0] = key(时间戳), values[1] = token
```

任一为空 → 抛"凭据解析失败"。**这个报错九成不是正则写错，而是页面被降级成精简版**（见下条）。

抓取页必须带完整浏览器头，`User-Agent` 用真实 Chrome/Edge 串，并带 `Accept`、`Accept-Language`、`Upgrade-Insecure-Requests: 1`。UA 过于简陋（或库里默认 UA）时服务器返回不含上述三变量的精简页，症状正是凭据解析失败。用 `urllib.request` + `HTTPCookieProcessor` 起一个新 cookie jar，**页面请求拿到的 cookie 要拼成 `Cookie` 头带到接口请求上**，缺 cookie 会 400。

两个 host 轮换（`https://cn.bing.com`、`https://www.bing.com`），失败即换下一个，并把 `host_index` 记住，下次从成功的那个开始。

### 2. 调接口

```
POST {host}/ttranslatev3?isVertical=1&IG={ig}&IID={iid}
body: fromLang=auto-detect & to=<目标语> & text=<一段文本> & token= & key=
```

必需请求头：`Content-Type: application/x-www-form-urlencoded; charset=UTF-8`、`Referer: {host}/translator`、`Origin: {host}`、`X-Requested-With: XMLHttpRequest`、`Accept-Encoding: identity`、`Cookie: <抓取页 cookie>`。

响应取 `payload[0]["translations"][0]["text"]`，空文本按失败处理（不要静默返回空串）。

**连接复用**：用 `http.client.HTTPSConnection` 保持 keep-alive，逐段请求走同一条 socket；`requests`/`urllib` 每次新建连接会明显拖慢批量。host 变了必须重建连接。

**重定向要当失败处理**：收到 301/302/303/307/308 说明被切到了另一个 host，此时凭据已属于旧 host，要立刻 `token = ""` 并关连接，重取凭据；直接跟随重定向会拿旧 token 撞 401。

单请求失败重试 1 次，间隔 0.8 秒，重试前先 `refresh()` 重新取凭据。

### 3. 批量协议（省时间的关键，也是最脆的一环）

≤10 段且总长 ≤820 字符时，把多段拼成一次请求：

```python
marker = secrets.token_hex(3)          # 随机，防与正文冲突
combined = texts[0]
for i, t in enumerate(texts[1:], 1):
    combined += f"\n[[[SEG_{marker}_{i}]]]\n{t}"
```

回包用 `r"\s*\[\[\[SEG_<marker>_(\d+)\]\]\]\s*"` 找分隔符切回。**四条校验，任一不满足就整批退回逐段翻译**（这是必须有的兜底，模型偶尔会吃掉、重复或改写 sentinel）：

1. 匹配数量 == 分隔符数量；
2. 序号必须严格 1,2,3… 递增（乱序说明段落被重排，不能按位置切）；
3. 切出的段数 == 输入段数；
4. 任何一段为空也算失败。

sentinel 一定用随机串，别写死 `"<<<1>>>"`：正文里出现同串会切错且切错是静默的。

打包时给每个分隔符预留 28 字符，单段自身就 >820 的直接单独成批。

## 通道三 · MyMemory 兜底

`GET https://api.mymemory.translated.net/get?q=<chunk>&langpair=<src>|<tgt>`，450 字符一片，结果必须 `html.unescape`。

**它不认 `auto-detect`**，源语种要自己按字形判：假名→ja、谚文→ko、西里尔→ru、阿拉伯→ar、泰文→th、天城→hi、希腊→el，其余按 en。判错语种的结果比不译更糟。

额度耗尽**不看 HTTP 状态**：`responseStatus != 200`，或 `translatedText` 里出现 `MYMEMORY WARNING` / `QUOTA` 就算失败（限流时它返回 200 + 警告文案，不检测会把警告当译文存进缓存）。每段 sleep 0.08 秒。同一台机器当天反复测很容易吃到 HTTP 429，那是额度，不是代码坏了。

## 回显检测（段数校验抓不到的那类错）

批量接口的四条校验只保证「段数对、非空」，但网页接口带 sentinel 打包时会把**原文单独占一行、译文写在旁边**整段吐回来（`The future of AI…\n人工智能的未来`）。数量对、内容错，缓存里就存进了一条脏译文。必须再加一条：

```python
def _echoes_source(source: str, translated: str) -> bool:
    head, _, tail = translated.partition("\n")
    if tail.strip() and head.strip().lower() == normalize_source(source).lower():
        return True                       # 首行是原文
    head, _, tail = translated.rpartition("\n")
    return bool(head.strip()) and tail.strip().lower() == normalize_source(source).lower()
```

命中即**整批判失败**并降级，别只把那一行删掉——一处的 framing 泄漏说明整批都不可信。

## 熔断与降级

- `preflight()` 用一句探针（`"Hello, how are you?"`）**按通道顺序**定链路：Edge 通 → 全程 Edge；Edge 不通 → 探网页接口，通了就置 `edge_disabled = True`；再不通 → 探 MyMemory，通则置 `edge_disabled = bing_disabled = True`；三个都不通直接抛错，别进主流程。
- 运行中：每个通道**各自**计数，单段连续 3 次 或 批量连续 2 次失败 → 置该通道的 `*_disabled`，本批和后续内容顺位降到下一通道。批量降级用 `_batch_pass(indices, …, engine, name, limits)` 返回「没处理的 index 列表」，下一通道拿同一批段落重试，最后剩下的才逐段走 `_translate_one`（它内部再按 Edge → 网页 → MyMemory 顺序试）。
- 失败段**保留原文**并计入 `failed_count`，不要让整篇文档挂掉；失败日志限流（前 5 条 + 每 25 条），否则 1000 段会刷 1000 行。
- 缓存写入要带上当次**实际使用**的引擎名，不是配置里写的引擎名。

## 缓存

```sql
CREATE TABLE IF NOT EXISTS translations (key TEXT PRIMARY KEY, translated TEXT NOT NULL, created_at INTEGER NOT NULL)
```

key = `sha256(f"{engine}\0{target_lang}\0{normalized_text}")`。**engine 必须在 key 里**：三个通道的结果不等价，若只用文本哈希，一旦某次降级走了兜底，低质量译文会永久污染主通道的命中。`target_lang` 同理。

**查缓存的顺序 ≠ 通道是否活着**：按质量顺序 `edge → bing → mymemory` 取第一个命中，通道被熔断也照样复用已存的高质量译文（省请求、结果更好）。写的时候永远用当次实际引擎名。

内存 dict 做一层，sqlite 做持久层；落盘失败（目录不存在、文件被别的进程占用）时静默退回纯内存并把连接置 None，不要让翻译因缓存写不进去而整体失败。文本入 key 前先归一化（NBSP→空格、删零宽空格、strip），否则同一句在 docx 与 PDF 里会算成两条。

## 预探测时机（最容易白等的一处）

`preflight()` 只应在**确实存在待翻段落**时由主流程内部触发：

```python
if pending:                       # 缓存/词条已过滤完
    if not self._preflighted:
        self.preflight()
```

若在任务开头手动 `preflight()`，即使全部段落都命中缓存，也要为一句话去抓页面 + 取凭据 + 发探针，实测白等十几秒；把 preflight 放在 `if pending:` 里之后，26 段全命中的任务耗时 0.00 秒、完全不产生网络请求（脚本实测 `preflighted = False`）。同理不要为"提前知道通不通"而额外预调用。

## OCR 缺空格的前置修复

RapidOCR 一类识别器常把英文单词间空格吃掉（`climatemodelanalysis`），直接把这种串丢给翻译会得到乱译。翻译前先重切词：

```python
if wordninja is None: return text                    # 可选依赖，缺了就原样返回
def repair(match):
    token = match.group(0)
    if len(token) < 4 and not re.search(r"[a-z][A-Z]", token): return token
    parts = wordninja.split(token)
    return " ".join(parts) if len(parts) > 1 else token
return re.sub(r"[A-Za-z]{2,}", repair, text)
```

两个细节：`len(parts) > 1` 才替换，否则短词会被拆碎；阈值只放开长词和 camelCase，避免把 `iOS`、`B2B` 这类专有写法拆散。

## 失效排查

| 症状 | 根因 | 处理 |
|---|---|---|
| Edge 接口 400 | body 传成对象数组、`from=` 填了 `english`/`auto` | body 用字符串数组，`from=` 留空或填 ISO 码 |
| Edge 请求连接被掐断（无状态码） | 单请求段数太多（实测 500 段会断） | 批量上限压到 40 段 / 6000 字符 |
| 凭据解析失败（三正则有一个为空） | UA/头不完整拿到精简页；或页面变量真的改名了 | 先补全浏览器头重试；仍失败即打开 `/translator` 人工核对变量名，改正则 |
| HTTP 400（网页接口） | 缺 cookie 头、超 900 字符、Content-Type 不对 | 逐项查这三条，顺序按经验最可能 |
| 401 / 返回格式异常（非 list） | token 过期或被风控 | `refresh()` 换 host 重来；连续出现就熔断到下一通道 |
| 意外重定向 | 被切到另一 host | 作废 token、关连接（见上） |
| 兜底返回 200 但是警告文案 | 额度耗尽 | 判文案而非状态码 |
| 兜底直接 HTTP 429 | 当天额度用光 | 属外部限制，别改代码；换时段或换机复测 |
| 批量结果段数对不上 | sentinel 被改写 | 已有四条校验，自动回退逐段；若高频回退说明正文里含类似串，加长随机串 |
| 译文里混着原文一整行 | 批量 framing 泄漏 | 加「回显检测」，整批降级 |
| 译文拼接处缺/多空格 | 分片结果用 `" "` join | 分片结果必须 `"".join()` |
| 缓存命中量异常偏低 | 入 key 前没归一化 | 统一走 `normalize_source` |

## 验证清单

按顺序跑，每步都要有明确输出（`scripts/free_translate.py`，实测通过）：

1. `python scripts/free_translate.py --probe` → 打印 `bing channel ready` 与成功 host，退出码 0。（脚本未含 Edge 通道；项目实现里探针应先命中 Edge 并打印「已连接 Edge 免费翻译通道」。）
2. `python scripts/free_translate.py --text "Chapter 1. ..." --text "..." --text "..."`（3 段，够一次批量）→ 3 行译文 + `translated 3, cache hits 0, failed 0`。
3. 带 `--cache <path>` 跑完后**立刻重跑同一命令** → `cache hits 3`、耗时 0.00 秒、无网络请求日志。这一步同时验证缓存 key 正确（见下）。
4. `--engine mymemory` 强走兜底跑同一段 → 结果与主通道不同，且再次用默认引擎跑时**不应**命中上一步的缓存（证明 key 带引擎有效）。项目实现里同理：把 `edge_disabled=True` 冷缓存跑一遍，缓存里应全是 `bing` 键。
5. 超长文本（>900 字符一段）→ 自动分片、译文完整，验证 `split_for_api` 与 `"".join()`。Edge 通道用 >4000 字符一段复测同样的拼接。
6. 混合语种一批（英/法/德/俄各一句丢进同一个数组）→ 每句都出中文，验证 `from=` 留空的逐段自动判定没串味。
7. 断网（拔网线或 hosts 屏蔽）→ 明确报错而不是无限重试，且失败段保留原文。

## Resources

- `scripts/free_translate.py` — 纯标准库实现，可 CLI 可 import（`BingEngine` / `MyMemoryEngine` / `TranslationCache` / `Translator` / `split_for_api` / `make_batches`）。译文走 stdout，日志与摘要走 stderr；Windows 下已内置 stdout UTF-8 重配置（控制台默认 GBK 会把中文译文打成乱码，那不是翻译失败）。
