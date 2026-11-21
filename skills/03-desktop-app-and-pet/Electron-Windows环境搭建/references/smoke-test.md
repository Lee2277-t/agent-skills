# Electron 截图与点击自检

用环境变量开关把截图、模拟点击和状态断言塞进主进程，跑完自动退出。适用于透明窗口、无边框桌宠、托盘应用等“人不在场也要确认能渲染”的场景。

## 约定

- 开关：`SMOKE_TEST=1`。
- 产物目录：项目下 `.dev/`。
- 结果文件：`.dev/smoke-result.json`，必须是合法 JSON，`ok` 为布尔值。
- 截图：`.dev/smoke-before.png`、`.dev/smoke-after.png`。
- 控制台标记：`SMOKE_OK`、`SMOKE_STATE ...`、`SMOKE_FAIL ...`。
- 退出码：0 成功，1 异常，2 超时。

## 主进程模板

把下面代码放进 `main.js`，按实际入口调整 `loadFile` 与断言字段。

```js
const { app, BrowserWindow } = require('electron');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const SMOKE = process.env.SMOKE_TEST === '1';

if (SMOKE) {
  app.setPath('userData', path.join(os.tmpdir(), `electron-smoke-${process.pid}`));
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function writeSmokeResult(result) {
  const dir = path.join(__dirname, '.dev');
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, 'smoke-result.json'), JSON.stringify(result, null, 2));
}

async function runSmoke(win) {
  const hardTimeout = setTimeout(() => {
    writeSmokeResult({ ok: false, error: 'timeout' });
    console.error('SMOKE_FAIL timeout');
    app.exit(2);
  }, 30000);

  try {
    await new Promise((resolve) => win.webContents.once('did-finish-load', resolve));
    await delay(600);

    const dir = path.join(__dirname, '.dev');
    fs.mkdirSync(dir, { recursive: true });

    const before = await win.webContents.capturePage();
    fs.writeFileSync(path.join(dir, 'smoke-before.png'), before.toPNG());

    const bitmap = before.toBitmap();
    const pixels = bitmap.length / 4;
    let transparent = 0;
    for (let i = 3; i < bitmap.length; i += 4) {
      if (bitmap[i] === 0) transparent += 1;
    }

    const target = await win.webContents.executeJavaScript(`(() => {
      const el = document.querySelector('[data-smoke-target]') || document.body;
      const rect = el.getBoundingClientRect();
      return {
        x: Math.round(rect.left + rect.width / 2),
        y: Math.round(rect.top + rect.height / 2)
      };
    })()`);

    win.webContents.sendInputEvent({ type: 'mouseMove', x: target.x, y: target.y });
    await delay(80);
    win.webContents.sendInputEvent({
      type: 'mouseDown', x: target.x, y: target.y, button: 'left', clickCount: 1
    });
    win.webContents.sendInputEvent({
      type: 'mouseUp', x: target.x, y: target.y, button: 'left', clickCount: 1
    });
    await delay(350);

    const state = await win.webContents.executeJavaScript(
      `window.__smokeState ? window.__smokeState() : (document.body.dataset.smokeState || null)`
    );

    const after = await win.webContents.capturePage();
    fs.writeFileSync(path.join(dir, 'smoke-after.png'), after.toPNG());

    const result = {
      ok: true,
      transparentRatio: transparent / pixels,
      target,
      state
    };
    writeSmokeResult(result);
    console.log('SMOKE_STATE', JSON.stringify(result));
    console.log('SMOKE_OK');
    clearTimeout(hardTimeout);
    app.exit(0);
  } catch (error) {
    writeSmokeResult({ ok: false, error: String((error && error.stack) || error) });
    console.error('SMOKE_FAIL', (error && error.stack) || error);
    clearTimeout(hardTimeout);
    app.exit(1);
  }
}

function createWindow() {
  const win = new BrowserWindow({
    width: 320,
    height: 360,
    show: true,
    webPreferences: { contextIsolation: true, nodeIntegration: false }
  });

  // 必须在 loadFile 之前调用：runSmoke 先挂 did-finish-load 监听。
  if (SMOKE) runSmoke(win);

  win.loadFile(path.join(__dirname, 'src', 'index.html'));
}
```

## 单实例处理

应用如果用了 `requestSingleInstanceLock()`，自检会被已在运行的实例挡掉。二选一：

```js
// 方案 A：自检时跳过单实例锁
if (!SMOKE && !app.requestSingleInstanceLock()) {
  app.quit();
}
```

```js
// 方案 B：保留锁，但在启动自检前关闭已有实例
// （不需要代码改动）
```

模板里的临时 `userData` 还能避免自检污染真实配置和存档。

## 渲染层约定

1. 给要点的元素加 `data-smoke-target`，例如宠物本体或主按钮。
2. 暴露只读状态函数，返回布尔值/数字/短字符串，不要返回 DOM：

```js
window.__smokeState = () => ({
  bubbleVisible: document.getElementById('bubble')?.classList.contains('show') || false,
  hearts: document.querySelectorAll('.heart').length
});
```

3. 点击后状态必须有可观察变化；否则只能证明“点到了”，不能证明“功能生效”。

## 运行

Git Bash：

```bash
mkdir -p .dev
rm -f .dev/smoke-result.json
SMOKE_TEST=1 "./node_modules/electron/dist/electron.exe" . > .dev/smoke.log 2>&1
status=$?
cat .dev/smoke-result.json
echo "exit=$status"
```

Windows GUI 进程从 shell 立即返回时，用 PowerShell 等待：

```powershell
$env:SMOKE_TEST = "1"
$p = Start-Process -FilePath ".\node_modules\electron\dist\electron.exe" -ArgumentList "." `
  -PassThru -Wait `
  -RedirectStandardOutput ".dev\smoke.out" `
  -RedirectStandardError ".dev\smoke.err"
$p.ExitCode
Get-Content .dev\smoke-result.json
```

## 通过条件

- 退出码为 0。
- `.dev/smoke-result.json` 存在且 `ok` 为 `true`。
- `smoke-before.png` 与 `smoke-after.png` 都存在且非空。
- 透明窗口的 `transparentRatio` 大于 0；不透明窗口为 0 属正常。
- `state` 中至少一个字段在点击后发生了预期变化。
- 日志出现 `SMOKE_OK`，没有 `SMOKE_FAIL`。

## 判读与排错

- 截图在图片查看器里显示白底不代表不透明；看 `transparentRatio` 或 PNG alpha。
- 截图全空白：确认窗口没有被最小化，尝试 `show: true` / `showInactive()`，或给 `BrowserWindow` 加 `paintWhenInitiallyHidden: true`。
- `transparentRatio` 为 0：检查 `BrowserWindow({ transparent: true })`、页面根节点背景和 `hasShadow`。
- 结果文件没生成：主进程可能没走到 `did-finish-load`，或 GUI 进程崩溃；先看 `.dev/smoke.log` / `.dev/smoke.err`。
- 进程不退出：`app.quit()` 被窗口拦截；自检分支用 `app.exit()`，并保留超时兜底。
- 点击无效：确认坐标是 CSS 像素、目标在视口内、窗口未忽略鼠标事件；`sendInputEvent` 只验证渲染层交互，不验证系统级鼠标穿透。
- 首帧较慢时把 600ms 等待和 30s 超时适当调大，不要用无限等待。

## 必须人工确认

截图和模拟点击无法覆盖：真实拖拽、系统级鼠标穿透、置顶层级、托盘菜单、多显示器、开机自启、SmartScreen 首次运行。汇报时单独列出。
