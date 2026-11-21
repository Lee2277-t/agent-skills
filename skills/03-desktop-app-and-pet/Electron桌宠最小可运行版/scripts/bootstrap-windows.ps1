[CmdletBinding()]
param(
  [string]$ProjectDir = ".",
  [string]$NodeVersion = "24.18.0",
  [string]$Registry = "https://registry.npmmirror.com",
  [string]$ElectronMirror = "",
  [string]$BootstrapSkillDir = "$env:USERPROFILE\.qoder-cn\skills\electron-windows-bootstrap",
  [switch]$AcceptDownload,
  [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Info([string]$Message) {
  Write-Host "PET_ENV $Message"
}

function Ok([string]$Message) {
  Write-Host "PET_ENV_OK $Message"
}

function Fail([string]$Message) {
  [Console]::Error.WriteLine("PET_ENV_FAIL $Message")
  exit 1
}

$ProjectDir = [IO.Path]::GetFullPath($ProjectDir)
if (-not (Test-Path -LiteralPath $ProjectDir)) {
  Fail "project directory not found: $ProjectDir"
}

$packagePath = Join-Path $ProjectDir "package.json"
$localNode = Join-Path $ProjectDir ".dev\node\node.exe"
$localNpmCli = Join-Path $ProjectDir ".dev\node\node_modules\npm\bin\npm-cli.js"
$systemNode = Get-Command node -ErrorAction SilentlyContinue
$systemNpm = Get-Command npm -ErrorAction SilentlyContinue

$nodeExe = $null
$npmMode = "missing"
if (Test-Path -LiteralPath $localNode) {
  $nodeExe = $localNode
  if (Test-Path -LiteralPath $localNpmCli) {
    $npmMode = "local"
  }
} elseif ($systemNode) {
  $nodeExe = $systemNode.Source
  if ($systemNpm) {
    $npmMode = "system"
  }
}

$electronPkg = Join-Path $ProjectDir "node_modules\electron\package.json"
$electronExe = Join-Path $ProjectDir "node_modules\electron\dist\electron.exe"
$electronReady = (Test-Path -LiteralPath $electronPkg) -and (Test-Path -LiteralPath $electronExe)

if ($CheckOnly) {
  if (-not $nodeExe) {
    Fail "node/npm missing; rerun with -AcceptDownload after the user approves the portable Node download"
  }
  if (-not $electronReady) {
    Fail "electron runtime missing at $electronExe; rerun without -CheckOnly after the user approves dependency setup"
  }
  $installedElectron = (Get-Content -LiteralPath $electronPkg -Raw | ConvertFrom-Json).version
  Ok "node=$(& $nodeExe -v) npm=$npmMode electron=$installedElectron project=$ProjectDir"
  exit 0
}

if (-not (Test-Path -LiteralPath $packagePath)) {
  Fail "package.json is missing; create the app skeleton first"
}

if (-not $nodeExe -or $npmMode -eq "missing") {
  if (-not $AcceptDownload) {
    Fail "node/npm missing; rerun with -AcceptDownload after the user approves the portable Node download"
  }
  $bootstrapNode = Join-Path $BootstrapSkillDir "scripts\bootstrap-node.ps1"
  if (-not (Test-Path -LiteralPath $bootstrapNode)) {
    Fail "portable Node helper not found at $bootstrapNode; install electron-windows-bootstrap or use the fallback commands in references/electron-pet-mvp.md"
  }
  Info "installing portable Node $NodeVersion via $bootstrapNode"
  & powershell -NoProfile -ExecutionPolicy Bypass -File $bootstrapNode `
    -Dest (Join-Path $ProjectDir ".dev\node") -Version $NodeVersion
  if ($LASTEXITCODE -ne 0) {
    Fail "portable Node installation failed"
  }
  $nodeExe = $localNode
  if (Test-Path -LiteralPath $localNpmCli) {
    $npmMode = "local"
  } else {
    Fail "npm is missing from the portable Node installation"
  }
}

if (-not (Test-Path -LiteralPath $electronPkg)) {
  Info "installing project dependencies with registry $Registry"
  $env:npm_config_audit = "false"
  $env:npm_config_fund = "false"
  if ($npmMode -eq "local") {
    & $nodeExe $localNpmCli install "--registry=$Registry" --no-audit --no-fund
  } else {
    & $systemNpm.Source install "--registry=$Registry" --no-audit --no-fund
  }
  if ($LASTEXITCODE -ne 0) {
    Fail "npm install failed"
  }
  if (-not (Test-Path -LiteralPath $electronPkg)) {
    Fail "electron package is still missing after npm install"
  }
}

if ($ElectronMirror) {
  $env:ELECTRON_MIRROR = $ElectronMirror
}

$ensureElectron = Join-Path $BootstrapSkillDir "scripts\ensure-electron.cjs"
if (Test-Path -LiteralPath $ensureElectron) {
  Info "ensuring Electron binary via $ensureElectron"
  & $nodeExe $ensureElectron $ProjectDir
  if ($LASTEXITCODE -ne 0) {
    Fail "Electron binary setup failed"
  }
} elseif (-not (Test-Path -LiteralPath $electronExe)) {
  $installScript = Join-Path $ProjectDir "node_modules\electron\install.js"
  if (-not (Test-Path -LiteralPath $installScript)) {
    Fail "electron install.js is missing; reinstall the electron package"
  }
  Info "running electron install.js directly"
  Push-Location $ProjectDir
  try {
    & $nodeExe $installScript
  } finally {
    Pop-Location
  }
  if ($LASTEXITCODE -ne 0) {
    Fail "electron install.js failed"
  }
}

if (-not (Test-Path -LiteralPath $electronExe)) {
  Fail "electron.exe is still missing at $electronExe"
}

$installedElectron = (Get-Content -LiteralPath $electronPkg -Raw | ConvertFrom-Json).version
Ok "node=$(& $nodeExe -v) electron=$installedElectron project=$ProjectDir"
Info "START $electronExe ."
