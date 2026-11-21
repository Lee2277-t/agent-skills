'use strict';

const fs = require('node:fs');
const path = require('node:path');

const DEFAULTS = {
  outputDir: null,
  clickSelector: '#pet',
  assertExpression: "Boolean(document.querySelector('#speech')?.classList.contains('show'))",
  resetExpression: "(() => { const el = document.querySelector('#speech'); if (el) { el.classList.remove('show'); el.textContent = ''; } return true; })()",
  readyTimeoutMs: 15000,
  warmupMs: 800,
  clickWaitMs: 400,
  minPetOpaqueRatio: 0.05,
  maxCornerAlpha: 16,
  keepOpen: false,
  cleanupUserData: false,
};

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function waitForWindow(getWindow, timeoutMs) {
  return new Promise((resolve, reject) => {
    const started = Date.now();
    const tick = () => {
      let win = null;
      try {
        win = getWindow();
      } catch {
        win = null;
      }
      if (win && !win.isDestroyed()) {
        resolve(win);
        return;
      }
      if (Date.now() - started > timeoutMs) {
        reject(new Error('window did not appear'));
        return;
      }
      setTimeout(tick, 50);
    };
    tick();
  });
}

function waitForLoad(win, timeoutMs) {
  return new Promise((resolve, reject) => {
    if (!win.webContents.isLoading()) {
      resolve();
      return;
    }
    const timer = setTimeout(() => reject(new Error('page did not finish loading')), timeoutMs);
    win.webContents.once('did-finish-load', () => {
      clearTimeout(timer);
      resolve();
    });
    win.webContents.once('did-fail-load', (_event, code, description, url, isMainFrame) => {
      if (!isMainFrame) return;
      clearTimeout(timer);
      reject(new Error(`did-fail-load ${code} ${description} ${url}`));
    });
  });
}

function readPixels(image, width, height) {
  const captureSize = image.getSize();
  if (!captureSize.width || !captureSize.height) {
    throw new Error('capturePage returned an empty image');
  }
  if (!width || !height) {
    throw new Error(`invalid content size ${width}x${height}`);
  }
  const normalized = image.resize({ width, height, quality: 'best' });
  const bitmap = normalized.toBitmap();
  const expected = width * height * 4;
  if (bitmap.length < expected) {
    throw new Error(`unexpected bitmap length ${bitmap.length}, expected ${expected}`);
  }
  return {
    width,
    height,
    bitmap,
    captureWidth: captureSize.width,
    captureHeight: captureSize.height,
  };
}

function alphaAt(pixels, x, y) {
  const px = Math.max(0, Math.min(pixels.width - 1, Math.round(x)));
  const py = Math.max(0, Math.min(pixels.height - 1, Math.round(y)));
  return pixels.bitmap[(py * pixels.width + px) * 4 + 3];
}

function analyzeRect(pixels, rect) {
  const x0 = Math.max(0, Math.floor(rect ? rect.x : 0));
  const y0 = Math.max(0, Math.floor(rect ? rect.y : 0));
  const x1 = Math.min(pixels.width, Math.ceil(rect ? rect.x + rect.width : pixels.width));
  const y1 = Math.min(pixels.height, Math.ceil(rect ? rect.y + rect.height : pixels.height));
  let opaque = 0;
  let total = 0;
  for (let y = y0; y < y1; y += 1) {
    for (let x = x0; x < x1; x += 1) {
      total += 1;
      if (alphaAt(pixels, x, y) > 16) opaque += 1;
    }
  }
  return {
    x: x0,
    y: y0,
    width: x1 - x0,
    height: y1 - y0,
    opaque,
    total,
    ratio: total > 0 ? opaque / total : 0,
  };
}

function findOpaquePoint(pixels, rect) {
  const x0 = Math.max(0, Math.floor(rect.x));
  const y0 = Math.max(0, Math.floor(rect.y));
  const x1 = Math.min(pixels.width, Math.ceil(rect.x + rect.width));
  const y1 = Math.min(pixels.height, Math.ceil(rect.y + rect.height));
  let sumX = 0;
  let sumY = 0;
  let count = 0;

  for (let y = y0; y < y1; y += 2) {
    for (let x = x0; x < x1; x += 2) {
      if (alphaAt(pixels, x, y) <= 200) continue;
      sumX += x;
      sumY += y;
      count += 1;
    }
  }
  if (count === 0) return null;

  const centerX = sumX / count;
  const centerY = sumY / count;
  let best = null;
  for (let y = y0; y < y1; y += 1) {
    for (let x = x0; x < x1; x += 1) {
      const alpha = alphaAt(pixels, x, y);
      if (alpha <= 200) continue;
      const distance = (x - centerX) ** 2 + (y - centerY) ** 2;
      if (!best || distance < best.distance) {
        best = { x, y, alpha, distance };
      }
    }
  }
  return best;
}

function readPetRect(win, selector) {
  return win.webContents.executeJavaScript(`(() => {
    const el = document.querySelector(${JSON.stringify(selector)});
    if (!el) return null;
    const rect = el.getBoundingClientRect();
    return { x: rect.left, y: rect.top, width: rect.width, height: rect.height };
  })()`).then((rect) => {
    if (!rect || rect.width <= 0 || rect.height <= 0) {
      throw new Error(`selector ${selector} was not found or has an empty box`);
    }
    return rect;
  });
}

function consoleEntry(args) {
  if (args.length === 1 && args[0] && typeof args[0] === 'object') {
    const detail = args[0];
    return {
      level: detail.level,
      message: String(detail.message ?? ''),
      line: detail.lineNumber ?? 0,
      source: detail.sourceId ?? '',
    };
  }
  return {
    level: args[0],
    message: String(args[1] ?? ''),
    line: args[2] ?? 0,
    source: args[3] ?? '',
  };
}

function isErrorLevel(level) {
  return level === 'error' || level === 3 || level === '3';
}

function installSmokeTest({ app, getWindow, options = {} }) {
  if (process.env.PET_SMOKE !== '1') return;

  const opts = { ...DEFAULTS, ...options };
  const outputDir = opts.outputDir || path.join(app.getAppPath(), '.dev');
  const reportPath = path.join(outputDir, 'smoke-report.json');
  const errors = { console: [], renderGone: [], failedLoad: [] };
  let finished = false;

  const writeReport = (report) => {
    try {
      fs.mkdirSync(outputDir, { recursive: true });
      fs.writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`);
    } catch (error) {
      console.error(`SMOKE_REPORT_WRITE_FAIL ${error.message}`);
    }
  };

  const finish = (ok, payload) => {
    if (finished) return;
    finished = true;
    const report = {
      ok,
      at: new Date().toISOString(),
      electron: process.versions.electron,
      chrome: process.versions.chrome,
      ...payload,
      errors,
      note: 'PNG previews may show transparent pixels as white. Judge transparency by alpha values, not by eye.',
    };
    writeReport(report);
    console.log(`${ok ? 'SMOKE_PASS' : 'SMOKE_FAIL'} ${JSON.stringify({
      reason: report.reason,
      cornerAlphaMax: report.alpha?.cornerMax,
      petOpaqueRatio: report.alpha?.pet?.ratio,
      clickAssertion: report.click?.value,
      report: reportPath,
    })}`);

    if (opts.cleanupUserData) {
      const userData = app.getPath('userData');
      if (path.basename(userData).toLowerCase().includes('smoke')) {
        try {
          fs.rmSync(userData, { recursive: true, force: true });
        } catch {
          // Best-effort cleanup only.
        }
      }
    }
    if (!opts.keepOpen) app.exit(ok ? 0 : 1);
  };

  const fail = (reason, extra = {}) => finish(false, { reason, ...extra });

  const overallTimer = setTimeout(
    () => fail(`smoke test timed out after ${opts.readyTimeoutMs + 10000}ms`),
    opts.readyTimeoutMs + 10000,
  );
  overallTimer.unref?.();

  (async () => {
    const win = await waitForWindow(getWindow, opts.readyTimeoutMs);

    win.webContents.on('console-message', (_event, ...args) => {
      const entry = consoleEntry(args);
      if (isErrorLevel(entry.level)) errors.console.push(entry);
    });
    win.webContents.on('render-process-gone', (_event, details) => {
      errors.renderGone.push(details);
    });
    win.webContents.on('did-fail-load', (_event, code, description, url, isMainFrame) => {
      if (isMainFrame) errors.failedLoad.push({ code, description, url });
    });

    await waitForLoad(win, opts.readyTimeoutMs);
    if (!win.isVisible()) win.showInactive();
    await sleep(opts.warmupMs);

    if (opts.resetExpression) {
      await win.webContents.executeJavaScript(opts.resetExpression);
      await sleep(80);
    }

    const [contentWidth, contentHeight] = win.getContentSize();
    const beforeImage = await win.webContents.capturePage();
    const beforePixels = readPixels(beforeImage, contentWidth, contentHeight);
    const petRect = await readPetRect(win, opts.clickSelector);
    const petAlpha = analyzeRect(beforePixels, petRect);
    const cornerPoints = [
      [2, 2],
      [beforePixels.width - 3, 2],
      [2, beforePixels.height - 3],
      [beforePixels.width - 3, beforePixels.height - 3],
    ];
    const cornerAlphas = cornerPoints.map(([x, y]) => alphaAt(beforePixels, x, y));
    const cornerMax = Math.max(...cornerAlphas);

    fs.mkdirSync(outputDir, { recursive: true });
    const beforePath = path.join(outputDir, 'smoke-before.png');
    const afterPath = path.join(outputDir, 'smoke-after.png');
    fs.writeFileSync(beforePath, beforeImage.toPNG());

    const point = findOpaquePoint(beforePixels, petRect);
    if (!point) return fail('no opaque pet pixel found inside the selector box');

    win.webContents.sendInputEvent({ type: 'mouseMove', x: point.x, y: point.y });
    await sleep(80);
    win.webContents.sendInputEvent({
      type: 'mouseDown',
      x: point.x,
      y: point.y,
      button: 'left',
      clickCount: 1,
    });
    win.webContents.sendInputEvent({
      type: 'mouseUp',
      x: point.x,
      y: point.y,
      button: 'left',
      clickCount: 1,
    });
    await sleep(opts.clickWaitMs);

    const clickValue = await win.webContents.executeJavaScript(opts.assertExpression);
    const afterImage = await win.webContents.capturePage();
    fs.writeFileSync(afterPath, afterImage.toPNG());

    const alpha = { corners: cornerAlphas, cornerMax, pet: petAlpha };
    const click = {
      x: point.x,
      y: point.y,
      alpha: point.alpha,
      expression: opts.assertExpression,
      value: Boolean(clickValue),
    };
    const base = {
      window: {
        width: beforePixels.width,
        height: beforePixels.height,
        captureWidth: beforePixels.captureWidth,
        captureHeight: beforePixels.captureHeight,
        scaleFactor: Number((beforePixels.captureWidth / beforePixels.width).toFixed(2)),
        visible: win.isVisible(),
      },
      petRect,
      alpha,
      click,
      previews: { before: beforePath, after: afterPath },
    };

    if (errors.failedLoad.length) return fail('page failed to load', base);
    if (errors.renderGone.length) return fail('renderer process gone', base);
    if (errors.console.length) return fail('renderer console error', base);
    if (petAlpha.ratio < opts.minPetOpaqueRatio) {
      return fail(
        `pet opaque ratio ${petAlpha.ratio.toFixed(3)} is below ${opts.minPetOpaqueRatio}`,
        base,
      );
    }
    if (cornerMax > opts.maxCornerAlpha) {
      return fail(
        `corner alpha ${cornerMax} exceeds ${opts.maxCornerAlpha}; the window may not be transparent`,
        base,
      );
    }
    if (!click.value) return fail('click assertion returned false', base);

    finish(true, base);
  })().catch((error) => {
    fail(error && error.message ? error.message : String(error), {
      stack: error && error.stack ? error.stack : '',
    });
  }).finally(() => clearTimeout(overallTimer));
}

module.exports = { installSmokeTest };
