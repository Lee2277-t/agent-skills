# 来源说明

这些技能是在实际项目里逐步写成的：先在某次任务里踩坑，把结论记下来，下一次遇到同类问题再修正，
迭代到不再需要临场发挥为止。

## 关于占位符

正文里的路径已替换成占位符，避免绑定某一台机器的目录结构：

| 占位符 | 含义 |
|---|---|
| `<project-root>` | 你的项目根目录，如 `D:\projects` |
| `<skills-root>` | 你的技能库根目录 |
| `<dsh-home>` | DeepSeek Harness 的数据目录 |
| `%USERPROFILE%` | Windows 用户目录 |

## 关于第三方

文中提到的 Qoder、WorkBuddy、Codex、微信开发者工具、CTranslate2、Electron、Tkinter 等，
只作产品名与技术名引用，不包含它们的代码或文档。

技能描述里的方法论是通用的工程写法，不来自任何单一来源的复制。

## 关于许可

本仓库整体 AGPL-3.0。**有一个例外**：

`skills/02-wechat-miniprogram/小程序项目勘察与上线清单/` 是独立的 MIT 项目
（`wechat-miniapp-engineering-mcp`，含自带 `LICENSE`），按它自己的 MIT 条款使用，
不受仓库根目录 AGPL 约束。其余技能均为 AGPL-3.0。

MIT 与 AGPL 兼容：再分发时保留该目录的 MIT 声明即可。