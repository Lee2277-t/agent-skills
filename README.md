# My Agent Skills

一组按主题整理、可直接被 agent 加载的技能。

共 **35 个技能**，分 **10 个主题**。全部来自实际项目里的反复迭代，不含客户数据或私人信息。

## 一个共同点：写清楚什么时候不要用

每个技能的描述里都带「不用于…」的边界。只写「适用于…」很容易被误触发——
模型最常犯的错不是想不到某个技能，而是把不相干的技能套上来，然后按错误的流程走完。

例如 `watercolor-icon-cutout` 结尾是「需要重绘整套图案时改用 game-icon-sheet-cutout」，
`repo-publish` 结尾是「不因普通本地修改或提交自动触发」。

## 怎么用

技能就是 `SKILL.md`（YAML frontmatter + Markdown 正文）。放进 agent 的扫描目录即可：

```
~/.claude/skills/<skill-name>/SKILL.md
~/.codex/skills/<skill-name>/SKILL.md
```

技能多了以后建议配索引：把上百条描述全塞进系统提示反而稀释注意力。
配套工具 [skill-hub](https://github.com/Lee2277-t/skill-hub) 只给 agent 装一个入口，按需检索。

## 目录

### 通用方法

| 技能 | 作用 |
|---|---|
| [argument-weight-editing](00-general/论点权重编辑)/ | 审阅或修改报告、开题报告、方案等论证内容，把篇幅和证据集中到核心论点、创新与关键争议 |
| [change-impact-verification](00-general/增量验证)/ | 在项目新增、删除、修改功能后的开发验证中，根据本次差异、调用关系和共享状态选择必要的测试与界面检查，覆盖改动及受影响功能，通过后停止 |
| [js-module-split-verification](00-general/JS单文件拆模块验证)/ | 在 JavaScript 单文件拆模块或拆分后排查跨模块漏引时，验证接口、依赖和实际行为 |
| [project-handoff](00-general/项目计划交接)/ | 在不同对话之间交出、接收或更新项目计划与执行进度 |
| [skill-router](00-general/按任务选择技能)/ | 根据当前任务筛选需要读取的技能，检查描述重叠与误触发，减少无关正文加载 |

### 图片与游戏素材

| 技能 | 作用 |
|---|---|
| [ai-image-watermark-removal](01-image-and-game-assets/去AI图片水印)/ | 在用户明确要求清理图片、扫描页或视频上的水印、角标与遮挡时，选择保留主体和纹理的处理方式并逐张验证结果 |
| [game-bg-series-generation](01-image-and-game-assets/成套游戏背景图生成)/ | 基于同系列已定稿参考图批量生成构图一致的游戏背景变体，用于季节、天气、时段或场景成套素材 |
| [game-icon-sheet-cutout](01-image-and-game-assets/图标素材表改水彩并抠透明底)/ | 依据参考素材表重绘统一风格的图标集，并拆分交付透明图标 |
| [watercolor-icon-cutout](01-image-and-game-assets/水彩白底图标抠透明底)/ | 从白底或近白底的水彩图标、笔刷素材中分离背景、按网格拆成单图并验证透明边缘 |

### 微信小程序

| 技能 | 作用 |
|---|---|
| [wechat-miniapp-engineering-skill](02-wechat-miniprogram/小程序项目勘察与上线清单)/ | Chinese-first WeChat Mini Program engineering workflow and local analysis skill. Use when Codex needs to inspect a WeChat native/miniprogram cloud project, create beginner-friendly product-to-engineering plans, map pages/components/cloud functions/data collections, gather task-relevant context, generate launch or CloudBase release checklists, run a mini program security quick scan, or replace the old wechat-miniapp-engineering MCP workflow without requiring MCP client configuration. |
| [wechat-miniprogram-asset-audit](02-wechat-miniprogram/小程序资源瘦身)/ | 在小程序资源体积检查失败或明确要求清理资源时，统计包内资产、核对静态与动态引用并提出可恢复的迁移方案 |
| [wechat-miniprogram-privacy-audit](02-wechat-miniprogram/小程序隐私合规审计)/ | 扫描微信小程序可能涉及隐私的接口、组件、声明与失败处理，形成带代码位置的待核对清单 |
| [wechat-miniprogram-silent-failure](02-wechat-miniprogram/小程序静默失败排查)/ | 排查小程序点击无反馈、loading 不结束、列表不刷新及异步交互异常 |

### 桌面应用与桌宠

| 技能 | 作用 |
|---|---|
| [companion-memory-perception](03-desktop-app-and-pet/陪伴AI记忆与感知)/ | 设计或接入陪伴 AI 的冷热记忆、音乐特征与情绪分析、乐器候选识别及屏幕陪看 |
| [desktop-pet-character-design](03-desktop-app-and-pet/桌宠角色外形设计)/ | 为桌宠、吉祥物或虚拟形象设计角色外形：概念图、比例与轮廓、配色、表情集和可实现的视觉规范 |
| [electron-desktop-pet-mvp](03-desktop-app-and-pet/Electron桌宠最小可运行版)/ | Build and verify a minimal runnable Electron desktop pet or transparent always-on-top desktop widget on Windows: bootstrap a portable Node when npm is missing, create a transparent click-through window with region hit-testing, implement main-process dragging with persisted position, add SVG idle animation, and verify automatically with capturePage alpha checks and sendInputEvent. Use when creating a desktop pet MVP, adding transparent or click-through desktop widgets, debugging Electron transparency/mouse pass-through, or installing Electron when npm is unavailable. 中文触发：从零做桌宠、桌面宠物最小版、透明置顶窗口、鼠标穿透、Electron 桌宠、便携 Node 安装 Electron |
| [electron-web-preview-qa](03-desktop-app-and-pet/Electron网页预览截图质检)/ | 当内嵌浏览器预览或截图工具不可用（如 viewport 0×0、截图空白/过期、无法交互）时，用本机已有 Electron 搭建一次性网页质检环境：隔离 userData、可见前台窗口、capturePage 截图、executeJavaScript 采集布局指标与触发弹窗，并按 390×844 复验移动端 |
| [electron-windows-bootstrap](03-desktop-app-and-pet/Electron-Windows环境搭建)/ | 诊断 Windows Electron 项目的 Node/npm、二进制下载与窗口启动问题 |

### 本地网页工具交付

| 技能 | 作用 |
|---|---|
| [audit-recon-tool-production](04-local-web-tool-delivery/审计对账工具制作闭环)/ | 面向审计、对账、记账这类「金额必须可复现、用户不是技术人员」的本地工具，给出长周期制作与验收方法：先立口径红线（哪些功能只能提示、绝不许改金额），按「对标选型→差距表→核许可证借语义→落地→复测→汇报」跑轮次，用六层证据栈（语法／golden 快照／vm 断言／一命令全量回归／真窗口 QA／真实语料与交付包往返）让每个数字都能复核，并用交接稿固化口径编号、已知坑与已判定不做的清单 |
| [offline-single-file-benchmark-loop](04-local-web-tool-delivery/离线单文件工具对标迭代)/ | 以对标驱动的方式开发并收尾离线单文件网页工具（file:// 双击即开）：选对标、列差距表、按轮次交付、用独立裁判反查、单文件构建与交接 |
| [offline-web-tool-fixture-regression](04-local-web-tool-delivery/离线网页工具夹具回归)/ | 用合成文件验证本地网页工具的导入、计算和导出内容 |
| [qoder-inapp-browser-ui-qa](04-local-web-tool-delivery/Qoder内置浏览器UI验收)/ | 在 Qoder 内置浏览器（browser-use MCP）里对本地网页工具做端到端功能验收的可复现流程 |
| [windows-local-web-tool-delivery](04-local-web-tool-delivery/本地网页工具双击交付骨架)/ | 在用户要求 Windows 双击运行且需要本地后端时，建立回环地址服务、单实例入口和可验收交付包 |
| [win-offline-web-tool-regression-package](04-local-web-tool-delivery/离线网页工具打包回归)/ | 回归并重新打包 Windows 离线网页工具，核对中文路径、实际导出与 ZIP 条目内容 |

### Windows 桌面工具

| 技能 | 作用 |
|---|---|
| [tkinter-gui-headless-e2e-qa](05-windows-desktop-tools/Tkinter无头端到端测试)/ | 通过应用入口与控件级驱动验证 Windows Tkinter 工具的关键流程，检查输出、日志和窗口状态 |
| [windows-tkinter-desktop-tool](05-windows-desktop-tools/Tkinter桌面工具成品化)/ | 将 Windows Tkinter 工具完善为可交付应用，处理 DPI、线程通信、可选拖放与启动反馈 |

### 翻译与双语文档

| 技能 | 作用 |
|---|---|
| [bilingual-word-pdf-layout](06-translation-and-bilingual/中英对照Word-PDF排版)/ | 生成或改进中英对照 Word/PDF 的段落配对、版式和导出，按文字版与扫描版选择流程 |
| [ctranslate2-offline-mt-integration](06-translation-and-bilingual/CTranslate2离线翻译集成)/ | Integrate and debug a CTranslate2 + SentencePiece offline MT model (OPUS-MT / Marian) on Windows: load a converted model from a CJK path, add the mandatory source </s>, inject sentence-final punctuation for short titles, batch-decode on CPU with int8, detect repetition degeneration, gate non-English input, and prove a confidential mode makes zero network calls. Use when wiring an offline translation engine, when offline output shows repeated garbage such as 目录目录 or 导言 导言 导言, when sentencepiece fails to open source.spm, when add_source_eos is false in the model config, when offline translation is unexpectedly slow, or when a no-network / no-cache confidentiality claim needs verification. Trigger words: CTranslate2, ct2, OPUS-MT, Marian, SentencePiece, 离线翻译, 保密模式, 断网, add_source_eos, compute_type, translate_batch. |
| [free-bing-translation-pipeline](06-translation-and-bilingual/免API免费翻译通道)/ | 排查或维护已有的免 Key 在线翻译链路，检查分片、缓存、降级与返回完整性 |
| [offline-mt-language-routing-tuning](06-translation-and-bilingual/离线翻译语言路由调优)/ | Tune and forensically verify language routing in an offline multi-model MT app (small English model plus an NLLB-style multilingual model): probe every extracted segment's verdict with letter counts and detector confidence, raise the Latin gate so short English titles stay on the English model (measured ≥40 letters AND prob ≥0.9), put an exact-match heading lookup before should_translate to kill whole-sentence hallucinations on short titles and rescue kanji-only Japanese headings skipped as Chinese, then quantify the payoff with a peak-RSS A/B. Use when a plain English document loads the ~800 MB multilingual model, when 意大利文/西班牙文 shows up in the per-language counts of an English file, when short headings translate to unrelated sentences, or when routing thresholds must be re-tuned after a model swap. Trigger words: 语种路由, 语种误判, 多语种模型误加载, langdetect 阈值, 短标题查表, heading lookup, should_translate 顺序, 峰值内存, route probe, NLLB routing. |

### 设计与创意

| 技能 | 作用 |
|---|---|
| [ai-mv-production](09-design-and-creative/AI音乐MV全流程)/ | 制作或修改 AI 音乐 MV、歌词视频、角色剧情 MV：从点子与写歌选歌，到音频节拍/歌词对时、分镜确认、角色一致性出图、Remotion 等代码合成、审片返修与成片核验 |
| [frontend-craft](09-design-and-creative/前端视觉打磨)/ | 在现有页面或新页面上确定审美方向，打磨视觉层级、中文排版、配色、间距、组件状态和动效，减少模板式设计 |

### 开发辅助

| 技能 | 作用 |
|---|---|
| [qoder-skill-authoring-gate](11-dev-assistance/Qoder技能落盘闸门)/ | 在 Qoder 技能编辑会话出现 SKILL_CONFIRMATION_REQUIRED、SKILL_PATH_CHANGED 或 SKILL_TARGET_MISMATCH 时定位阻塞并保留可恢复草稿 |
| [repo-publish](11-dev-assistance/GitHub发布前审计)/ | 审查本地项目准备公开到 GitHub 的文件、密钥风险、文档与发布清单，并在用户授权范围内完成仓库或 Release 发布 |

### 平台集成

| 技能 | 作用 |
|---|---|
| [workbuddy-token-usage](12-platform-integration/WorkBuddy Token用量统计)/ | 读取本机 WorkBuddy JSONL 日志统计已记录的 token 字段及分会话用量 |

## 约定

- 正文里的 `<project-root>`、`<skills-root>`、`%USERPROFILE%` 是占位符，替换成你环境里的实际路径
- 目录名不参与加载，`name` 字段才是标识
- 技能之间按 `name` 互相引用，不用路径

## 许可

AGPL-3.0-only。

例外：`skills/02-wechat-miniprogram/小程序项目勘察与上线清单/` 是一个独立的 MIT 项目，按它自带的 LICENSE 使用。

涉及的第三方工具（Qoder、WorkBuddy、微信开发者工具等）只作名称引用，不包含其代码。