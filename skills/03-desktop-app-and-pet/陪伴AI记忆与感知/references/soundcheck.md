# dsh-soundcheck 音乐分析

核对了 README、package.json、`engine/analyze.py` 和宿主入口。取得的包版本为 0.9.6，Windows DSH 插件，MIT；本次没有安装分析引擎或模型。

技术路径：本地音频解码与特征提取 → 结构化或紧凑报告 → 文本模型基于证据回答。源码使用 librosa；拍速可走模型并用 librosa 给第二意见，保留半速/倍速歧义。调性基于 chroma/模板及候选；人声分轨和歌词 ASR 是可选组件，成本与不确定性分别报告。

可报告时长、拍速候选、RMS/LUFS、真峰值、能量走势和局部片段特征；这些不能直接证明具体乐器、情绪意象或精确歌词。歌词听写需校对，特征测量也不等于模型实际试听。

需要情绪或具体乐器时，继续读[情绪与乐器识别](music-understanding.md)，接入真实音频模型并保留候选与未知；基础测量不能独自完成这些判断。增强方法是本库的扩展指引，不是 dsh-soundcheck 已实现功能的声明。

## 使用与适配

DSH 文档提供 `audio_analyze`、`audio_section`、`audio_bands`、`audio_provision`。先查宿主是否真实注册工具；不要把工具名直接当作当前会话可调用工具。

独立 CLI 文档入口是插件完整目录内 `engine/analyze.py`，在已装好相应依赖的 Python 下，例如 PowerShell：

```powershell
& $python -X utf8 "$pluginDir\engine\analyze.py" $audioPath --json --brief
& $python -X utf8 "$pluginDir\engine\analyze.py" $audioPath --start 1:30 --end 2:10
```

变量必须先指向真实路径，检查当前 `--help` 与引擎状态。研究目录只有选定源码，不是完整可运行安装包。按问题先用简报或指定片段；只有需要时启用分轨/ASR，缺组件不能说已完成。缓存键应覆盖文件内容、分析选项和模型版本，避免同路径替换音频后读旧结果。

先以合成节拍、静音和已知电平音频验证节拍歧义、单位、削波/响度及无声处理，再检查真实歌曲片段和异常路径。不要要求音色/情绪断言等于测量真值。MV 可用测量辅助时间轴，逐字字幕仍需实际对齐数据；分轨不是逐字对齐。
