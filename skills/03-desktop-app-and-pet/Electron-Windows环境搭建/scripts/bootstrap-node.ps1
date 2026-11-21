[CmdletBinding()]
param(
  [string]$Dest = ".dev\node",
  [string]$Version = "24",
  [string]$Mirror = "https://npmmirror.com/mirrors/node",
  [switch]$Force
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

function Write-Step([string]$Message) {
  Write-Host "NODE_STEP $Message"
}

function Fail([string]$Message) {
  [Console]::Error.WriteLine("NODE_FAIL $Message")
  exit 1
}

$Dest = [IO.Path]::GetFullPath($Dest)
$nodeExe = Join-Path $Dest "node.exe"
$npmCli = Join-Path $Dest "node_modules\npm\bin\npm-cli.js"

$Version = $Version.Trim().TrimStart("v")
if ($Version -notmatch '^\d+(\.\d+\.\d+)?$') {
  Fail "Version must be a major number (24) or full version (24.18.0), got '$Version'"
}
$parts = $Version.Split(".")
$major = $parts[0]
$exact = $parts.Count -eq 3

if ((Test-Path $nodeExe) -and (Test-Path $npmCli) -and -not $Force) {
  $existing = (& $nodeExe -v).Trim().TrimStart("v")
  $matchesRequest = if ($exact) { $existing -eq $Version } else { $existing.Split(".")[0] -eq $major }
  if ($matchesRequest) {
    $npmVersion = (& $nodeExe $npmCli -v).Trim()
    Write-Host "NODE_OK version=v$existing npm=$npmVersion dest=$Dest"
    exit 0
  }
  Write-Step "existing Node v$existing does not match requested $Version; refreshing"
}

$base = $Mirror.TrimEnd("/")
$resolved = $Version

if (-not $exact) {
  $indexUrl = "$base/index.json"
  Write-Step "resolve latest Node $major from $indexUrl"
  $index = Invoke-RestMethod -Uri $indexUrl -UseBasicParsing -TimeoutSec 120
  $pattern = '^v' + [regex]::Escape($major) + '\.\d+\.\d+$'
  $candidate = @($index | Where-Object { $_.version -match $pattern })
  if ($candidate.Count -eq 0) {
    Fail "no Node $major release found in $indexUrl"
  }
  $resolved = ($candidate |
    Sort-Object { [version]$_.version.TrimStart("v") } -Descending |
    Select-Object -First 1).version.TrimStart("v")
}

$zipName = "node-v$resolved-win-x64.zip"
$releaseBase = "$base/v$resolved"
$zipUrl = "$releaseBase/$zipName"
$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("qoder-node-" + [Guid]::NewGuid().ToString("N"))

try {
  New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
  $zipPath = Join-Path $tempRoot $zipName

  Write-Step "download $zipUrl"
  Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath -UseBasicParsing -TimeoutSec 600

  $shasumsUrl = "$releaseBase/SHASUMS256.txt"
  $shasums = (Invoke-WebRequest -Uri $shasumsUrl -UseBasicParsing -TimeoutSec 120).Content
  $line = ($shasums -split "`n" |
    Where-Object { $_ -match "\s+$([regex]::Escape($zipName))$" } |
    Select-Object -First 1)
  if (-not $line) {
    Fail "checksum entry for $zipName not found in $shasumsUrl"
  }
  $expected = ($line.Trim() -split '\s+')[0].ToLowerInvariant()
  $actual = (Get-FileHash -Path $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($expected -ne $actual) {
    Fail "sha256 mismatch for $zipName expected=$expected actual=$actual"
  }
  Write-Step "checksum ok"

  $staging = Join-Path $tempRoot "staging"
  Write-Step "extract"
  Expand-Archive -Path $zipPath -DestinationPath $staging -Force
  $root = Get-ChildItem -LiteralPath $staging -Directory | Select-Object -First 1
  if (-not $root) {
    Fail "unexpected archive layout: no top-level directory"
  }

  if (-not (Test-Path $Dest)) {
    New-Item -ItemType Directory -Path $Dest -Force | Out-Null
  }
  Write-Step "install to $Dest"
  Copy-Item -Path (Join-Path $root.FullName '*') -Destination $Dest -Recurse -Force

  if (-not (Test-Path $nodeExe)) {
    Fail "node.exe not found after extraction"
  }
  if (-not (Test-Path $npmCli)) {
    Fail "npm not found after extraction"
  }

  $nodeVersion = (& $nodeExe -v).Trim()
  $npmVersion = (& $nodeExe $npmCli -v).Trim()
  Write-Host "NODE_OK version=$nodeVersion npm=$npmVersion dest=$Dest"
}
catch {
  Fail $_.Exception.Message
}
finally {
  if ($tempRoot -and (Test-Path $tempRoot)) {
    Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
  }
}
