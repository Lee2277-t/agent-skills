# GitHub 相关技能对照

核对日期：2026-10-28。已阅读下列仓库的 SKILL.md；只作流程研究，未安装或执行其中脚本，也未验证外部服务、价格和最终渲染结果。仓库后续可能变化，实际采用前重新核对依赖、许可证及当前接口。

| 项目与技能入口 | 路线及适配场景 | 依赖、边界与本次采用内容 |
|---|---|---|
| [BuzyOwl/song-video-director](https://github.com/BuzyOwl/song-video-director)，[SKILL.md](https://github.com/BuzyOwl/song-video-director/blob/main/skill/song-video-director/SKILL.md) | 音乐分析驱动 Remotion/p5.js/three.js 代码 MV；与本教程的合成路线最接近 | 仓库标明 MIT；音频分析脚本依赖 Python/numpy，可选语音识别。参考实际歌曲分析、可复现帧与成片证据；不照搬个人审美硬规则、发布指令或并行代理要求 |
| [huangserva/musical-mv-storyboard](https://github.com/huangserva/musical-mv-storyboard)，[SKILL.md](https://github.com/huangserva/musical-mv-storyboard/blob/main/SKILL.md) | 音乐结构 → 导演分镜 → 关键帧/视频生成 → 剪辑；适合更强调连续角色表演的镜头 | 本次未确认独立 LICENSE，复制分发前需核实授权；流程含特定供应商工具。参考段落/高潮设计、短句口型边界与剪辑交接，不继承模型参数默认值或强制工具 |
| [obie/slopcore](https://github.com/obie/slopcore)，[music-video/SKILL.md](https://github.com/obie/slopcore/blob/main/skills/music-video/SKILL.md) | 定稿歌 → 图像 → 视频片段，并结合代码歌词排版；适合确实需要图生视频的镜头 | 仓库标明 MIT；依赖其工具链及外部生成服务。参考先试一镜、控制生成开支、时间码修复和抽样审片；不把其账户、费用、平台或审批规则带入本技能 |
| [tomc98/sketch-to-video-skill](https://github.com/tomc98/sketch-to-video-skill)，[SKILL.md](https://github.com/tomc98/sketch-to-video-skill/blob/main/SKILL.md) | 草图/PDF → 风格图 → 视频提示词 → 音乐与节拍剪辑；适合已有绘画或草图的项目 | 仓库标明 MIT；包含 Shell、FFmpeg 及额外工具要求。参考视觉基准与素材交接；起点与本教程不同，不要求用户先手绘，不强制附加技能 |

## 选择建议

围绕本视频创建的技能以歌曲和代码合成为主，优先参考 song-video-director。需要镜头级生成视频时，再借鉴 musical-mv-storyboard 或 slopcore 的分镜/素材约定；已有草图时再考虑 sketch-to-video-skill。

本技能独立撰写中文指令，不捆绑上述仓库，不默认授权运行下载来的脚本或调用付费服务。上表是文档层面对照，不能等同于安装测试、效果排名或供应商推荐。若后续引入代码或大量原文，保留适用许可证与署名；授权不明确时先不复制。
