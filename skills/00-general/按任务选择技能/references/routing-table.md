> 上游参考资料：其中原作者的机器状态、固定数值、DSH 路径与审批习惯不代表当前环境。执行以本目录 SKILL.md、当前项目规则及用户授权为准。

# 任务类型 → 技能对照表

`scripts/scan.py --task` 打分失败时（新技能、描述写得含糊、用户用词太口语）用手工兜底。左边是任务类型，右边是**该加载的技能**（≤3 个）。

## 按任务类型

| 任务类型 | 加载 | 别加载 | 备注 |
| --- | --- | --- | --- |
| 发布到 GitHub / 开源 / 建仓库 | `repo-publish` | `qianwenai-deploy` | 后者是部署到阿里云，不是 GitHub |
| 部署上线到云（阿里云） | `qianwenai-deploy` | `repo-publish` | 需要询价确认，会花钱 |
| 前端美化 / 去 AI 味 / 页面太丑 | `frontend-craft` | — | 一次只动一类 |
| 写 SKILL.md / 改技能 | 无（直接做） | `skill-router` 自身 | 技能文档很短，不需要专门技能 |
| 选技能 / 省额度 | `skill-router` | — | 就是它自己 |
| 图片生成 / 海报 / 插画 | `qianwen-image-generation` | `qianwen-vision` | vision 是**读**图，不是生成 |
| 看图 / OCR / 视频理解 | `qianwen-vision` | `qianwen-image-generation` | |
| 视频生成 | `qianwen-video-generation` | `qianwen-vision` | |
| 配音 / TTS / 朗读 | `qianwen-audio-tts` | `qianwen-text` | |
| 查余额 / 账单 / 用量 | `qianwen-usage` | `qianwen-payment` | payment 只负责**充值** |
| 充值 / 支付 | `qianwen-payment` | `qianwen-usage` | 会真花钱，必须用户确认金额 |
| 配置 API key / 401 报错 | `qianwen-ops-auth` | `qianwen-usage` | |
| 选模型 / 比价 | `qianwen-model-selector` | — | |
| Word / docx | `office-docx` | `office` | `office` 只是入口，具体活给子技能 |
| Excel / xlsx / 表格 | `office-xlsx` | `office` | |
| PPT / 幻灯片 | `office-pptx` | `office` | |
| 转 PDF | `office-export-pdf` | `office` | |
| 重算表格公式 | `office-recalculate` | `office-xlsx` | |
| 看文档长什么样 / 渲染 | `office-render` | — | |
| STM32 / 单片机 / 嵌入式 | `embed` | — | |
| 找技能 / 装技能 | `qianwen-find-skills` | `skill-router` | 前者是「去外面找」，后者是「选已有的」 |
| 检查技能更新 | `qianwen-update-check` | — | |
| 沙箱权限被拒 | `diagnose-windows-sandbox-acl` | — | 只修 ACL，不做别的 |

## 常见误判

| 用户说 | 容易误加载 | 实际该用 |
| --- | --- | --- |
| 「把项目部署到 GitHub」 | `qianwenai-deploy` | `repo-publish` |
| 「生成一个网页」 | `qianwen-image-generation` | 无（直接写代码）；要美化再加 `frontend-craft` |
| 「看看这张图」 | `qianwen-image-generation` | `qianwen-vision` |
| 「查一下额度」 | `qianwen-payment` | `qianwen-usage` |
| 「做个表格」 | `office` | `office-xlsx` |
| 「这个技能怎么用」 | `qianwen-find-skills` | 无（直接读那个技能） |
| 「优化一下性能」 | `frontend-craft` | 无（frontend-craft 只管视觉，不管性能） |

## 多个技能的组合

真正需要 3 个以上的情况很少，但有几种常见组合：

| 场景 | 组合 |
| --- | --- |
| 发布一个带网页和安装包的工具 | `repo-publish` + `frontend-craft`（如果页面需要改） |
| 做一份带图的产品文档 | `office-docx` + `qianwen-image-generation` |
| 部署一个需要美化页面的站 | `qianwenai-deploy` + `frontend-craft` |

**超过 3 个就是任务没拆清。** 拆成两轮做，每轮 2–3 个技能。

## 维护这张表

技能增删后手动更新这张表。判据：每个已装技能至少出现在表里一次（要么在「加载」，要么在「别加载」列里被明确排除）。

漏掉的技能在 `scan.py` 里也扫不出来时，说明它的 `description` 写得不够具体 —— 去改 description，而不是改这张表。
