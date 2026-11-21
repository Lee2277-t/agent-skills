# 网上资源索引（2026-10-30 核对）

> 星数和活跃度在 2026-10-30 逐个查过。只收能落成规则的来源，每条写「取什么 / 别学什么」。
> 用法：一个来源只取 **一条** 能马上用在当前页面上的规则，不要收藏完就结束。

## 一、系统方法（先读，改变判断方式）

| 资源 | 形式 | 取什么 | 别学什么 |
| --- | --- | --- | --- |
| [Refactoring UI](https://www.refactoringui.com/)（Adam Wathan & Steve Schoger） | 书 + 免费预览 | 9 档色板法；先用字重和颜色做层级，不够再放大；留白先给多再收；不要在彩色底上放灰字 | 具体色板不照抄，按品牌重新造 |
| [Every Layout](https://every-layout.dev/)（Heydon Pickering & Andy Bell） | 书 + 免费章节 | Stack / Cluster / Sidebar / Switcher / Cover / Frame / Imposter / Icon 等内在布局；用 flex 比例代替断点 | 不需要把 13 个组件全搬进项目 |
| [Practical Typography](https://practicaltypography.com/)（Matthew Butterick） | 在线书，自愿付费 | 行宽、行距、字号、页边距四件事决定排版质量；字体选择要克制 | 它的报纸式排版不适合所有界面 |
| [The Elements of Typographic Style](https://en.wikipedia.org/wiki/The_Elements_of_Typographic_Style)（Robert Bringhurst） | 书 | 字阶与页面比例；Anthropic 的 frontend-design 也以它为字阶基准 | 不必逐条套用到 UI |
| [Laws of UX](https://lawsofux.com/)（Jon Yablonski） | 网站 | Fitts（目标大小）、Hick（选项数量）、Miller（分组）、Jakob（遵循惯例） | 不要当公式，评审时用来解释「为什么难用」 |
| 《写给大家看的设计书》（Robin Williams） | 书 | 对比、重复、对齐、亲密性四原则 | — |

## 二、现代 CSS（动手查）

| 资源 | 形式 | 取什么 |
| --- | --- | --- |
| [moderncss.dev](https://moderncss.dev/)（Stephanie Eckles） | 文章 | 容器查询、`:has()`、`clamp()`、逻辑属性、现代布局的实战写法 |
| [web.dev/learn/css](https://web.dev/learn/css/)（Andy Bell 主笔） | 系统课程 | 从选择器到布局的完整基础，适合补概念 |
| [CSS-Tricks Almanac](https://css-tricks.com/almanac/) | 属性速查 | 某个属性到底怎么用、兼容性如何 |
| [Josh Comeau](https://www.joshwcomeau.com/) | 博客/课程 | CSS 与 React 交互的「为什么」，解释最透 |
| [chokcoco/iCSS](https://github.com/chokcoco/iCSS) | GitHub 20.6k | 中文 CSS 技巧合集，查「这个效果怎么做」很快 |
| [phuocng/csslayout](https://github.com/phuocng/csslayout) | GitHub 8.0k | 布局模式的系统整理 |
| [You-Dont-Need-JavaScript](https://github.com/you-dont-need/You-Dont-Need-JavaScript) | GitHub 20.6k | 纯 CSS 实现交互的参考（弹窗、开关、提示） |
| [Open Props](https://github.com/argyleink/open-props) | GitHub 5.6k，MIT | 设计 token 的结构：颜色、阴影、缓动、尺寸都变量化；可抄结构，不必引依赖 |
| [Utopia](https://utopia.fyi/) | 工具/方法 | 用两组 clamp 在视口间插值，做流式字号和间距 |
| [Modern Font Stacks](https://modernfontstacks.com/) | 工具 | 按字族分类的系统字体栈，零下载、零布局跳动 |
| [CSS Protips](https://github.com/AllThingsSmitty/css-protips) | GitHub 30.3k | 短小实用的 CSS 技巧；挑当前项目用得上的，不要全抄 |

## 三、Agent 设计技能（可直接借方法）

| 资源 | 规模 | 取什么 | 注意 |
| --- | --- | --- | --- |
| [anthropics/skills · frontend-design](https://github.com/anthropics/skills/tree/main/skills/frontend-design) | 整仓 184.8k | 先定审美方向再写代码；「大胆只花在一个地方」；结构装置必须承载信息；当前 AI 默认长相清单 | 它面向新建页面；改旧页面时以现有品牌为准 |
| [pbakaus/impeccable](https://github.com/pbakaus/impeccable) | 95.1k，Apache-2.0 | 24 个命令（critique / audit / polish / typeset）；62 条确定性规则；支持 Qoder | 它的规则是护栏，不是审美标准；不要为了清零规则过度设计 |
| [ui-ux-pro-max](https://github.com/nextlevelbuilder/ui-ux-pro-max) | 星数较少（数百） | 50+ 风格、161 色板、99 条 UX 规范，可当素材库 | 未经充分验证；只取清单，不把结论当权威 |

## 四、组件与细节（看实现，不只看截图）

| 资源 | 规模 | 取什么 |
| --- | --- | --- |
| [radix-ui/primitives](https://github.com/radix-ui/primitives) | 19.4k | 弹层/下拉/焦点管理的无障碍行为；`--transform-origin` 之类的 CSS 变量 |
| [shadcn/ui](https://github.com/shadcn-ui/ui) | 126.9k | 组件结构与 API 设计；**不取皮肤**——它正是 AI 默认长相之一 |
| [motiondivision/motion](https://github.com/motiondivision/motion) | 34.7k | 动效 API 与编排示例 |
| [emilkowalski/vaul](https://github.com/emilkowalski/vaul) | 8.7k | 抽屉的手势、回弹、阻尼细节 |
| [emilkowalski/sonner](https://github.com/emilkowalski/sonner) | 13.1k，MIT | Toast 的堆叠、暂停、关闭细节 |
| [lucide-icons/lucide](https://github.com/lucide-icons/lucide) | 25.4k | 线性图标，风格统一 |
| [tailwindlabs/heroicons](https://github.com/tailwindlabs/heroicons) | 23.9k，MIT | 线性/面性两套；同一界面只用一套 |
| [sivan/heti](https://github.com/sivan/heti) | 6.7k，MIT | 中文正文排版 CSS（赫蹏），可直接看它的标点与间距处理 |
| [sofish/typo.css](https://github.com/sofish/typo.css) | 4.5k | 中文排版基线；许可证需按仓库说明核对 |
| [W3C clreq](https://www.w3.org/TR/clreq/) | 标准 | 中文排版需求的权威依据：标点、混排、行首行尾禁则 |

## 五、配色、字体与灵感

| 资源 | 用途 | 提醒 |
| --- | --- | --- |
| [oklch.com](https://oklch.com/) | OKLCH 调色与转换 | 固定 L/C 只转 H，最容易造出成组等重的颜色 |
| [Color & Contrast](https://colorandcontrast.com/) | 对比度与可读性解释 | 先保证 4.5:1，再谈好看 |
| [Realtime Colors](https://realtimecolors.com/) | 实时预览配色在页面上的效果 | 它是起点，不是答案 |
| [Typewolf](https://www.typewolf.com/) | 字体搭配与真实案例 | 看它为什么配，不要只抄字体名 |
| [Fontpair](https://www.fontpair.co/) | 搭配灵感 | 只作起点；两个字体必须明显不同 |
| [Typescale](https://typescale.com/) | 字阶计算 | 选一个比例就固定，不要每页换 |
| [easings.co](https://easings.co/) | 缓动曲线库 | 交互反馈优先 `ease-out` |
| [Godly](https://godly.website/) | 高质量网页灵感 | 偏展示型，学构图不学特效堆叠 |
| [Land-book](https://land-book.com/) | 落地页分类 | 看信息结构，不看皮肤 |
| [Refero](https://refero.design/) | 产品界面截图库 | 需要注册；适合拆解真实产品 |
| [Checklist Design](https://www.checklist.design/) | UI 元素检查清单 | 用来查漏，不用来评分 |
| [NN/g](https://www.nngroup.com/) | UX 研究与启发式 | 评审时引用，避免「我觉得」 |
| [UI Patterns](https://ui-patterns.com/) | 交互模式库 | 先查惯例，再决定要不要创新 |

## 六、四周学习路径

| 周 | 只练 | 读 | 做 |
| --- | --- | --- | --- |
| 1 | 字体 | Modern Font Stacks、Typewolf、Bringhurst 字阶 | 同一页面换三套字体组合，只改字体 |
| 2 | 颜色 | Refactoring UI 色板章节、oklch.com | 9 档法重做一套色板并替换 |
| 3 | 布局/间距 | Every Layout 免费章节、Utopia | 只用 8pt 档位重排一页，不加装饰 |
| 4 | 动效/细节 | Emil 的七条动效建议、Vaul/Sonner 源码 | 只做按压反馈、进场、origin |

## 七、别学什么

- **渐变/玻璃拟态生成器当主视觉**：工具本身没问题，拿来当设计方向就是默认值。
- **Dribbble 纯视觉稿**：大量作品不考虑实现、无障碍和长内容，照抄会翻车。
- **「make it modern / clean / beautiful」提示词合集**：这些词正是 AI 味的来源；要给出主体、气质、约束和一个记忆点。
- **整站照抄**：方法和比例可以学，品牌资产、文案、插画不要搬。
- **一次收藏 50 个链接**：每个来源只取一条能执行的规则，用在自己页面上，比收藏更有用。
- **把规则当配额**：颜色 ≤ 3 种、卡片数改成 4 个，这些是提醒，不是硬指标；页面真实问题优先。

## 八、许可证与引用

- Anthropic 的 skill 和 Impeccable 各有 LICENSE；本库只做中文转述和方法提炼，不整段复制原文。
- 字体、图标商用前核对许可证：Heroicons（MIT）、Heti（MIT）、Sonner（MIT）、Open Props（MIT）已核对；Lucide 和 typo.css 的 GitHub 许可证标识为 `NOASSERTION`，以仓库内 LICENSE 文件为准。
- 参考截图只作内部分析，不随成品分发；参考站的版式可以学，文案和图片不要搬。
