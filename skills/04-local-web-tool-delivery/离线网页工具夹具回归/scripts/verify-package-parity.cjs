// Compare a delivery zip against its source directory, file by file (md5), then clean up.
// usage: node verify-package-parity.cjs <package.zip> <srcDir> [--keep-tmp]
const cp = require('child_process');
const crypto = require('crypto');
const fs = require('fs');
const os = require('os');
const path = require('path');

const zip = path.resolve(process.argv[2] || '');
const src = path.resolve(process.argv[3] || '');
const keepTmp = process.argv.includes('--keep-tmp');

function fail(msg) {
  console.log('FAIL ' + msg);
  process.exit(2);
}

if (!fs.existsSync(zip)) fail('zip not found: ' + zip);
if (!fs.existsSync(src) || !fs.statSync(src).isDirectory()) fail('source dir not found: ' + src);

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'pkg-parity-'));
const r = cp.spawnSync('tar', ['-xf', zip, '-C', tmp], { encoding: 'utf8' });
if (r.status !== 0) {
  cleanup();
  fail('cannot extract with tar: ' + (r.stderr || '').trim());
}

// A delivery zip often wraps everything in one folder named after the project.
const entries = fs.readdirSync(tmp);
let root = tmp;
if (entries.length === 1 && fs.statSync(path.join(tmp, entries[0])).isDirectory()) {
  root = path.join(tmp, entries[0]);
}

function walk(dir, base) {
  const out = [];
  for (const name of fs.readdirSync(dir)) {
    const abs = path.join(dir, name);
    if (fs.statSync(abs).isDirectory()) {
      out.push(...walk(abs, base));
      continue;
    }
    const rel = path.relative(base, abs).split(path.sep).join('/');
    if (/^__MACOSX\/|\/\.DS_Store$|^[^/]*\.DS_Store$/.test(rel)) continue;
    out.push(rel);
  }
  return out;
}

function md5(abs) {
  return crypto.createHash('md5').update(fs.readFileSync(abs)).digest('hex');
}

const srcFiles = walk(src, src).sort();
const pkgFiles = walk(root, root).sort();
const pkgSet = new Set(pkgFiles);
const srcSet = new Set(srcFiles);

let bad = 0;
for (const rel of srcFiles) {
  if (!pkgSet.has(rel)) {
    console.log('MISSING ' + rel);
    bad += 1;
    continue;
  }
  const a = md5(path.join(src, rel));
  const b = md5(path.join(root, rel));
  if (a !== b) {
    console.log('DIFF    ' + rel + ' src=' + a + ' pkg=' + b);
    bad += 1;
  } else {
    console.log('OK      ' + rel + ' ' + fs.statSync(path.join(src, rel)).size + 'B');
  }
}
for (const rel of pkgFiles) {
  if (!srcSet.has(rel)) {
    console.log('EXTRA   ' + rel);
    bad += 1;
  }
}

cleanup();
console.log('SOURCE_FILES ' + srcFiles.length + ' PKG_FILES ' + pkgFiles.length + ' PROBLEMS ' + bad);
console.log(bad === 0 ? 'PASS package matches source' : 'FAIL package differs from source');
process.exit(bad === 0 ? 0 : 1);

function cleanup() {
  if (keepTmp) {
    console.log('KEPT ' + tmp);
    return;
  }
  fs.rmSync(tmp, { recursive: true, force: true });
}
