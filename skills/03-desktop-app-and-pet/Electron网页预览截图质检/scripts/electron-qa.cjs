#!/usr/bin/env node
'use strict';

// Electron CLI quirk: a URL-like argument followed by any other argument makes
// Electron exit 127 before this script loads. Always pass --url LAST.
// Usage: electron electron-qa.cjs --out <dir> [options] --url <url>
const { app, BrowserWindow, screen } = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { pathToFileURL } = require('node:url');

const CONSOLE_NOISE = [
  /Electron Security Warning/i,
  /DevTools failed to load source map/i,
  /Autofill\./i,
];

const opts = parseArgs(process.argv.slice(2));

if (!opts.url || !opts.out) {
  console.error('QA_FAILED missing --url or --out');
  console.error('Usage: electron electron-qa.cjs --out <dir> --width 1280 --height 900 [--mobile] [--mobile-only] ... --url <url|file>');
  process.exit(2);
}

const outDir = path.resolve(opts.out);
const reportPath = path.resolve(opts.report || path.join(outDir, 'report.json'));
const userDataDir = path.resolve(opts.userDataDir || path.join(outDir, 'userdata'));

try {
  fs.mkdirSync(outDir, { recursive: true });
  fs.mkdirSync(userDataDir, { recursive: true });
  fs.mkdirSync(path.dirname(reportPath), { recursive: true });
  fs.writeFileSync(path.join(outDir, 'qa.pid'), String(process.pid), 'utf8');
} catch (error) {
  console.error('QA_FAILED cannot prepare output directory: ' + error.message);
  process.exit(2);
}

// Keep QA rendering alive even when the window loses focus.
app.commandLine.appendSwitch('disable-background-timer-throttling');
app.commandLine.appendSwitch('disable-renderer-backgrounding');
app.commandLine.appendSwitch('disable-backgrounding-occluded-windows');
app.setPath('userData', userDataDir);

const startedAt = new Date().toISOString();
const targetUrl = normalizeUrl(opts.url);

const report = {
  ok: false,
  startedAt,
  finishedAt: null,
  pid: process.pid,
  inputUrl: opts.url,
  resolvedUrl: targetUrl,
  outDir,
  reportPath,
  userDataDir,
  electron: process.versions.electron,
  chrome: process.versions.chrome,
  node: process.versions.node,
  platform: process.platform,
  options: {
    width: opts.width,
    height: opts.height,
    mobile: opts.mobile,
    mobileOnly: opts.mobileOnly,
    mobileWidth: opts.mobileWidth,
    mobileHeight: opts.mobileHeight,
    settle: opts.settle,
    timeout: opts.timeout,
    scrollOffset: opts.scrollOffset,
    ignoreSelectors: opts.ignores,
  },
  window: null,
  desktop: null,
  mobile: null,
  screenshots: [],
  consoleErrors: [],
  consoleWarnings: [],
  warnings: [],
};

try {
  fs.writeFileSync(path.join(outDir, 'qa-meta.json'), JSON.stringify({
    pid: report.pid,
    script: __filename,
    argv: process.argv.slice(2),
    startedAt,
    outDir,
    userDataDir,
  }, null, 2), 'utf8');
} catch (error) {
  report.warnings.push('could not write qa-meta.json: ' + error.message);
}

let finished = false;
let win = null;
let shotCounter = 0;
const usedShotNames = new Set();

const watchdog = setTimeout(() => {
  if (finished) return;
  finished = true;
  report.ok = false;
  report.error = 'hard timeout after ' + opts.timeout + 'ms';
  report.finishedAt = new Date().toISOString();
  safeWriteReport();
  console.error('QA_TIMEOUT ' + opts.timeout + 'ms');
  console.log('QA_RESULT ' + reportPath);
  app.exit(2);
}, opts.timeout);

process.on('uncaughtException', (error) => finishError(error));
process.on('unhandledRejection', (error) => finishError(error));
app.on('window-all-closed', () => app.quit());
app.whenReady().then(run).catch(finishError);

async function run() {
  console.log('QA_PID ' + process.pid);
  console.log('QA_STEP create-window');

  const initial = opts.mobileOnly
    ? { width: opts.mobileWidth, height: opts.mobileHeight }
    : { width: opts.width, height: opts.height };
  const workArea = screen.getPrimaryDisplay().workArea;

  win = new BrowserWindow({
    width: initial.width,
    height: initial.height,
    x: workArea.x + Math.max(0, Math.floor((workArea.width - initial.width) / 2)),
    y: workArea.y + Math.max(0, Math.floor((workArea.height - initial.height) / 2)),
    useContentSize: true,
    show: true,
    skipTaskbar: true,
    autoHideMenuBar: true,
    backgroundColor: '#ffffff',
    webPreferences: {
      offscreen: false,
      backgroundThrottling: false,
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  win.setMenuBarVisibility(false);
  win.focus();
  win.webContents.focus();

  if (opts.mobileOnly) {
    win.setContentSize(opts.mobileWidth, opts.mobileHeight);
    placeWindow(win, opts.mobileWidth, opts.mobileHeight);
  }

  report.window = {
    requested: initial,
    actualContentSize: contentSize(win),
    workArea: { x: workArea.x, y: workArea.y, width: workArea.width, height: workArea.height },
  };
  checkSize(report.window.actualContentSize, initial, 'initial');

  attachEvents(win);

  try {
    await win.webContents.session.clearCache();
  } catch (error) {
    report.warnings.push('clearCache failed: ' + error.message);
  }

  console.log('QA_STEP load');
  await loadPage(win, targetUrl);
  await settlePage(win, opts.settle);
  await resetScroll(win);

  if (!opts.mobileOnly) {
    report.desktop = { metrics: null, shots: [], clicks: [] };
    console.log('QA_STEP desktop-top');
    await shoot(win, 'desktop-top');
    report.desktop.metrics = await metrics(win);

    for (const shot of opts.shots) {
      report.desktop.shots.push(await runShot(win, shot, false));
    }

    let blocked = false;
    for (const click of opts.clicks) {
      const result = await runClick(win, click, false);
      report.desktop.clicks.push(result);
      if (result.blocked) {
        blocked = true;
        report.warnings.push('desktop actions aborted after click timeout: ' + click.name);
        break;
      }
    }

    if (opts.mobile && !blocked) {
      await runMobile(win, targetUrl, true);
    } else if (opts.mobile && blocked) {
      report.warnings.push('mobile phase skipped because desktop renderer became unresponsive; rerun with --mobile-only');
    }
  } else {
    if (opts.clicks.length || opts.shots.length) {
      report.warnings.push('--mobile-only ignores --click/--shot; use --mobile-click/--mobile-shot');
    }
    await runMobile(win, targetUrl, false);
  }

  report.ok = true;
  report.finishedAt = new Date().toISOString();
  finish(0);
}

async function runMobile(browserWindow, url, reload) {
  report.mobile = { metrics: null, shots: [], clicks: [] };

  console.log('QA_STEP mobile-resize');
  browserWindow.setContentSize(opts.mobileWidth, opts.mobileHeight);
  placeWindow(browserWindow, opts.mobileWidth, opts.mobileHeight);
  report.window.mobileContentSize = contentSize(browserWindow);
  checkSize(report.window.mobileContentSize, { width: opts.mobileWidth, height: opts.mobileHeight }, 'mobile');

  if (reload) {
    await wait(300);
    console.log('QA_STEP mobile-load');
    await loadPage(browserWindow, url);
    await settlePage(browserWindow, opts.settle);
  }

  await resetScroll(browserWindow);
  console.log('QA_STEP mobile-top');
  await shoot(browserWindow, 'mobile-top');
  report.mobile.metrics = await metrics(browserWindow);

  for (const shot of opts.mobileShots) {
    report.mobile.shots.push(await runShot(browserWindow, shot, true));
  }

  let blocked = false;
  for (const click of opts.mobileClicks) {
    const result = await runClick(browserWindow, click, true);
    report.mobile.clicks.push(result);
    if (result.blocked) {
      blocked = true;
      report.warnings.push('mobile actions aborted after click timeout: ' + click.name);
      break;
    }
  }
  if (blocked) {
    report.warnings.push('mobile renderer became unresponsive; inspect the last QA_STEP and the report');
  }
}

function parseArgs(argv) {
  const options = {
    width: 1280,
    height: 900,
    settle: 800,
    timeout: 60000,
    scrollOffset: 24,
    mobileWidth: 390,
    mobileHeight: 844,
    mobile: false,
    mobileOnly: false,
    clicks: [],
    mobileClicks: [],
    shots: [],
    mobileShots: [],
    checks: [],
    ignores: [],
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    const next = () => {
      if (i + 1 >= argv.length) {
        console.error('QA_FAILED missing value for ' + arg);
        process.exit(2);
      }
      i += 1;
      return argv[i];
    };

    switch (arg) {
      case '--url':
        options.url = next();
        break;
      case '--out':
        options.out = next();
        break;
      case '--user-data-dir':
        options.userDataDir = next();
        break;
      case '--report':
        options.report = next();
        break;
      case '--width':
        options.width = positiveInt(next(), arg);
        break;
      case '--height':
        options.height = positiveInt(next(), arg);
        break;
      case '--settle':
        options.settle = nonNegativeInt(next(), arg);
        break;
      case '--timeout':
        options.timeout = positiveInt(next(), arg);
        break;
      case '--scroll-offset':
        options.scrollOffset = nonNegativeInt(next(), arg);
        break;
      case '--mobile-width':
        options.mobileWidth = positiveInt(next(), arg);
        break;
      case '--mobile-height':
        options.mobileHeight = positiveInt(next(), arg);
        break;
      case '--mobile':
        options.mobile = true;
        break;
      case '--mobile-only':
        options.mobile = true;
        options.mobileOnly = true;
        break;
      case '--click':
        options.clicks.push(parseAction(next()));
        break;
      case '--mobile-click':
        options.mobileClicks.push(parseAction(next()));
        break;
      case '--shot':
        options.shots.push(parseAction(next()));
        break;
      case '--mobile-shot':
        options.mobileShots.push(parseAction(next()));
        break;
      case '--check':
        options.checks.push(parseAction(next()));
        break;
      case '--ignore-selector':
        options.ignores.push(next());
        break;
      case '--help':
      case '-h':
        console.log('Usage: electron electron-qa.cjs --out <dir> --width 1280 --height 900 --settle 800 --shot name=selector --click name=selector --check name=selector --ignore-selector sel --mobile --mobile-only --mobile-width 390 --mobile-height 844 --mobile-shot name=selector --mobile-click name=selector --scroll-offset 24 --timeout 60000 --url <url|file>');
        process.exit(0);
        break;
      default:
        console.error('QA_FAILED unknown option ' + arg);
        process.exit(2);
    }
  }

  if (options.mobileClicks.length || options.mobileShots.length) options.mobile = true;
  if (options.mobileOnly) options.mobile = true;
  return options;
}

function parseAction(value) {
  const raw = String(value);
  const index = raw.indexOf('=');
  if (index > 0 && index < raw.length - 1) {
    const left = raw.slice(0, index);
    const right = raw.slice(index + 1);
    if (/^[A-Za-z0-9._-]+$/.test(left)) return { name: left, selector: right };
  }
  return { name: raw, selector: raw };
}

function positiveInt(value, flag) {
  const number = Number(value);
  if (!Number.isFinite(number) || number <= 0) {
    console.error('QA_FAILED ' + flag + ' must be a positive number');
    process.exit(2);
  }
  return Math.round(number);
}

function nonNegativeInt(value, flag) {
  const number = Number(value);
  if (!Number.isFinite(number) || number < 0) {
    console.error('QA_FAILED ' + flag + ' must be a non-negative number');
    process.exit(2);
  }
  return Math.round(number);
}

function normalizeUrl(input) {
  const raw = String(input);
  if (/^[a-zA-Z]:[\\/]/.test(raw)) return pathToFileURL(path.resolve(raw)).href;
  if (/^[a-z][a-z0-9+.-]*:/i.test(raw)) return raw;
  return pathToFileURL(path.resolve(raw)).href;
}

function contentSize(browserWindow) {
  const [width, height] = browserWindow.getContentSize();
  return { width, height };
}

function checkSize(actual, requested, label) {
  if (!actual) return;
  if (Math.abs(actual.width - requested.width) > 2 || Math.abs(actual.height - requested.height) > 2) {
    report.warnings.push(
      label + ' content size ' + actual.width + 'x' + actual.height +
      ' differs from requested ' + requested.width + 'x' + requested.height +
      ' (screen work area or window manager clamp)',
    );
  }
}

function placeWindow(browserWindow, width, height) {
  const { workArea } = screen.getPrimaryDisplay();
  const x = workArea.x + Math.max(0, Math.floor((workArea.width - width) / 2));
  const y = workArea.y + Math.max(0, Math.floor((workArea.height - height) / 2));
  browserWindow.setPosition(x, y);
}

function attachEvents(browserWindow) {
  const seen = new Set();

  browserWindow.webContents.on('console-message', (event, level, message) => {
    const msg = event && typeof event === 'object' && 'message' in event ? event.message : message;
    const lvl = event && typeof event === 'object' && 'level' in event ? event.level : level;
    if (!msg) return;
    if (CONSOLE_NOISE.some((pattern) => pattern.test(msg))) return;

    const isError = lvl === 'error' || lvl === 3;
    const isWarning = lvl === 'warning' || lvl === 2;
    if (!isError && !isWarning) return;

    const entry = { level: isError ? 'error' : 'warning', message: String(msg).slice(0, 500) };
    const key = entry.level + ':' + entry.message;
    if (seen.has(key)) return;
    seen.add(key);

    const bucket = isError ? report.consoleErrors : report.consoleWarnings;
    if (bucket.length < 40) bucket.push(entry);
  });

  browserWindow.on('unresponsive', () => report.warnings.push('window unresponsive'));
  browserWindow.webContents.on('render-process-gone', (_event, details) => {
    report.warnings.push('render-process-gone: ' + (details && details.reason ? details.reason : 'unknown'));
  });
  browserWindow.webContents.on('did-fail-load', (_event, code, description, failedUrl, isMainFrame) => {
    if (isMainFrame) {
      report.warnings.push('did-fail-load ' + code + ' ' + description + ' ' + failedUrl);
    }
  });
  browserWindow.on('closed', () => {
    win = null;
  });
}

async function loadPage(browserWindow, url) {
  await withTimeout(browserWindow.loadURL(url), 30000, 'loadURL');
  if (browserWindow.isMinimized()) browserWindow.restore();
  if (!browserWindow.isVisible()) browserWindow.show();
  browserWindow.focus();
  browserWindow.webContents.focus();
}

async function settlePage(browserWindow, settleMs) {
  console.log('QA_STEP settle');
  await withTimeout(browserWindow.webContents.executeJavaScript(`(async () => {
    try {
      if (document.fonts && document.fonts.ready) await document.fonts.ready;
    } catch (error) {
      // Font loading API is optional.
    }
    const images = Array.from(document.images);
    await Promise.all(images.map((img) => {
      if (img.complete) return Promise.resolve();
      return new Promise((resolve) => {
        const done = () => resolve();
        img.addEventListener('load', done, { once: true });
        img.addEventListener('error', done, { once: true });
        setTimeout(done, 3000);
      });
    }));
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    return { fonts: document.fonts ? document.fonts.status : 'n/a', images: images.length };
  })()`, false), 15000, 'settle');
  await wait(settleMs);
}

async function resetScroll(browserWindow) {
  await withTimeout(browserWindow.webContents.executeJavaScript(`(() => {
    document.documentElement.style.scrollBehavior = 'auto';
    if (document.body) document.body.style.scrollBehavior = 'auto';
    window.scrollTo(0, 0);
    return window.scrollY;
  })()`, false), 5000, 'reset scroll');
  await wait(200);
}

async function shoot(browserWindow, name) {
  console.log('QA_STEP shot:' + name);

  if (browserWindow.isMinimized()) browserWindow.restore();
  if (!browserWindow.isVisible()) browserWindow.show();
  browserWindow.focus();
  browserWindow.webContents.focus();
  await wait(150);

  const image = await withTimeout(browserWindow.webContents.capturePage(), 15000, 'capturePage ' + name);
  if (image.isEmpty()) throw new Error('capturePage returned an empty image');

  const buffer = image.toPNG();
  const size = image.getSize();
  const fileName = uniqueShotName(name);
  const filePath = path.join(outDir, fileName + '.png');
  fs.writeFileSync(filePath, buffer);

  const item = {
    name,
    path: filePath,
    width: size.width,
    height: size.height,
    bytes: buffer.length,
    sha1: crypto.createHash('sha1').update(buffer).digest('hex').slice(0, 12),
  };
  report.screenshots.push(item);
  return item;
}

function uniqueShotName(name) {
  const base = String(name).replace(/[^a-zA-Z0-9._-]+/g, '-').replace(/^-+|-+$/g, '') || 'shot';
  let candidate = base;
  while (usedShotNames.has(candidate)) {
    shotCounter += 1;
    candidate = base + '-' + shotCounter;
  }
  usedShotNames.add(candidate);
  return candidate;
}

async function metrics(browserWindow) {
  console.log('QA_STEP metrics');
  const expression = buildMetricsExpression(opts.ignores, opts.checks);
  return withTimeout(browserWindow.webContents.executeJavaScript(expression, false), 15000, 'metrics');
}

function buildMetricsExpression(ignoreSelectors, checks) {
  return `(() => {
    const ignored = ${JSON.stringify(ignoreSelectors)};
    const checkDefs = ${JSON.stringify(checks)};
    const se = document.scrollingElement || document.documentElement;
    const vw = se.clientWidth;
    const vh = se.clientHeight;
    const isIgnored = (el) => ignored.some((selector) => {
      try { return el.matches(selector); } catch (error) { return false; }
    });
    const describe = (el) => {
      const rect = el.getBoundingClientRect();
      const style = getComputedStyle(el);
      return {
        tag: el.tagName ? el.tagName.toLowerCase() : '',
        id: el.id || '',
        className: typeof el.className === 'string' ? el.className.slice(0, 120) : (el.getAttribute('class') || '').slice(0, 120),
        left: Math.round(rect.left),
        right: Math.round(rect.right),
        top: Math.round(rect.top),
        width: Math.round(rect.width),
        height: Math.round(rect.height),
        display: style.display,
        visibility: style.visibility,
        opacity: style.opacity,
        fontSize: style.fontSize,
        lineHeight: style.lineHeight,
        visible: style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity) !== 0 && rect.width > 0 && rect.height > 0,
      };
    };

    const outside = [...document.querySelectorAll('body *')].filter((el) => {
      if (['SCRIPT', 'STYLE', 'LINK', 'META', 'NOSCRIPT', 'TEMPLATE'].includes(el.tagName)) return false;
      const rect = el.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) return false;
      if (isIgnored(el)) return false;
      return rect.right > vw + 1 || rect.left < -1;
    });

    const checkResults = {};
    for (const def of checkDefs) {
      try {
        const elements = [...document.querySelectorAll(def.selector)];
        checkResults[def.name] = {
          selector: def.selector,
          count: elements.length,
          items: elements.slice(0, 5).map((el) => {
            const item = describe(el);
            item.text = (el.innerText || el.textContent || '').trim().slice(0, 120);
            return item;
          }),
        };
      } catch (error) {
        checkResults[def.name] = { selector: def.selector, error: String(error.message || error) };
      }
    }

    const brokenImages = [...document.images]
      .filter((img) => img.complete && img.naturalWidth === 0 && (img.currentSrc || img.src))
      .map((img) => img.currentSrc || img.src)
      .slice(0, 20);

    return {
      url: location.href,
      title: document.title,
      readyState: document.readyState,
      viewport: {
        innerWidth: window.innerWidth,
        innerHeight: window.innerHeight,
        clientWidth: vw,
        clientHeight: vh,
        scrollbarWidth: Math.max(0, Math.round(window.innerWidth - vw)),
        dpr: window.devicePixelRatio,
      },
      document: {
        scrollWidth: se.scrollWidth,
        scrollHeight: se.scrollHeight,
        scrollX: window.scrollX,
        scrollY: window.scrollY,
      },
      horizontalOverflow: se.scrollWidth > vw + 1,
      outOfViewportCount: outside.length,
      outOfViewport: outside.slice(0, 20).map(describe),
      brokenImages,
      imageCount: document.images.length,
      fonts: {
        status: document.fonts ? document.fonts.status : null,
        body: getComputedStyle(document.body).fontFamily,
      },
      checks: checkResults,
    };
  })()`;
}

async function runShot(browserWindow, shot, mobile) {
  const name = (mobile ? 'mobile-section-' : 'section-') + shot.name;
  console.log('QA_STEP ' + name);

  const offset = Number(opts.scrollOffset) || 0;
  const result = await withTimeout(browserWindow.webContents.executeJavaScript(`(() => {
    const el = document.querySelector(${JSON.stringify(shot.selector)});
    if (!el) return { found: false };
    document.documentElement.style.scrollBehavior = 'auto';
    if (document.body) document.body.style.scrollBehavior = 'auto';
    el.scrollIntoView({ block: 'start' });
    window.scrollBy(0, -${offset});
    return { found: true, scrollY: window.scrollY };
  })()`, false), 5000, 'scroll ' + shot.name);

  if (!result.found) {
    report.warnings.push('shot selector not found: ' + shot.selector);
    return { name: shot.name, selector: shot.selector, found: false };
  }

  await wait(400);
  const screenshot = await shoot(browserWindow, name);
  return {
    name: shot.name,
    selector: shot.selector,
    found: true,
    scrollY: result.scrollY,
    screenshot,
  };
}

async function runClick(browserWindow, click, mobile) {
  const name = (mobile ? 'mobile-click-' : 'click-') + click.name;
  console.log('QA_STEP ' + name);

  if (browserWindow.isMinimized()) browserWindow.restore();
  if (!browserWindow.isVisible()) browserWindow.show();
  browserWindow.focus();
  browserWindow.webContents.focus();
  await wait(100);

  let result;
  let blocked = false;

  try {
    result = await withTimeout(browserWindow.webContents.executeJavaScript(`(() => {
      const el = document.querySelector(${JSON.stringify(click.selector)});
      if (!el) return { found: false };
      el.scrollIntoView({ block: 'center' });
      el.click();
      return {
        found: true,
        tag: el.tagName ? el.tagName.toLowerCase() : '',
        text: (el.innerText || el.textContent || '').trim().slice(0, 120),
      };
    })()`, true), 5000, 'click ' + click.name);
  } catch (error) {
    blocked = true;
    result = { found: false, error: String(error && error.message ? error.message : error) };
    report.warnings.push('click failed or timed out; renderer may be blocked by clipboard/focus: ' + click.name);
  }

  let screenshot = null;
  if (result.found) {
    await wait(300);
    try {
      screenshot = await shoot(browserWindow, name);
    } catch (error) {
      blocked = true;
      report.warnings.push('screenshot after click failed: ' + click.name + ': ' + error.message);
    }
  } else if (!result.error) {
    report.warnings.push('click selector not found: ' + click.selector);
  }

  return {
    name: click.name,
    selector: click.selector,
    found: Boolean(result.found),
    tag: result.tag || null,
    text: result.text || null,
    error: result.error || null,
    blocked,
    screenshot,
  };
}

function withTimeout(promise, ms, label) {
  let timer;
  return Promise.race([
    Promise.resolve(promise).finally(() => clearTimeout(timer)),
    new Promise((_resolve, reject) => {
      timer = setTimeout(() => reject(new Error(label + ' timed out after ' + ms + 'ms')), ms);
    }),
  ]);
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function finish(code) {
  if (finished) return;
  finished = true;
  clearTimeout(watchdog);
  report.finishedAt = report.finishedAt || new Date().toISOString();
  safeWriteReport();

  console.log('QA_RESULT ' + reportPath);
  console.log('QA_SUMMARY ' + JSON.stringify({
    ok: report.ok,
    screenshots: report.screenshots.length,
    desktopViewport: report.desktop && report.desktop.metrics ? report.desktop.metrics.viewport : null,
    mobileViewport: report.mobile && report.mobile.metrics ? report.mobile.metrics.viewport : null,
    warningCount: report.warnings.length,
    consoleErrorCount: report.consoleErrors.length,
  }));

  if (code === 0) {
    app.quit();
    setTimeout(() => app.exit(0), 1500);
  } else {
    app.exit(code);
  }
}

function finishError(error) {
  if (finished) return;
  report.ok = false;
  report.error = String(error && error.message ? error.message : error);
  report.finishedAt = new Date().toISOString();
  console.error('QA_FAILED ' + report.error);
  finish(2);
}

function safeWriteReport() {
  try {
    fs.writeFileSync(reportPath, JSON.stringify(report, null, 2), 'utf8');
  } catch (error) {
    console.error('QA_WARN could not write report: ' + error.message);
  }
}
