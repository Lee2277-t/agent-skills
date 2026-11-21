#!/usr/bin/env node
'use strict';

const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

function fail(reason, code = 1) {
  console.error(`ELECTRON_FAIL ${reason}`);
  process.exit(code);
}

function help() {
  console.log(`Usage: node ensure-electron.cjs [project-dir] [--mirror=<url>]

Checks node_modules/electron/dist, runs Electron's install.js when the binary is
missing, then verifies the result. Exits 0 only when the runtime is usable.
`);
}

const args = process.argv.slice(2);
let projectDir = process.cwd();
let mirror = process.env.ELECTRON_MIRROR || '';

for (const arg of args) {
  if (arg === '--help' || arg === '-h') {
    help();
    process.exit(0);
  }
  if (arg.startsWith('--mirror=')) {
    mirror = arg.slice('--mirror='.length);
    continue;
  }
  if (arg.startsWith('-')) {
    fail(`unknown argument: ${arg}`, 2);
  }
  projectDir = path.resolve(arg);
}

const electronDir = path.join(projectDir, 'node_modules', 'electron');
const packagePath = path.join(electronDir, 'package.json');
const installScript = path.join(electronDir, 'install.js');

if (!fs.existsSync(electronDir) || !fs.existsSync(packagePath)) {
  fail(`electron is not installed at ${electronDir}; run npm install first`);
}

let pkg;
try {
  pkg = JSON.parse(fs.readFileSync(packagePath, 'utf8'));
} catch (error) {
  fail(`cannot read ${packagePath}: ${error.message}`);
}

if (!pkg.version) {
  fail(`missing version in ${packagePath}`);
}

function platformExecutable() {
  if (process.platform === 'win32') return 'electron.exe';
  if (process.platform === 'darwin') return 'Electron.app/Contents/MacOS/Electron';
  return 'electron';
}

const executableRelative = platformExecutable();
const distDir = path.join(electronDir, 'dist');
const executablePath = path.join(distDir, executableRelative);

function readText(file) {
  try {
    return fs.readFileSync(file, 'utf8').trim();
  } catch {
    return '';
  }
}

function inspect() {
  const distVersion = readText(path.join(distDir, 'version')).replace(/^v/, '');
  const pathTxt = readText(path.join(electronDir, 'path.txt'));
  const executable = fs.existsSync(executablePath);
  return {
    ok: distVersion === pkg.version && pathTxt === executableRelative && executable,
    distVersion,
    pathTxt,
    executable,
  };
}

const before = inspect();
if (before.ok) {
  console.log(`ELECTRON_OK version=${pkg.version} exe=${executablePath}`);
  process.exit(0);
}

if (!fs.existsSync(installScript)) {
  fail(`missing ${installScript}; reinstall the electron package`);
}

const env = { ...process.env };
if (mirror) {
  env.ELECTRON_MIRROR = mirror.endsWith('/') ? mirror : `${mirror}/`;
}

console.log(
  `ELECTRON_MISSING version=${pkg.version} distVersion=${before.distVersion || 'none'} ` +
  `pathTxt=${before.pathTxt || 'none'} exe=${before.executable}`,
);
console.log(`ELECTRON_INSTALL node=${process.execPath} mirror=${env.ELECTRON_MIRROR || 'default'}`);

const result = spawnSync(process.execPath, [installScript], {
  cwd: electronDir,
  env,
  stdio: 'inherit',
});

if (result.error) {
  fail(`failed to run install.js: ${result.error.message}`);
}
if (result.status !== 0) {
  fail(`install.js exited with ${result.status === null ? result.signal : result.status}`);
}

const after = inspect();
if (!after.ok) {
  fail(
    `binary is still incomplete after install.js ` +
    `(version=${after.distVersion || 'none'}, pathTxt=${after.pathTxt || 'none'}, exe=${after.executable})`,
  );
}

console.log(`ELECTRON_OK version=${pkg.version} exe=${executablePath}`);
