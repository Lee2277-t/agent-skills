# Electron 桌宠最小版：代码骨架与验收

## 文件布局

```text
<app>/
├── main.js
├── preload.js
├── package.json
├── scripts/
│   └── smoke-test.cjs        # 从本 Skill 的 scripts/ 复制
├── src/
│   ├── index.html
│   ├── renderer.js
│   └── style.css
└── 启动桌宠.cmd               # 可选
```

`package.json` 固定 Electron 版本；示例基线是 44.9.3。

```json
{
  "name": "desktop-pet-mvp",
  "version": "0.1.0",
  "private": true,
  "main": "main.js",
  "scripts": { "start": "electron ." },
  "devDependencies": { "electron": "44.9.3" }
}
```

## 环境 fallback

优先使用 `electron-windows-bootstrap` Skill 的脚本。没有该 Skill 时，按下面顺序手动处理：

```bash
# 1) 便携 Node（放在项目 .dev，不动 PATH）
#    从 https://nodejs.org/dist/ 或 https://npmmirror.com/mirrors/node/ 下载
#    node-v24.18.0-win-x64.zip，核对 SHASUMS256.txt 后解压到 .dev/node

# 2) 安装依赖，显式使用便携 Node 的 npm-cli.js
.dev/node/node.exe .dev/node/node_modules/npm/bin/npm-cli.js install \
  --registry=https://registry.npmmirror.com --no-audit --no-fund

# 3) Electron 44 不会自动下载 dist
.dev/node/node.exe node_modules/electron/install.js

# 4) 验证
.dev/node/node.exe -v
node_modules/electron/dist/electron.exe --version
```

失败时报告具体原因，不要关闭 checksum，也不要改系统 PATH。

## main.js

```js
const { app, BrowserWindow, Menu, ipcMain, screen } = require('electron');
const path = require('node:path');
const fs = require('node:fs');

const IS_SMOKE = process.env.PET_SMOKE === '1';
const WIN_WIDTH = 280;
const WIN_HEIGHT = 320;
const EDGE_MARGIN = 24;

if (IS_SMOKE) {
  app.setPath('userData', path.join(app.getPath('temp'), `desktop-pet-smoke-${process.pid}`));
}

let win = null;
let isDragging = false;
let dragOffset = null;
let dragTimer = null;
let ignoreMouse = true;

if (IS_SMOKE || app.requestSingleInstanceLock()) {
  if (!IS_SMOKE) {
    app.on('second-instance', () => {
      if (win) win.showInactive();
    });
  }

  app.whenReady().then(() => {
    registerIpc();
    createWindow();
    if (IS_SMOKE) {
      require('./scripts/smoke-test.cjs').installSmokeTest({
        app,
        getWindow: () => win,
        options: {
          outputDir: path.join(__dirname, '.dev'),
          cleanupUserData: true,
        },
      });
    }
  });

  app.on('before-quit', () => {
    if (!IS_SMOKE) savePosition();
  });
  app.on('window-all-closed', () => app.quit());
} else {
  app.quit();
}

function statePath() {
  return path.join(app.getPath('userData'), 'pet-state.json');
}

function defaultPosition() {
  const { workArea } = screen.getPrimaryDisplay();
  return {
    x: workArea.x + workArea.width - WIN_WIDTH - EDGE_MARGIN,
    y: workArea.y + workArea.height - WIN_HEIGHT - EDGE_MARGIN,
  };
}

function savedPosition() {
  try {
    const data = JSON.parse(fs.readFileSync(statePath(), 'utf8'));
    if (!Number.isFinite(data.x) || !Number.isFinite(data.y)) return null;
    const visible = screen.getAllDisplays().some(({ workArea }) => (
      data.x + WIN_WIDTH > workArea.x + 80 &&
      data.x < workArea.x + workArea.width - 80 &&
      data.y + WIN_HEIGHT > workArea.y + 80 &&
      data.y < workArea.y + workArea.height - 40
    ));
    return visible ? { x: data.x, y: data.y } : null;
  } catch {
    return null;
  }
}

function savePosition() {
  if (!win) return;
  const [x, y] = win.getPosition();
  try {
    fs.mkdirSync(path.dirname(statePath()), { recursive: true });
    fs.writeFileSync(statePath(), JSON.stringify({ x, y }));
  } catch {
    // Position persistence is optional; never block the pet on a failed write.
  }
}

function clampPosition(x, y) {
  const { workArea } = screen.getDisplayNearestPoint({ x, y });
  return {
    x: Math.min(Math.max(x, workArea.x - WIN_WIDTH + 80), workArea.x + workArea.width - 80),
    y: Math.min(Math.max(y, workArea.y), workArea.y + workArea.height - WIN_HEIGHT + 40),
  };
}

function createWindow() {
  const pos = savedPosition() || defaultPosition();

  win = new BrowserWindow({
    width: WIN_WIDTH,
    height: WIN_HEIGHT,
    x: pos.x,
    y: pos.y,
    show: false,
    transparent: true,
    backgroundColor: '#00000000',
    frame: false,
    resizable: false,
    maximizable: false,
    minimizable: false,
    fullscreenable: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    hasShadow: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  win.setIgnoreMouseEvents(true, { forward: true });
  win.loadFile(path.join(__dirname, 'src', 'index.html'));
  win.once('ready-to-show', () => win.showInactive());
  win.on('closed', () => {
    clearInterval(dragTimer);
    dragTimer = null;
    dragOffset = null;
    isDragging = false;
    win = null;
  });
}

function registerIpc() {
  ipcMain.on('pet:set-ignore', (_event, ignore) => {
    if (!win || isDragging) return;
    const next = Boolean(ignore);
    if (next === ignoreMouse) return;
    ignoreMouse = next;
    win.setIgnoreMouseEvents(next, { forward: true });
  });

  ipcMain.on('pet:drag-start', () => {
    if (!win) return;
    isDragging = true;
    ignoreMouse = false;
    win.setIgnoreMouseEvents(false);

    const cursor = screen.getCursorScreenPoint();
    const [x, y] = win.getPosition();
    dragOffset = { x: cursor.x - x, y: cursor.y - y };

    clearInterval(dragTimer);
    dragTimer = setInterval(() => {
      if (!win || !dragOffset) return;
      const point = screen.getCursorScreenPoint();
      const next = clampPosition(point.x - dragOffset.x, point.y - dragOffset.y);
      win.setPosition(next.x, next.y);
    }, 16);
  });

  ipcMain.on('pet:drag-end', () => {
    if (!win) return;
    clearInterval(dragTimer);
    dragTimer = null;
    dragOffset = null;
    isDragging = false;
    ignoreMouse = false;
    win.setIgnoreMouseEvents(false);
    savePosition();
  });

  ipcMain.on('pet:context-menu', () => {
    if (!win) return;
    Menu.buildFromTemplate([
      { label: '说句话', click: () => win?.webContents.send('pet:say') },
      {
        label: '回到右下角',
        click: () => {
          const pos = defaultPosition();
          win?.setPosition(pos.x, pos.y);
          savePosition();
        },
      },
      { type: 'separator' },
      { label: '退出', click: () => app.quit() },
    ]).popup({ window: win });
  });
}
```

## preload.js

```js
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('petAPI', {
  setIgnore: (ignore) => ipcRenderer.send('pet:set-ignore', ignore),
  dragStart: () => ipcRenderer.send('pet:drag-start'),
  dragEnd: () => ipcRenderer.send('pet:drag-end'),
  contextMenu: () => ipcRenderer.send('pet:context-menu'),
  onSay: (callback) => ipcRenderer.on('pet:say', () => callback()),
});
```

## src/index.html

占位形象只负责让点击和 alpha 自检可测，正式形象按 `desktop-pet-character-design` 替换。

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta http-equiv="Content-Security-Policy" content="default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:;" />
  <title>桌宠</title>
  <link rel="stylesheet" href="style.css" />
</head>
<body>
  <main id="stage">
    <div id="speech" class="speech" role="status" aria-live="polite"></div>

    <div id="pet" aria-label="桌宠">
      <svg viewBox="0 0 200 220" xmlns="http://www.w3.org/2000/svg">
        <ellipse cx="100" cy="208" rx="48" ry="7" fill="#4A3226" opacity="0.12" />
        <g class="tail">
          <path d="M 145 175 C 180 185 190 155 176 138" fill="none" stroke="#E8B98E" stroke-width="14" stroke-linecap="round" />
        </g>
        <ellipse cx="100" cy="160" rx="54" ry="44" fill="#F0C39B" />
        <ellipse cx="100" cy="172" rx="30" ry="24" fill="#FFE7CF" />
        <path d="M 58 75 C 50 48 55 28 66 24 C 78 22 92 45 97 58 Z" fill="#F0C39B" />
        <path d="M 142 75 C 150 48 145 28 134 24 C 122 22 108 45 103 58 Z" fill="#F0C39B" />
        <path d="M 66 60 C 62 44 65 34 70 32 C 77 31 85 45 89 55 Z" fill="#E79A9A" />
        <path d="M 134 60 C 138 44 135 34 130 32 C 123 31 115 45 111 55 Z" fill="#E79A9A" />
        <circle cx="100" cy="98" r="56" fill="#F7D8B8" />
        <ellipse cx="60" cy="118" rx="10" ry="5" fill="#EE9E9E" opacity="0.55" />
        <ellipse cx="140" cy="118" rx="10" ry="5" fill="#EE9E9E" opacity="0.55" />
        <g class="eye" data-eye>
          <ellipse cx="79" cy="100" rx="7" ry="9" fill="#3B2A24" />
          <circle cx="76.5" cy="97" r="2.4" fill="#FFFFFF" />
        </g>
        <g class="eye" data-eye>
          <ellipse cx="121" cy="100" rx="7" ry="9" fill="#3B2A24" />
          <circle cx="118.5" cy="97" r="2.4" fill="#FFFFFF" />
        </g>
        <path d="M 96 111 Q 100 108 104 111 Q 102 115 100 115 Q 98 115 96 111 Z" fill="#D98282" />
        <path d="M 100 115 L 100 118 M 100 118 Q 96 122 93 119 M 100 118 Q 104 122 107 119" stroke="#6B4A3A" stroke-width="1.6" fill="none" stroke-linecap="round" />
      </svg>
    </div>
  </main>

  <script src="renderer.js"></script>
</body>
</html>
```

## src/renderer.js

```js
const pet = document.getElementById('pet');
const speech = document.getElementById('speech');

const CLICK_LINES = ['在呢在呢', '别戳我啦~', '陪你一会儿', '今天也要加油'];
const DROP_LINES = ['呼~落地了', '这里也不错'];

let speechTimer = null;
let pokeTimer = null;
let down = null;
let dragging = false;
let lastOver = null;

function pick(list) {
  return list[Math.floor(Math.random() * list.length)];
}

function showSpeech(text) {
  speech.textContent = text;
  speech.classList.remove('show');
  void speech.offsetWidth;
  speech.classList.add('show');
  clearTimeout(speechTimer);
  speechTimer = setTimeout(() => speech.classList.remove('show'), 2800);
}

function react() {
  pet.classList.remove('poke');
  void pet.offsetWidth;
  pet.classList.add('poke');
  clearTimeout(pokeTimer);
  pokeTimer = setTimeout(() => pet.classList.remove('poke'), 600);
  showSpeech(pick(CLICK_LINES));
}

function scheduleBlink() {
  setTimeout(() => {
    document.querySelectorAll('[data-eye]').forEach((eye) => eye.classList.add('blink'));
    setTimeout(() => {
      document.querySelectorAll('[data-eye]').forEach((eye) => eye.classList.remove('blink'));
      scheduleBlink();
    }, 120);
  }, 2600 + Math.random() * 3600);
}

function isOverPet(x, y) {
  const el = document.elementFromPoint(x, y);
  return Boolean(el && el.closest('#pet'));
}

window.addEventListener('mousemove', (event) => {
  if (down) return;
  const over = isOverPet(event.clientX, event.clientY);
  if (over === lastOver) return;
  lastOver = over;
  window.petAPI.setIgnore(!over);
});

pet.addEventListener('pointerdown', (event) => {
  if (event.button !== 0) return;
  down = { x: event.screenX, y: event.screenY, pointerId: event.pointerId };
  dragging = false;
  try {
    pet.setPointerCapture(event.pointerId);
  } catch {
    // Synthetic test clicks may not have an active pointer.
  }
});

window.addEventListener('pointermove', (event) => {
  if (!down) return;
  if (!dragging && Math.hypot(event.screenX - down.x, event.screenY - down.y) > 4) {
    dragging = true;
    pet.classList.remove('poke');
    pet.classList.add('dragging');
    speech.classList.remove('show');
    window.petAPI.dragStart();
  }
});

function finishPointer(event) {
  if (!down) return;
  const wasDragging = dragging;
  try {
    pet.releasePointerCapture(event.pointerId);
  } catch {
    // The pointer may already be released.
  }
  down = null;
  dragging = false;
  pet.classList.remove('dragging');

  if (wasDragging) {
    window.petAPI.dragEnd();
    window.petAPI.setIgnore(false);
    lastOver = true;
    showSpeech(pick(DROP_LINES));
  } else {
    react();
  }
}

window.addEventListener('pointerup', finishPointer);
window.addEventListener('pointercancel', finishPointer);

pet.addEventListener('contextmenu', (event) => {
  event.preventDefault();
  window.petAPI.contextMenu();
});

window.petAPI.onSay(() => {
  showSpeech(pick(CLICK_LINES));
});

scheduleBlink();
```

## src/style.css

```css
* { box-sizing: border-box; }

html,
body {
  width: 100%;
  height: 100%;
  margin: 0;
  overflow: hidden;
  background: transparent;
  user-select: none;
  -webkit-user-select: none;
}

body {
  font-family: "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif;
}

#stage {
  position: relative;
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  padding-bottom: 4px;
}

#pet {
  width: 200px;
  height: auto;
  cursor: grab;
  pointer-events: none;
  transform-origin: 50% 92%;
  animation: breathe 3.4s ease-in-out infinite;
  transition: transform 0.15s ease;
  will-change: transform;
}

#pet svg {
  display: block;
  width: 100%;
  height: auto;
  overflow: visible;
  pointer-events: none;
}

#pet svg * {
  cursor: grab;
  pointer-events: visiblePainted;
}

#pet.dragging {
  cursor: grabbing;
  animation: none;
  transform: scale(1.04) rotate(-2deg);
}

#pet.poke {
  animation: poke 0.55s cubic-bezier(0.34, 1.56, 0.64, 1);
}

@keyframes breathe {
  0%, 100% { transform: translateY(0) scale(1); }
  50% { transform: translateY(-2px) scale(1.012, 0.99); }
}

@keyframes poke {
  0% { transform: scale(1); }
  30% { transform: scale(1.06, 0.94); }
  60% { transform: scale(0.97, 1.05); }
  100% { transform: scale(1); }
}

.tail {
  transform-box: fill-box;
  transform-origin: 10% 80%;
  animation: tail-sway 3.2s ease-in-out infinite alternate;
}

@keyframes tail-sway {
  from { transform: rotate(-6deg); }
  to { transform: rotate(7deg); }
}

[data-eye] {
  transform-box: fill-box;
  transform-origin: center;
  transition: transform 0.09s ease;
}

[data-eye].blink { transform: scaleY(0.08); }

.speech {
  position: relative;
  max-width: 230px;
  margin-bottom: 2px;
  padding: 9px 15px;
  border-radius: 16px;
  background: #FFFDF8;
  color: #6B4B3A;
  font-size: 14px;
  line-height: 1.45;
  text-align: center;
  box-shadow: 0 6px 18px rgba(90, 60, 30, 0.14);
  opacity: 0;
  transform: translateY(8px) scale(0.92);
  transition: opacity 0.18s ease, transform 0.22s cubic-bezier(0.34, 1.56, 0.64, 1);
  pointer-events: none;
  white-space: pre-wrap;
}

.speech::after {
  content: "";
  position: absolute;
  left: 50%;
  bottom: -6px;
  width: 12px;
  height: 12px;
  background: #FFFDF8;
  border-radius: 2px;
  transform: translateX(-50%) rotate(45deg);
}

.speech.show {
  opacity: 1;
  transform: translateY(0) scale(1);
}
```

## 启动桌宠.cmd

```bat
@echo off
cd /d "%~dp0"
if not exist "node_modules\electron\dist\electron.exe" (
  echo Electron runtime is missing. Please reinstall dependencies.
  pause
  exit /b 1
)
start "" "node_modules\electron\dist\electron.exe" .
```

## 冒烟自检接线

1. 把本 Skill 的 `scripts/smoke-test.cjs` 复制到应用的 `scripts/smoke-test.cjs`。
2. 按 `main.js` 示例，在 `PET_SMOKE=1` 时调用 `installSmokeTest`。
3. 在自检模式下跳过单实例锁，并把 `userData` 指到临时目录；脚本只清理名称含 `smoke` 的临时目录。
4. 用 `SKILL.md` 里的 PowerShell 命令启动，读取 `.dev/smoke-report.json`。

## 已验证基线与边界

本骨架已在 Windows 10.0.26300、Electron 44.9.3、Chromium 152、系统缩放 200% 下跑通：

```text
SMOKE_PASS {"cornerAlphaMax":0,"petOpaqueRatio":0.424951399249514,"clickAssertion":true}
```

验证内容：四角 alpha=0；宠物框内 42.5% 像素不透明；合成点击后 `#speech.show` 为真；无 console/render 错误；退出码 0。

未自动验证：真实拖拽手感、系统级鼠标穿透、始终置顶层级、重启位置恢复、多显示器行为。这些必须人工确认。

## 追加排查

- **高 DPI**：`capturePage()` 返回物理像素，`sendInputEvent()` 使用 DIP。用 `win.getContentSize()` 归一化截图并据此采样，否则 200% 缩放下点击会偏。
- **点击落点**：不要固定点窗口中心；先按选择器取宠物框，再从 alpha>200 的像素中找靠近质心的点，避免点到透明区域。
- **预览白底**：图片查看器会把透明区域显示成白色；必须读 alpha，不能目测。
- **单实例锁**：自检实例会被正在运行的桌宠顶掉；自检模式跳过锁并隔离 `userData`。
- **指针捕获**：`setPointerCapture`/`releasePointerCapture` 在没有活动指针时会抛错；必须 `try/catch`。
- **命中区**：`pointer-events: visiblePainted` 让透明像素不挡桌面；若改成整块元素命中，透明角落也会拦截鼠标。
- **拖拽与穿透**：拖拽期间主进程忽略 `set-ignore`，结束后恢复；否则拖到一半窗口会开始穿透。
- **动画恢复**：一次性 `poke` class 会覆盖常驻呼吸动画，动画结束要移除。
