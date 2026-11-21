# 双语 PDF — 扫描版（OCR + inpaint 路线）

参考实现：`<project-root>/translator/core/pdf_translator.py` 的 `_is_scanned` / `_ocr_groups` / `_clean_scanned_page`。右半页放**擦掉原文墨迹后的整页图**，中文叠在原坐标上。

## 常量

```python
OCR_DPI = 200
OCR_MIN_SCORE = 0.45
```

## 判页

```python
def _is_scanned(page) -> bool:
    if len(page.get_text("text").strip()) >= 20:
        return False
    area = page.rect.width * page.rect.height
    if area <= 0:
        return False
    covered = 0.0
    for info in page.get_image_info():
        rect = pymupdf.Rect(info["bbox"]) & page.rect
        if rect.width > 0 and rect.height > 0:
            covered += rect.width * rect.height
    return covered > area * 0.5
```

- 20 字符阈值：很多扫描 PDF 有极少量 OCR 层残留或页码文本层，不能只看"有没有文本"。
- 用 `get_image_info()` 的 bbox 交集累加，而不是"存在图片对象"——插图 PDF 也不是扫描件。
- 有 `get_image_info()` 抛异常 → 判非扫描（保守，走文字版）。

## OCR 引擎（进程内单例 + 锁）

```python
_OCR_ENGINE = None
_OCR_LOCK = threading.Lock()

def _get_ocr_engine():
    global _OCR_ENGINE
    with _OCR_LOCK:
        if _OCR_ENGINE is None:
            from rapidocr_onnxruntime import RapidOCR
            _OCR_ENGINE = RapidOCR()
    return _OCR_ENGINE
```

首次加载要提示（`正在加载 OCR 识别引擎…`），实测扫描件 29 段整页耗时约 13 秒、峰值内存约 900MB，用户会以为卡死。

## 识别 + 坐标换算

```python
pixmap = page.get_pixmap(dpi=OCR_DPI, alpha=False)
array = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
    pixmap.height, pixmap.width, pixmap.n)
if pixmap.n == 4:
    array = array[:, :, :3]
image = np.ascontiguousarray(array[:, :, ::-1])      # RGB → BGR，RapidOCR 要 BGR
result, _ = engine(image)
del pixmap, array, image                              # 大图尽快释放
scale = 72.0 / OCR_DPI                                # 像素 → pt
for box, text, score in result:
    if score < OCR_MIN_SCORE or not text.strip():
        continue
    xs = [p[0] for p in box]; ys = [p[1] for p in box]    # box 是四点多边形，不是矩形
    rect = pymupdf.Rect(min(xs)*scale, min(ys)*scale, max(xs)*scale, max(ys)*scale)
```

- `[:, :, ::-1]` 后必须 `ascontiguousarray`，否则 OpenCV/ONNX 输入非连续会报错或结果错。
- 过滤 `rect.width <= 1 or rect.height <= 1` 的碎片。
- 行内中文之间去空格：`re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", text)`。

## OCR 丢空格重切（喂翻译前必修）

```python
def _fix_ocr_words(text: str) -> str:
    if wordninja is None:          # 缺依赖就原样返回，别整条链挂掉
        return text
    def repair(match):
        token = match.group(0)
        if len(token) < 4 and not re.search(r"[a-z][A-Z]", token):
            return token
        parts = wordninja.split(token)
        return " ".join(parts) if len(parts) > 1 else token
    return re.sub(r"[A-Za-z]{2,}", repair, text)
```

RapidOCR 常把 `temperature` 认成整块无空格 token（甚至 `Temper ature` 合并成 `Temperature`）；不重切会让翻译引擎把整块当未知词，输出跑偏。`wordninja` 可选依赖，缺失时降级。

## 分组四条判据

```python
lines.sort(key=lambda item: (round(item[0].y0, 1), item[0].x0))
column_width = {}                       # 每列最宽行，用于"是否折行"判据
for rect, _ in lines:
    key = int(round(rect.x0 / 5.0))
    column_width[key] = max(column_width.get(key, 0.0), rect.width)

for rect, text in lines:
    column = int(round(rect.x0 / 5.0))
    if raw_groups:
        group = raw_groups[-1]
        gap = rect.y0 - group["bbox"].y1
        previous_rect, previous_text = group["lines"][-1]
        width = max(column_width.get(group["column"], previous_rect.width),
                    previous_rect.width)
        full_line = previous_rect.width >= width * 0.72
        ends_sentence = bool(re.search(r"[.!?;:。！？；：]$", previous_text))
        limit = max(3.0, previous_rect.height * 0.55)
        if (column == group["column"] and gap <= limit
                and full_line and not ends_sentence):
            合并到 group
```

四条各自挡掉一类错误，缺一就出具体问题：

| 判据 | 挡掉的问题 |
|---|---|
| `column == group["column"]`（x0 桶 5pt） | 把左右两列/表格并成一句 |
| `gap <= max(3, 0.55*上一行高)` | 跨条目、跨段落粘连 |
| `full_line`（上一行达该列最宽 0.72） | 短行本是完整句，被下一段拽走 |
| `not ends_sentence` | 上一行已经说完，不该续接 |

接回文本时按语族决定分隔符：

```python
def _join_ocr_text(texts):
    joined = " ".join(texts)
    cjk = len(CJK_RE.findall(joined)); latin = len(re.findall(r"[A-Za-z]", joined))
    return "".join(texts) if cjk and cjk / max(cjk + latin, 1) > 0.3 else joined
```

组属性：`font_size = min(max(median(行高) * 0.82, 5.0), 24.0)`，`cover_rects = [_expand(rect, 1.5)]`（OCR 框偏紧，外扩比文字版的 1.2 大），颜色固定黑（扫描页无颜色信息）。

## 擦墨迹并重建纸面（inpaint）

```python
dark = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)[1]
horizontal = cv2.morphologyEx(dark, cv2.MORPH_OPEN, np.ones((1, 60), np.uint8))
vertical   = cv2.morphologyEx(dark, cv2.MORPH_OPEN, np.ones((60, 1), np.uint8))
rules = cv2.dilate(horizontal | vertical, np.ones((3, 3), np.uint8), iterations=1)
```

`rules` = 页面上的表格线/长直线。核长 60px（200dpi 下约 1cm）足以把线留下、把字笔画滤掉。

判定某组是否在表格里，并据此选掩码方式：

```python
scale_x, scale_y = pixmap.width / page.rect.width, pixmap.height / page.rect.height
in_table = False
if bbox.width < 250:                     # 宽段落一般是正文，不在表格里
    band = int(14 * scale_x)
    for edge in (int(bbox.x0*scale_x), int(bbox.x1*scale_x)):
        xa, xb = max(0, edge-band), min(pixmap.width, edge+band)
        if vertical[y0:y1, xa:xb].any():
            in_table = True; break

for rect in group.cover_rects:
    if in_table:                         # 只掩墨迹，保住单元格底色与线内侧
        area = _expand(rect, 2.0)
        region = gray[ry0:ry1, x0:x1]
        background = np.percentile(region, 80)         # 80 分位当纸色（避开墨）
        difference = np.abs(region.astype(np.int16) - int(background))
        local = (difference > 28).astype(np.uint8) * 255
        mask[ry0:ry1, x0:x1] = np.maximum(mask[ry0:ry1, x0:x1], local)
    else:                                # 正文：整行矩形全掩
        mask[ry0:ry1, x0:x1] = 255

mask[rules > 0] = 0                                        # ①
mask = cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=2)
mask[rules > 0] = 0                                        # ②
cleaned = cv2.inpaint(image, mask, 4, cv2.INPAINT_TELEA)
ok, encoded = cv2.imencode(".png", cv2.cvtColor(cleaned, cv2.COLOR_RGB2BGR))
return encoded.tobytes() if ok else None
```

- **`mask[rules>0]=0` 要做两次**：dilate 前把线排除，但 `iterations=2` 会把掩码重新吃进线 1–2px，所以 dilate 后再清一次；否则表格线被 inpaint 啃断。
- 墨迹阈值 28 + 80 分位背景：值调高会残留字影（灰影），调低会把纸张纹理当字 inpaint 掉（纸纹消失）。
- inpaint 半径 4、TELEA 是实测组合；半径过大在小字体密集区会串墨。
- 整段 `try/except` 返回 `None`：缺 `cv2`/`numpy` 或内存不足时，调用方必须降级到"底色覆盖"，不能整个任务失败。

## 右半页组装

```python
scan_image = _clean_scanned_page(page, [g for g, _, _ in placements])
...
new_page.insert_image(right_rect, stream=scan_image, keep_proportion=False)
for group, translated, size in placements:
    if _insert_translation_text(new_page, group, right_x, translated, size):
        drawn += 1
    else:
        fit_failures += 1
```

- `keep_proportion=False` 是必须的：图片由同一页按 200dpi 生成，宽高与 `right_rect` 一致，保持比例会留白边导致译文与纸面错位。
- 译文用 `right_x` 偏移直接叠在整页图上，**不画覆盖矩形**（图已擦干净，画矩形会出现白块——这是扫描分支和文字分支最大的差别）。
- `scan_image is None` → 退回 `show_pdf_page(right_rect, doc, idx)` + `_draw_translation`（底色覆盖），仍会写译文。

## 降级与提示

| 情况 | 行为 |
|---|---|
| `ocr_enabled=False` 且遇到扫描页 | 日志`第 N 页是扫描件，已跳过 OCR（保留原页）`，mode=`copy` |
| OCR 抛异常 | 日志带 `type(exc).__name__`，该页 mode=`copy` |
| 全是扫描页且关了 OCR | 抛 `这份 PDF 是扫描件，需要开启 OCR 才能翻译。` |
| RapidOCR 只认中英 | 非中英扫描件需在日志说明，别宣称支持全语种 |

验收要点：擦除处应能看到纸张纹理连续、表格线无断口、无纯白矩形；若某行原文仍可见，多半是该组被 `in_table` 误判走了墨迹掩码而阈值 28 太高，或 `OCR_MIN_SCORE` 把该行滤掉了（分数低但确实有字）。
