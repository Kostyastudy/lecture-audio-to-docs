param(
    [string]$SkillsRoot = "$env:USERPROFILE\.dsh\skills",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$src = $PSScriptRoot
$name = "lecture-audio-to-docs"
$target = Join-Path $SkillsRoot $name

if (-not (Test-Path (Join-Path $src "SKILL.md"))) {
    throw "SKILL.md not found next to install.ps1"
}

if (Test-Path $target) {
    if (-not $Force) {
        Write-Host "Already installed: $target"
        Write-Host "Re-run with -Force to overwrite."
        exit 1
    }
    $resolved = (Resolve-Path -LiteralPath $target).Path
    if ($resolved.StartsWith((Resolve-Path $SkillsRoot).Path)) {
        Remove-Item -LiteralPath $resolved -Recurse -Force
    } else {
        throw "Refusing to remove unexpected path: $resolved"
    }
}

New-Item -ItemType Directory -Force -Path $target | Out-Null
Copy-Item -LiteralPath (Join-Path $src "SKILL.md") -Destination $target
Copy-Item -LiteralPath (Join-Path $src "scripts") -Destination $target -Recurse
Copy-Item -LiteralPath (Join-Path $src "references") -Destination $target -Recurse
Get-ChildItem -Path (Join-Path $target "scripts") -Filter "__pycache__" -Recurse -Force -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force

Write-Host "Installed to $target"
Write-Host "Restart the session (or reload skills) to pick it up."
