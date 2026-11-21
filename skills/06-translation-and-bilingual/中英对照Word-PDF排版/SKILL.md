---
name: bilingual-word-pdf-layout
description: "生成或改进中英对照 Word/PDF 的段落配对、版式和导出，按文字版与扫描版选择流程。保留原件并逐页检查，不依赖历史翻译项目路径或把单一字号阈值套用所有文档。"
---

# 双语 Word/PDF 对照版式

> 适用性：文中 <project-root>/translator 等路径是历史实现位置；先定位当前项目与输出目录，不依赖这些文件一定存在。保留原文、逐页检查，并按任务范围决定是否需要 OCR 或整篇重排。

## Overview

把一份外文文档变成"每段原文旁边紧跟译文"的成品，且**不破坏原文档的表格线、底纹、编号和图片**。三条互不相同的分支：Word 逐段插入、文字版 PDF 右页擦除后重排、扫描版 PDF OCR + inpaint 后右页贴图。

本机已验证的参考实现（改造前先读它，别照本 skill 重敲）：

- `<project-root>/translator/core/word_translator.py`
- `<project-root>/translator/core/pdf_translator.py`
- 实测环境：PyMuPDF 2.0、opencv-python 5.0.0.93、rapidocr_onnxruntime 1.4.4、numpy 2.4.6、wordninja 2.0.0。
- 译文从哪来不在本 skill 范围内；离线翻译引擎见 skill `ctranslate2-offline-mt-integration`。

## 第 0 步：分流（判错分支，后面全白做）

```python
def is_scanned(page):                      # 与已验证实现一致
    if len(page.get_text("text").strip()) >= 20:
        return False
    area = page.rect.width * page.rect.height
    covered = sum((pymupdf.Rect(info["bbox"]) & page.rect).get_area()
                  for info in page.get_image_info())
    return covered > area * 0.5
```

| 情况 | 分支 | 做法 |
|---|---|---|
| `.docx` | Word | 源段后插入译文段 |
| 有可选中文本 | text | 右页 redaction 擦原文 → 重排译文 |
| 文本 <20 字符且图片覆盖 >50% 面积 | ocr | OCR → inpaint 清理 → 右页整页图 + 译文 |
| 两者都不满足 | copy | 右页原样贴图 + 底色覆盖法写译文 |

分支是**逐页判定**的：同一份 PDF 常混有文字页与扫描页，每页各自记 `mode`（text / ocr / copy），别用"第一页是什么就当全篇是什么"。

进入任何分支前先处理：`doc.needs_pass` 且 `authenticate("")` 失败 → 直接报错让用户先解密码，别硬跑。`page.rotation` 非 0 → 记一条"旋转页译文位置可能偏移"的提示（该场景未验证）。

## 全局不变量

1. **左半页永远放原封不动的原页**（`show_pdf_page`），所有破坏性操作只在**副本**上做。redaction 不可逆，直接在源文档页上擦就丢了左页。
2. **只插不删**（Word）：译文是新段，落在源段**之后**，不改源段。
3. **译文等于源文就不写**：`normalize_source(translated) == normalize_source(source)` 时跳过——中文原文被"翻"成自己、或引擎原样吐回，写进去只是重复噪音。
4. **段落收集去重的键是 lxml 元素对象本身**，不是 `id()`、不是文本。`doc.paragraphs` 每次访问都新建 `Paragraph` 代理对象，按文本去重会把正文里重复出现的同一句误删（漏译）。
5. **试字号必须在离页（scratch page）上试**，不能往成品页试：`insert_textbox` 没有撤销，试错一次就留一层隐形文字。
6. **中文字体优先用 `fontfile` 嵌入系统字体**。内置 `china-ss` 会把英文字母按全宽绘制，`AI` 显示成 `A I`。
7. **每层失败都要降级并计数**，日志必须报出 `放置 N 段 / M 处因空间不足保留原文`。

## Word 分支（要点）

```python
new_element = OxmlElement("w:p")
source._p.addnext(new_element)                 # 插到源段之后
props = deepcopy(source._p.pPr)
for tag in ("w:numPr", "w:sectPr", "w:pageBreakBefore",
            "w:framePr", "w:pBdr", "w:shd"):    # 编号/分节/分页/边框/底纹必须剥
    for e in props.findall(qn(tag)):
        props.remove(e)
spacing = props.find(qn("w:spacing")) or OxmlElement("w:spacing")
spacing.set(qn("w:before"), "0")               # 紧贴原文，不留段前距
new_element.insert(0, props)                   # pPr 必须是 w:p 的第一个子元素
```

- 剥 `numPr` 是硬要求，否则译文被再编一次号（中英各一条 1. 2. 3.）。
- `pPr` `append` 到段尾会让 Word 报损——只能 `insert(0, ...)`。
- 中文字体要 `rFonts` 的 `w:ascii` / `w:hAnsi` / `w:eastAsia` **三个都设**（只设 `run.font.name` 对中文无效）。
- 粗体/斜体只在**所有非空源 run 都粗/斜**时继承，避免段里一个粗体词把整条译文加粗。
- 页眉页脚：遍历 `section.header/footer/first_page_*/even_page_*`，跳过 `is_linked_to_previous`，再按 `str(container.part.partname)` 去重（多个 section 常共享同一 part）。
- 正文收集用 `doc.element.body.iter(qn("w:p"))`，一次覆盖正文 + 表格 + 嵌套内容。

完整代码见 [references/word-bilingual-docx.md](references/word-bilingual-docx.md)。

## 文字版 PDF 分支（要点）

顺序不能换：单页复制到工作副本 → 加 redact → `apply_redactions` → 插译文 → 整页贴到右半。

```python
work = pymupdf.open()
work.insert_pdf(doc, from_page=i, to_page=i)      # 原页要留给左半页，只能擦副本
wp = work[0]
for group in placements:
    for cover in group.cover_rects:
        wp.add_redact_annot(cover, fill=False)      # fill=False = 不画填充矩形
wp.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                    graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)  # 保住图片与矢量线条
```

- **这两个枚举才是"表格线和底纹存活"的真正原因**，`fill=False` 单独用不够：默认行为会填充矩形并删掉重叠图形。
- redaction 抛异常 → 降级**底色覆盖**：按 cover_rect 采样局部背景色、`draw_rect(color=None, fill=...)` 盖住原文再写译文。采样用 dpi 110 pixmap + 每通道 16 级分桶取众数色，别直接取均值（灰底表格里均值是脏灰）。
- 译文颜色沿用该组文字主色；与背景亮度差 `< 0.22` 时强制改黑或改白。
- 字号：从该组字号（逐字符加权中位数，夹到 5–36）起，在 scratch page 上每次 `-0.5` 试到 5pt；`insert_textbox` 返回值 `>= 0` 才算装下，`< 0` 是溢出。全部试不下 → 保留原文并计入 `fit_failures`。
- 文字版分组判据：垂直间距 `<= max(3, 0.55*行高)` 且行首 x0 位移在 `-1 ~ +22`，可把折行与同表格列接起来；项目符号（`•·▪` 或 `1)`）常单独成行，要并到它标记的那一行。
- 成品页宽 `width*2 + RIGHT_GAP`（实测 14.0），中线画一条 `(0.82,0.82,0.82)` / 0.7pt 分隔线。
- 保留元数据与目录：标题追加`（中英对照）`、`out.set_toc(doc.get_toc(simple=False))`；保存前 `subset_fonts()`，保存 `garbage=3, deflate=True`（中文字体不子集化，成品容易几十 MB）。

完整代码见 [references/pdf-text-redaction.md](references/pdf-text-redaction.md)。

## 扫描版 PDF 分支（要点）

右半页 = 擦掉原文墨迹的整页图（`insert_image(..., keep_proportion=False)`），译文按原坐标 + `right_x` 偏移叠上去。

- OCR：RapidOCR（单例 + 锁），页面渲染 200dpi，`score < 0.45` 丢弃；结果框是四点多边形不是矩形，取 min/max 转 `Rect`，坐标乘 `72/OCR_DPI` 回到 pt。喂给 OCR 前 RGB→BGR（`[:, :, ::-1]` + `ascontiguousarray`）。
- RapidOCR 常吞掉词内空格 → 用 `wordninja` 重切长词/驼峰词，否则翻译引擎收到 `Temperature` 这种整块。
- 分组四条判据（缺一就多并或乱并）：同列（`round(x0/5)` 相等）+ 垂直间距 `<= max(3, 0.55*上一行高)` + 上一行宽度达到该列最宽行的 0.72（说明是折行不是新条目）+ 上一行**不以句末标点结尾**（`.[!?;:。！？；：]`）。
- 表格线保护：`dark = threshold(gray, 200, THRESH_BINARY_INV)` → 形态学 open，横线核 `np.ones((1,60))`、竖线核 `np.ones((60,1))` → 取并再 dilate 一次得 `rules`。
- **混合掩码**：`bbox.width < 250` 且左右边缘 14pt 带内存在竖线 → 判为表格单元格 → 只掩墨迹（区域内 80 百分位当背景，`|区域-背景| > 28` 才入掩码）；否则整行矩形全掩。
- `mask[rules > 0] = 0` 要在 dilate **前和 dilate 后各做一次**（dilate 会把掩码吃进表格线，线会糊）。最后 `cv2.inpaint(img, mask, 4, cv2.INPAINT_TELEA)`。
- OCR 分组字号用 `median(行高) * 0.82`，夹到 5–24；cover_rect 外扩 1.5（文字版用 1.2）。
- 折行接回时中文语族不加空格：`cjk/(cjk+latin) > 0.3` 用 `"".join`，否则 `" ".join`。
- OCR 整体失败 → 该页降级 `copy`（保留原页）；inpaint 返回 `None`（缺 cv2/numpy 或编码失败）→ 走文字版的底色覆盖路径。

完整阈值与代码见 [references/pdf-scan-ocr-inpaint.md](references/pdf-scan-ocr-inpaint.md)。

## 已知坑

- `add_redact_annot` 默认画黑色填充矩形并连带删图形。
- 在源文档页面上直接 redaction，左半对照页就没了。
- 内置 `china-ss` 英文全宽；`fontfile` 按 `msyh.ttc` → `simhei.ttf` → `simsun.ttc` 顺序探测存在，并在 scratch 页试插一次 `中文Aa`，抛异常就把 `USE_LOCAL_FONT` 关掉退回 `china-ss`。
- `insert_textbox` 溢出**不抛异常**，只返回负数；不检查返回值就会静默丢文字。
- 段落收集按文本去重 → 重复句漏译；按 `id()` 去重 → 代理对象回收后 id 复用，误判重复。
- 扫描件 inpaint 后仍有纯白块 = 表格内的组走了矩形掩码；表格线断掉 = `mask[rules]=0` 只做了一次，或形态学核太短把文字笔画当线。
- 译文放不下时"借用邻页空白"或"缩到 4pt 以下"都不要做，保留原文 + 计数上报才是已验证行为。
- 密码 PDF 直接拒；旋转页只提示；**跨页表格未验证**。
- 译文质量仍需人工复核（离线小模型对短标题易跑偏，见 `ctranslate2-offline-mt-integration`）。

## 验收清单

1. 逐段配对计数：成品译文段数 == 计划写入段数。本机实测：26 段英文 docx → 26/26，扫描版 PDF → 29/29。
2. 左右页放大对比：右页的表格线、底纹、图片必须与左页逐像素一致（只有文字被换掉）。
3. 扫描页无纯白矩形，擦除处能看到纸纹。
4. Word 能正常打开；编号列表不被译文重复编号；译文紧贴原文（无多余段前距）。
5. 日志给出 `放置 N 段` 与 `M 处因空间不足保留原文`；`fit_failures > 0` 时要能定位是哪些段。
6. 成品体积合理（字体已子集化）；元数据标题带`（中英对照）`、书签目录还在。
7. 现成样例可直接对照（同目录有原文）：
   - `<project-root>/translator/samples/示例-文字版_双语.pdf`、`示例-扫描版_双语.pdf`、`示例-英文报告_双语.docx`
   - `<project-root>/translator/samples/保密模式样例/`：日文 / 俄文 docx、多语种 PDF、扫描版 PDF

## Resources

- [references/word-bilingual-docx.md](references/word-bilingual-docx.md) — Word 段落收集、pPr 剥离、run 字体/颜色/继承完整代码
- [references/pdf-text-redaction.md](references/pdf-text-redaction.md) — 文字版 redaction、底色覆盖降级、背景色采样、字号适配、页面组装
- [references/pdf-scan-ocr-inpaint.md](references/pdf-scan-ocr-inpaint.md) — OCR 分组、长直线检测、混合掩码、inpaint 完整参数
