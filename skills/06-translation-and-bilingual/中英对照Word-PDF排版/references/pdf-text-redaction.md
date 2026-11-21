# 双语 PDF — 文字版（redaction 路线）

参考实现：`<project-root>/translator/core/pdf_translator.py`。适用于文本可选中的 born-digital PDF：右半页把原文擦掉、原位印上中文，表格线与底纹**逐像素保留**。

## 常量

```python
RIGHT_GAP = 14.0          # 左右两半之间的分隔带宽度
MIN_FONT_SIZE = 5.0       # 字号缩到这就放弃，保留原文
CJK_FONT = "china-ss"     # 内置中文字体（英文会全宽，仅作兜底）
LOCAL_FONT_NAME = "zh-local"
LOCAL_FONT_FILES = ("C:/Windows/Fonts/msyh.ttc",
                    "C:/Windows/Fonts/simhei.ttf",
                    "C:/Windows/Fonts/simsun.ttc")
USE_LOCAL_FONT = bool(next((p for p in LOCAL_FONT_FILES if os.path.exists(p)), ""))
BULLET_RE = re.compile(r"^(?:[•·▪◦●○■□◆◇‣∙*\-–—]|\(?\d{1,2}[.)])$")
```

## 字体：优先嵌入系统字体

```python
def _font_kwargs() -> dict:
    if USE_LOCAL_FONT:
        return {"fontname": LOCAL_FONT_NAME, "fontfile": LOCAL_FONT_FILE}
    return {"fontname": CJK_FONT}

def _check_local_font(page) -> None:      # 在 scratch 页试插一次
    global USE_LOCAL_FONT
    if not USE_LOCAL_FONT:
        return
    try:
        page.insert_text(pymupdf.Point(4, page.rect.height - 4), "中文Aa", **_font_kwargs())
    except Exception:
        USE_LOCAL_FONT = False
```

内置 `china-ss` 会把拉丁字母按全宽绘制（`AI` → `A I`），所以能用 `fontfile` 就用；探测一次、失败即全局回落，避免每段都抛异常。

## 分组（`get_text("dict", sort=True)` → TextGroup）

每组带 `bbox`（写译文用）、`cover_rects`（擦原文用，逐行而非整组一个大框）、`font_size`、`color`、`align`。

三步：

1. **行归一**：逐 span 累计字号（按字符数加权，一个 block 里混字号时取中位数才准）与颜色直方图。
2. **项目符号并回**：`BULLET_RE` 命中的单独行，若与下一行垂直间距 `<= max(高度, 6)`，合成一组，`cover_rects` 保留两个（否则符号会被擦掉但没写回译文，或反之）。
3. **折行合并**：

```python
gap   = item["rect"].y0 - previous["last_y1"]
shift = item["cover_rects"][0].x0 - previous["last_x0"]
limit = max(3.0, previous["last_height"] * 0.55)
if gap <= limit and -1.0 <= shift <= 22.0:      # 同段折行
    merge()
```

`shift` 上界 22 用来把**同一表格单元格的多行**接起来、把**相邻列**分开；负 1 容差是行首对齐抖动。

文本收尾清洗（三条 regex 都要）：

```python
text = " ".join(group["text_parts"])
text = re.sub(r"(?<=[A-Za-z])-\s+(?=[a-z])", "", text)        # 跨行连字符 hybrid\nuation
text = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", text)  # 中文之间不留空格
text = re.sub(r"\s+", " ", text).strip()
font_size = min(max(_median(group["sizes"]), 5.0), 36.0)
cover_rects = [_expand(rect, 1.2) for rect in group_cover_rects]
```

对齐猜测（标题居中、页右对齐）：

```python
def _guess_align(bbox, page_width, font_size) -> int:      # 0 左 1 中 2 右
    if abs(center - page_width/2) < page_width*0.04 and width < page_width*0.85 and font_size >= 12:
        return 1
    if bbox.x1 > page_width*0.9 and bbox.x0 > page_width*0.5 and width < page_width*0.5:
        return 2
    return 0
```

## 背景色采样（底色覆盖降级用）

```python
pixmap = page.get_pixmap(dpi=110, alpha=False)
...
def sample(rect):                     # 取区域内"最多的颜色"，不是平均色
    area = _expand(rect, 2.5)
    block = pixels[y0:y1+1, x0:x1+1].reshape(-1, 3).astype(np.int32)
    keys = (block[:,0]//16)*256 + (block[:,1]//16)*16 + (block[:,2]//16)
    counts = np.bincount(keys, minlength=4096)
    dominant = keys == int(counts.argmax())
    return tuple(float(v)/255.0 for v in block[dominant].mean(axis=0))
```

dpi 110 足够（只是取底色），别用 200dpi 浪费内存；均值在灰底表格里会得到脏灰，与周围明显不同。

## redaction 主路径

```python
work_doc = pymupdf.open()
work_doc.insert_pdf(doc, from_page=idx, to_page=idx)
work_page = work_doc[0]
for group, _, _ in placements:
    for cover in group.cover_rects:
        work_page.add_redact_annot(cover, fill=False)
work_page.apply_redactions(
    images=pymupdf.PDF_REDACT_IMAGE_NONE,
    graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
)
for group, translated, size in placements:
    if _insert_translation_text(work_page, group, 0, translated, size):
        placed += 1
```

三个参数缺一不可：

| 参数 | 不给会怎样 |
|---|---|
| `fill=False` | 每个 redact 区域画一个填充矩形（默认黑），盖掉底纹 |
| `images=PDF_REDACT_IMAGE_NONE` | 与文字重叠的整张图片被裁掉 |
| `graphics=PDF_REDACT_LINE_ART_NONE` | 表格线、边框、矢量图形随文字一起被删 |

`work_page` 完成后整页 `show_pdf_page(right_rect, work_doc, 0)` 贴到右半。**不要**在 `doc` 的页上直接 redact——左半页还要用原样页。

异常 → 关闭 `work_doc`、`redacted=False`，落到底色覆盖路径：

```python
def _draw_translation(page, group, offset_x, text, size):
    for index, cover in enumerate(group.cover_rects):
        fill = group.cover_colors[index] if index < len(group.cover_colors) else (1, 1, 1)
        page.draw_rect(rect_with_offset, color=None, fill=fill, overlay=True)
    return _insert_translation_text(page, group, offset_x, text, size)
```

## 颜色对比保护

```python
def _luminance(c): return c[0]*0.2126 + c[1]*0.7152 + c[2]*0.0722

def _translation_color(group):
    color = group.color
    if group.cover_colors:
        background = 通道平均(group.cover_colors)
        if abs(_luminance(color) - _luminance(background)) < 0.22:
            color = (1,1,1) if _luminance(background) < 0.5 else (0,0,0)
    return color
```

深色底纹上的深灰原文色直接复用会看不见；差值门限 0.22 以下强制翻成黑或白。

## 字号适配（离页试字）

```python
def _find_fitting_size(scratch_page, rect, text, start_size, align):
    if rect.width < 3 or rect.height < 3:
        return None
    size = min(max(start_size, MIN_FONT_SIZE), 36.0)
    while size >= MIN_FONT_SIZE:
        spare = scratch_page.insert_textbox(rect, text, **_font_kwargs(),
                                           fontsize=size, color=(0,0,0),
                                           align=align, lineheight=1.18)
        if spare >= 0:            # 返回值是剩余高度，负数 = 溢出
            return size
        size -= 0.5
    return None
```

- `scratch_page` 尺寸取全篇最大页 `max(width)+20 × max(height)+20`，坐标才能逐页复用。
- 每页的 rect 直接用该组的 `bbox`（不偏移），因为 redaction 副本和右半贴图同尺寸；只有走"原页 + 覆盖"时才要 `offset_x = right_x`。
- 试到 5pt 仍放不下 → 返回 `None`，该段计入 `fit_failures`，**保留原文**，不要越界写到别的段或下一行。
- `lineheight=1.18` 是实测能塞进表格行高的最紧值；更小会视觉挤，更大常溢出。

## 页面组装与保存

```python
right_x = width + RIGHT_GAP
new_page = out.new_page(width=width*2 + RIGHT_GAP, height=height)
new_page.show_pdf_page(pymupdf.Rect(0, 0, width, height), doc, idx)       # 左：原样
if redacted:            new_page.show_pdf_page(right_rect, work_doc, 0)   # 右：擦后重排
elif scan_image:        ...                                                # 右：清理后的扫描图
else:                   new_page.show_pdf_page(right_rect, doc, idx) + 覆盖写译文
new_page.draw_line(Point(width + RIGHT_GAP/2, 0), Point(width + RIGHT_GAP/2, height),
                   color=(0.82, 0.82, 0.82), width=0.7)                   # 中缝细线
```

收尾（都要）：

```python
metadata["title"] = f"{title}（中英对照）"; out.set_metadata(metadata)
toc = doc.get_toc(simple=False);  out.set_toc(toc)     # 保留书签
out.subset_fonts()                                     # 中文不子集化 → 成品几十 MB
out.save(output_path, garbage=3, deflate=True)
```

日志必须报数：`已生成对照 PDF：成功放置 {drawn} 段译文` + 有失败时追加 `；{fit_failures} 处因空间不足保留原文`。
