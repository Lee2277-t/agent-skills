# 校验每个技能：frontmatter 合法、描述长度、没有绑定本机路径。
$ErrorActionPreference = 'Stop'
$root = Join-Path (Split-Path -Parent $PSScriptRoot) 'skills'

if (-not (Test-Path -LiteralPath $root)) { Write-Host "找不到 skills 目录: $root"; exit 1 }

$fail = 0
$skills = @(Get-ChildItem -LiteralPath $root -Recurse -Filter 'SKILL.md' -File)
Write-Host "检查 $($skills.Count) 个技能`n"

foreach ($f in $skills) {
    $rel = $f.Directory.FullName.Substring($root.Length).TrimStart('\')
    $raw = [System.IO.File]::ReadAllText($f.FullName, [System.Text.Encoding]::UTF8)

    if ($raw -notmatch '^---\r?\n') { Write-Host "  [FAIL] $rel 缺 frontmatter"; $fail++; continue }

    $name = if ($raw -match '(?m)^name:\s*(.+)$') { $Matches[1].Trim() } else { '' }
    $desc = if ($raw -match '(?m)^description:\s*(.+)$') { $Matches[1].Trim() } else { '' }

    if (-not $name) { Write-Host "  [FAIL] $rel 缺 name"; $fail++ }
    elseif ($name -notmatch '^[a-z0-9]+(-[a-z0-9]+)*$') { Write-Host "  [FAIL] $rel name 不是小写 kebab: $name"; $fail++ }
    elseif ($name -ne $f.Directory.Name -and $name -notmatch '^[a-z0-9-]+$') { Write-Host "  [WARN] $rel name($name) 与目录名不一致" }

    if (-not $desc) { Write-Host "  [FAIL] $rel 缺 description"; $fail++ }
    elseif ($desc.Length -lt 40) { Write-Host "  [FAIL] $rel description 太短（$($desc.Length) 字符），难以被检索命中"; $fail++ }

    # 不允许绑定本机绝对路径
    $leak = [regex]::Match($raw, 'C:\\Users\\[^\\\s]+|D:\\(开发|计划|桌宠|审计|翻译|去水印|技能中心)')
    if ($leak.Success) { Write-Host "  [FAIL] $rel 含本机路径: $($leak.Value)"; $fail++ }
}

Write-Host ''
if ($fail -eq 0) { Write-Host "全部通过" -ForegroundColor Green; exit 0 }
Write-Host "$fail 项失败" -ForegroundColor Red
exit 1
