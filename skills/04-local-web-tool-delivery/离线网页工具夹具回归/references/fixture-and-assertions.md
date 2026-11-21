# 夹具生成与页面内断言模板

把 `<项目>` 换成被测目录，`<fn>` 换成实际函数名。**先读源码确认函数名与入参**，模板里的名字只是常见形态，不要照抄。

## 1. 夹具生成（复用应用自带的 SheetJS）

不要为测试新装依赖，直接 `require` 被测页 `vendor/` 里那份，保证生成的 xlsx 与应用解析的是同一版本格式。

```js
// make-fixtures.cjs  —  node make-fixtures.cjs
const XLSX = require('<项目>/vendor/xlsx.full.min.js');
const fs = require('fs');
const path = require('path');

const out = process.env.FIXTURE_DIR || path.join(require('os').tmpdir(), 'tool-fixtures');
fs.mkdirSync(out, { recursive: true });

function write(name, sheets) {
  const wb = XLSX.utils.book_new();
  sheets.forEach((s) => {
    const ws = XLSX.utils.aoa_to_sheet(s.aoa);
    if (s.merges) ws['!merges'] = s.merges;          // 合并单元格靠这个，不是靠空单元格
    XLSX.utils.book_append_sheet(wb, ws, s.name);
  });
  fs.writeFileSync(path.join(out, name), XLSX.write(wb, { type: 'buffer', bookType: 'xlsx' }));
}

// 合并单元格：名称列 r2:0 与 r3:0 合成一格，只有首行有值
write('merged.xlsx', [{
  name: '应收账款底稿',
  aoa: [
    ['企业名称', '业务摘要', '金额（元）'],
    ['北京华信科技有限公司', '9月货款', 100000],
    ['', '9月补记', 20000],                       // 逻辑上属于上一行
    ['合计', '', 120000],
  ],
  merges: [{ s: { r: 1, c: 0 }, e: { r: 2, c: 0 } }],
}]);
```

必须凑齐的边界样本（每样一个文件，命名可辨）：合并单元格续行、仅表名含方向、表头上方带标题行、表内含方向列、方向列留空、负数/红字、GBK 编码 CSV、带合计行、只有文件名能推断方向。CSV 写 GBK 用 `new TextEncoder()` 不行，直接 `Buffer.from(text, 'gbk')`（Node 支持 gbk）。

金额一律用整数、可心算的组合（如 100000 / 20000 / 120000），期望值写死在断言里。

## 2. 页面内免点击回归（`browser-use__evaluate_script`）

一次一段、每段有返回值。**不要**返回整个 `state`。

```js
// 段 1：探测全局是否真的可用（脚本被 module/IIFE 封装时这里就会露馅）
JSON.stringify(['handleFiles', 'runReconciliation', 'buildExportWorkbook']
  .map((n) => n + ':' + typeof window[n]));

// 段 2：导入一份夹具
(async () => {
  const url = 'http://127.0.0.1:<port>/' + encodeURI('merged.xlsx');   // 中文名必须 encodeURI
  const buf = await (await fetch(url)).arrayBuffer();
  const file = new File([buf], 'merged.xlsx');
  await window.handleFiles([file]);                                    // <fn>：应用的文件入口
  return JSON.stringify({
    sources: window.state.sources.length,
    records: window.state.sources.map((s) => s.records && s.records.length),
  });
})();

// 段 3：跑计算并断言精简指标
(() => {
  window.runReconciliation();                                          // <fn>：应用的计算入口
  const g = window.state.groups || [];
  return JSON.stringify({
    groups: g.length,
    net: g.map((x) => [x.name, x.recv, x.pay]),                       // 逐组净额，期望值来自夹具
    inherited: g.reduce((n, x) => n + (x.rows || []).filter((r) => r.inherited).length, 0),
    skipped: (window.state.skipped || []).map((s) => s.reason),
    companies: g.map((x) => x.name),                                  // 断言归属，不只看笔数
  });
})();
```

断言的公司名列表是必需项：只核笔数的话，"续行被当成新企业"这类错误会全绿通过。

## 3. 导出闭环（不产生真实下载）

```js
(() => {
  const captured = [];
  const real = XLSX.writeFile;
  XLSX.writeFile = (wb, name) => { captured.push({ wb, name }); };     // 劫持唯一写盘出口
  window.exportResults();                                              // <fn>：应用的导出入口
  XLSX.writeFile = real;
  if (!captured.length) return JSON.stringify({ FAIL: 'export never reached writeFile' });
  const { wb, name } = captured[0];
  const dump = wb.SheetNames.map((sn) => [sn, XLSX.utils.sheet_to_json(wb.Sheets[sn], { header: 1 }).slice(0, 2)]);
  return JSON.stringify({ name, sheets: wb.SheetNames, head: dump });   // 断言文件名/sheet/列头
})();
```

闭环那一步：把捕获的 workbook 重新 `XLSX.write(wb, {type:'array'})` 成字节，`new File` 后回灌第 2 段的导入入口，比对与页面结果一致——这同时验证"导出格式"和"导入能吃自己导出的东西"。

## 4. 报告口径

如实区分三类：函数级断言通过、界面渲染截图通过、真实浏览器下载动作未覆盖。最后一条除非真点过，否则不要写成"导出已实测"。
