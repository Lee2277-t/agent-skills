# 双语 Word（python-docx）

参考实现：`<project-root>/translator/core/word_translator.py`。产物形如「原文段 / 紧随其后的中文段」。

## 常量

```python
CJK_FONT = "微软雅黑"
TRANSLATION_COLOR = RGBColor(0x1E, 0x49, 0x76)   # 深蓝，和正文区分
```

## 1. 收集段落：去重键必须是 lxml 元素

```python
def _collect_paragraphs(doc) -> list[tuple[Paragraph, str]]:
    entries, seen = [], set()

    def add(container, parent) -> None:
        for paragraph_element in container.iter(qn("w:p")):   # 一次覆盖正文+表格+嵌套
            if paragraph_element in seen:
                continue
            seen.add(paragraph_element)                       # ← 元素对象本身
            paragraph = Paragraph(paragraph_element, parent)
            text = _paragraph_text(paragraph)
            if is_translatable(text):
                entries.append((paragraph, normalize_source(text)))

    add(doc.element.body, doc)

    header_footer_seen: set[str] = set()
    for section in doc.sections:
        for container in (section.header, section.footer,
                          section.first_page_header, section.first_page_footer,
                          section.even_page_header, section.even_page_footer):
            try:
                if container.is_linked_to_previous:
                    continue
                part_name = str(container.part.partname)
            except Exception:
                continue
            if part_name in header_footer_seen:      # 多 section 常共享同一 part
                continue
            header_footer_seen.add(part_name)
            add(container._element, container)
    return entries
```

- `seen` 用 `Paragraph` 对象 → 错。`doc.paragraphs` 每次访问都新建代理对象，同一 `w:p` 两次取会拿到不同代理。用 `w:p` 的 lxml 元素做键才稳。
- `seen` 用 `id()` → 错。代理对象被回收后 id 会复用，导致误判重复而漏译。
- 页眉页脚**不能**用同一个 `seen`（元素在不同 part 里可能等价），所以按 `partname` 单独去重。

## 2. 取段文本：自己遍历，不用 `paragraph.text`

`paragraph.text` 会漏掉 `w:tab`、`w:br`、超链接内文字，且把嵌套 `w:p`（文本框）算进来。

```python
def _paragraph_text(paragraph: Paragraph) -> str:
    parts: list[str] = []

    def walk(element) -> None:
        for child in element.iterchildren():
            tag = child.tag
            if tag == qn("w:p"):            # 嵌套段落跳过，交给外层遍历
                continue
            if tag == qn("w:t"):
                parts.append(child.text or "")
            elif tag == qn("w:tab"):
                parts.append(" ")
            elif tag in (qn("w:br"), qn("w:cr")):
                parts.append(" ")
            elif tag == qn("w:noBreakHyphen"):
                parts.append("-")
            elif tag == qn("w:softHyphen"):
                continue
            else:
                walk(child)

    walk(paragraph._p)
    return "".join(parts)
```

## 3. 插入译文段

```python
def _insert_translation_after(source: Paragraph, text: str) -> None:
    new_element = OxmlElement("w:p")
    source._p.addnext(new_element)                     # 在源段之后
    new_paragraph = Paragraph(new_element, source._parent)

    if source._p.pPr is not None:
        properties = deepcopy(source._p.pPr)
        for tag in ("w:numPr", "w:sectPr", "w:pageBreakBefore",
                    "w:framePr", "w:pBdr", "w:shd"):
            for element in properties.findall(qn(tag)):
                properties.remove(element)
        spacing = properties.find(qn("w:spacing"))
        if spacing is None:
            spacing = OxmlElement("w:spacing")
            properties.append(spacing)
        spacing.set(qn("w:before"), "0")
        new_element.insert(0, properties)              # 顺序：pPr 必须首位

    run = new_paragraph.add_run(text)
    run.font.name = CJK_FONT
    run_properties = run._element.get_or_add_rPr()
    fonts = run_properties.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        run_properties.insert(0, fonts)                # rFonts 也必须在 rPr 首位
    fonts.set(qn("w:ascii"), CJK_FONT)
    fonts.set(qn("w:hAnsi"), CJK_FONT)
    fonts.set(qn("w:eastAsia"), CJK_FONT)

    size = _source_font_size(source)
    if size is not None:
        run.font.size = size
    run.font.color.rgb = TRANSLATION_COLOR

    source_runs = [r for r in source.runs if r.text.strip()]
    if source_runs and all(r.bold for r in source_runs):
        run.font.bold = True
    if source_runs and all(r.italic for r in source_runs):
        run.font.italic = True

    language = OxmlElement("w:lang")
    language.set(qn("w:val"), "zh-CN")
    language.set(qn("w:eastAsia"), "zh-CN")
    run_properties.append(language)
```

各条的作用（去掉任何一条都会出具体问题）：

| 处理 | 为什么 |
|---|---|
| 剥 `w:numPr` | 否则译文被独立编号，列表变成中英各一条 1./2./3. |
| 剥 `w:sectPr` | 段落里带分节符，复制过来会凭空多一节 |
| 剥 `w:pageBreakBefore` | 否则每个译文段都强制分页 |
| 剥 `w:framePr` / `w:pBdr` / `w:shd` | 文本框定位、段落边框、底纹会让译文看起来像"带框的重复内容" |
| `spacing before=0` | 译文紧贴原文，视觉上成对 |
| `insert(0, properties)` | `w:pPr` 必须是 `w:p` 第一个子元素；`append` 会让 Word 打开报损 |
| `rFonts` 三属性 | 只设 `run.font.name` 只改 ascii，中文仍回落默认宋体 |
| 全 run 都粗才加粗 | 段里一个粗体词不该把整条译文加粗 |
| `w:lang zh-CN` | 关掉 Word 对中文段的拼写检查红线与自动中英混排规则 |

字号继承顺序：第一个有 `font.size` 的 run → 段落样式的 `font.size` → 不设（用文档默认）。

```python
def _source_font_size(paragraph):
    for run in paragraph.runs:
        if run.font.size is not None:
            return run.font.size
    try:
        if paragraph.style is not None and paragraph.style.font.size is not None:
            return paragraph.style.font.size
    except Exception:
        pass
    return None
```

## 4. 主循环的写入闸门

```python
inserted = 0
for (paragraph, source_text), translated in zip(entries, translations):
    check_cancel(translator.stop_event)
    if not translated.strip():
        continue
    if normalize_source(translated) == source_text:   # 引擎原样吐回 / 中文没动
        continue
    _insert_translation_after(paragraph, translated.strip())
    inserted += 1

if inserted == 0:
    raise TranslationError("没有获得可写入的译文，请稍后重试或更换文档。")
output_path = unique_output_path(src_path, "双语", ".docx")   # 冲突时 _双语(2).docx
doc.save(output_path)
```

- 先**全部翻译完再写**（`translate_texts` 批量），因为写入位置依赖段落对象；边翻边插在批量失败重试时会把译文写重复。
- `entries` 里的 `Paragraph` 对象在插入新段后仍指向原 `w:p`，所以按序 zip 是安全的（`addnext` 不影响后续元素身份）。
- 空集合与零写入都要抛错并给出人话提示，别静默产出一个"看起来成功"的原样副本。
