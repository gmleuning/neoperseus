<#
.SYNOPSIS
    Publish the built reader (site/public/) to Cloudflare Pages.

.DESCRIPTION
    Uploads site/public/ with Cloudflare's wrangler tool (run through npx, nothing to install
    besides Node.js). Only files that changed since the last deploy are uploaded, so after
    the first deploy an update takes seconds. Wrangler runs inside site/, so its cache
    (site/.wrangler) stays with the site.

    First time only: run  npx wrangler login  and approve access in the browser.

.EXAMPLE
    .\tools\deploy.ps1                 # upload site/public/ as it is
.EXAMPLE
    .\tools\deploy.ps1 -Build          # python perseus.py build --public, then upload
.EXAMPLE
    .\tools\deploy.ps1 -Update         # python perseus.py update (download + convert + build), then upload
.EXAMPLE
    .\tools\deploy.ps1 -Check          # only check site/public/ against Cloudflare's limits, upload nothing
#>
param(
    [switch]$Build,
    [switch]$Update,
    [switch]$Check,
    [string]$Project = 'neoperseus'
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root
$Public = 'site/public'
$wrangler = @('--yes', 'wrangler@4')

function Run([string]$exe, [string[]]$argv) {
    & $exe @argv
    if ($LASTEXITCODE -ne 0) { throw "$exe $($argv -join ' ') failed (exit $LASTEXITCODE)" }
}

# 1. build
if ($Update)    { Run python @('perseus.py', 'update'); Run python @('perseus.py', 'build', '--public') }
elseif ($Build) { Run python @('perseus.py', 'build', '--public') }

# 2. check site/public/ against Cloudflare Pages' free-plan limits
if (-not (Test-Path "$Public/index.html")) { throw "$Public/index.html not found. Build first: .\tools\deploy.ps1 -Build" }
if (Test-Path "$Public/_local") { throw "$Public was built for this computer (it has the catalog page). Rebuild the public version: .\tools\deploy.ps1 -Build" }
if (Test-Path "$Public/_private") { throw "$Public was built with private texts (they must not be published). Rebuild without them: .\tools\deploy.ps1 -Build" }
if (-not (Test-Path "$Public/dict/READY")) {
    Write-Warning "Dictionaries are missing ($Public/dict/READY). The dictionary panel will be empty. Run: python perseus.py dictionaries"
}
if (-not (Test-Path "$Public/fonts")) { throw "$Public/fonts is missing: the site would have no fonts. Rebuild: .\tools\deploy.ps1 -Build" }
$files = Get-ChildItem $Public -Recurse -File
$largest = $files | Sort-Object Length -Descending | Select-Object -First 1
$totalMB = [math]::Round(($files | Measure-Object Length -Sum).Sum / 1MB)
'{0:N0} files, {1:N0} MB; largest {2} ({3:N1} MB)' -f $files.Count, $totalMB,
    $largest.FullName.Substring((Resolve-Path $Public).Path.Length + 1), ($largest.Length / 1MB)
if ($files.Count -gt 20000) { throw "Cloudflare Pages allows 20,000 files per site; $Public has $($files.Count)." }
$tooBig = $files | Where-Object Length -gt 25MB
if ($tooBig) { throw "Cloudflare Pages allows 25 MB per file. Too big:`n$($tooBig.FullName -join "`n")" }
if ($Check) { 'Check passed; nothing uploaded.'; return }

# 3. create the Pages project on first use (wrangler runs inside site/)
Push-Location site
try {
    $list = & npx @wrangler pages project list 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) { throw "Could not reach Cloudflare. Logged in? Run: npx wrangler login`n$list" }
    if ($list -notmatch "(?m)\b$([regex]::Escape($Project))\b") {
        "Creating Cloudflare Pages project '$Project'..."
        Run npx ($wrangler + @('pages', 'project', 'create', $Project, '--production-branch', 'main'))
    }

    # 4. upload
    Run npx ($wrangler + @('pages', 'deploy', 'public', '--project-name', $Project, '--branch', 'main', '--commit-dirty=true'))
} finally {
    Pop-Location
}
