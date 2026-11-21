# 来源与相关技能

核对日期：2026-10-29。此技能为中文原创适配指引，没有复制上游运行代码。选定原文/源码证据保存在项目内部的调研记录，不把不完整研究快照作为运行安装包。GitHub API 限流，未取得提交锁定；下载来自当时 main，不能宣称绑定永久版本。

| 来源 | 定位 | 状态 |
|---|---|---|
| [ARCHEON999/Companion-AI-Memory-Context-Token-Optimization](https://github.com/ARCHEON999/Companion-AI-Memory-Context-Token-Optimization) | 冷热记忆、连续性与向量排序设计 | README 和三份设计文档已核对；未接入，参数待验证；未核实再分发许可，不复制整包 |
| [ALittleLov/dsh-soundcheck](https://github.com/ALittleLov/dsh-soundcheck) | 本地音乐特征提取与 DSH 工具桥接 | MIT，关键源码已核对；引擎未安装、音频分析未运行 |
| [pairun325/dsh-whale-sense](https://github.com/pairun325/dsh-whale-sense) | 截屏差异事件与 DSH 陪看 | MIT，关键源码已核对；未采集实屏或启动帮工 |

项目名称末尾的 Public 是 GitHub 可见性标记，不是上述记忆仓库名称的一部分。搜索也出现同名仓库，本次以 ARCHEON999 公开方案作为参考，不断言其他同名项目的归属。

## 相关 skill 搜索结果

- [memory-systems](https://github.com/muratcankoylan/Agent-Skills-for-Context-Engineering/tree/main/skills/memory-systems)：跨会话实体、时态与检索设计。本次完整子目录收录到 `00-通用技能/记忆系统设计`，包含支持资源；不是已运行的记忆后端。
  附带 `memory_store.py` 使用占位随机嵌入和内存结构，不具备现成的语义检索与重启持久化能力；使用前读该目录 `_来源.md` 的边界说明。
- 同一合集的 [context-compression](https://github.com/muratcankoylan/Agent-Skills-for-Context-Engineering/tree/main/skills/context-compression)：本地已收录同名能力，本次不重复安装；偏会话摘要和交接。
- [bradautomates/claude-video 的 watch](https://github.com/bradautomates/claude-video/tree/main/skills/watch)：本地 `00-通用技能/AI看视频` 已收录，含脚本、字幕/转录与关键帧，以及可选 Gemini 引擎。具体依赖和数据去向以现有技能为准，本次未重装。
- [OpenMontage/video-understand](https://github.com/calesthio/OpenMontage/tree/main/.agents/skills/video-understand)：FFmpeg 抽帧加可选 Whisper，适合本地证据提取；与已有 watch 重叠，仅记录候选，未安装。
- [marlin-cli/video-understanding](https://github.com/shu-bamma/marlin-cli/tree/main/skills/video-understanding)：本地视觉描述/事件定位，文档限定 Apple Silicon 和短片窗口；当前 Windows 不选作默认方案，未安装。

DSH 插件与 Codex 插件不通用。本次入库不等于在任何宿主全局启用，也未授权后续持续采集、模型下载或云端付费调用。

音乐增强补充核对了 PANNs 官方 README/推理说明、LAION-CLAP README/接口源码及 Essentia 官方模型目录，选型与边界见[情绪与乐器识别](music-understanding.md)。该扩展尚未安装或实测，不归入 soundcheck 上游已实现能力。
