# ---------------------------------------------------------------------------
# Rebuild the frontend bundle, sanity-check the backend address, and push.
#
# Render serves frontend/dist straight from the repository, so the bundle has
# to be COMMITTED - building locally is not enough.
#
# Run from the repository root:
#     powershell -ExecutionPolicy Bypass -File deploy_fix.ps1
#
# Set the backend address at the same time (writes frontend/public/config.js):
#     powershell -ExecutionPolicy Bypass -File deploy_fix.ps1 -ApiBase "https://your-service.onrender.com"
#
# Build and check, but do not commit or push:
#     powershell -ExecutionPolicy Bypass -File deploy_fix.ps1 -NoPush
# ---------------------------------------------------------------------------

param(
    [string]$ApiBase,
    [switch]$NoPush,
    [string]$Message = "Rebuild frontend bundle"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Info ($t) { Write-Host $t -ForegroundColor Cyan }
function Good ($t) { Write-Host $t -ForegroundColor Green }
function Warn ($t) { Write-Host $t -ForegroundColor Yellow }
function Bad  ($t) { Write-Host $t -ForegroundColor Red }

if (-not (Test-Path "frontend\package.json")) {
    Bad "Run this from the repository root (the folder holding backend\ and frontend\)."
    exit 1
}

# --- 1. Refuse to build over unresolved merge conflicts --------------------
Info "Checking for unresolved merge conflicts..."
$markers = Get-ChildItem -Recurse frontend\src -Include *.jsx, *.js, *.css -ErrorAction SilentlyContinue |
           Select-String -Pattern '^<<<<<<<|^=======$|^>>>>>>>'
if ($markers) {
    Bad "Unresolved conflict markers found - the build would fail:"
    $markers | ForEach-Object { Bad ("  {0}:{1}" -f $_.Path, $_.LineNumber) }
    Bad "Open those files and accept one side of each conflict, then re-run."
    exit 1
}
Good "  none found."

# --- 2. Backend address -----------------------------------------------------
$configPath = "frontend\public\config.js"

if ($PSBoundParameters.ContainsKey("ApiBase")) {
    $clean = $ApiBase.Trim().TrimEnd("/")
    if ($clean -and $clean -notmatch '^https?://') { $clean = "https://$clean" }

    @"
/* PARAKH runtime configuration - copied into dist/ verbatim, NOT bundled.
   Change this line to repoint the API; no rebuild of the JS is required.
   Leave it as "" when FastAPI serves this bundle itself (same origin). */

window.__PARAKH_API_BASE__ = "$clean";
"@ | Set-Content -Path $configPath -Encoding UTF8 -NoNewline

    Good "  wrote $configPath -> `"$clean`""
}
elseif (Test-Path $configPath) {
    $current = (Get-Content $configPath -Raw)
    if ($current -match '__PARAKH_API_BASE__\s*=\s*"([^"]*)"') {
        $set = $Matches[1]
        if ($set) { Good "  config.js points at $set" }
        else {
            Warn "  config.js is empty, so the app will call its OWN origin."
            Warn "  That is correct for Render (FastAPI serves the bundle)."
            Warn "  It is WRONG for Vercel, where there is no backend on that origin."
            Warn "  Fix with:  .\deploy_fix.ps1 -ApiBase `"https://your-service.onrender.com`""
        }
    }
}
else {
    Warn "  $configPath is missing - the runtime override will not be available."
}

# --- 3. Build ---------------------------------------------------------------
Push-Location frontend
try {
    if (-not (Test-Path "node_modules")) {
        Info "node_modules missing - installing first (this takes a minute)..."
        npm install
        if ($LASTEXITCODE -ne 0) { Bad "npm install failed."; exit 1 }
    }

    Info "Building the frontend bundle..."
    npm run build
    if ($LASTEXITCODE -ne 0) {
        Bad "The build failed. Nothing was committed."
        exit 1
    }
}
finally { Pop-Location }

$asset = Get-ChildItem "frontend\dist\assets" -Filter "*.js" -ErrorAction SilentlyContinue |
         Select-Object -First 1
if (-not $asset) { Bad "No bundle in frontend\dist\assets after the build."; exit 1 }
Good ("  built {0} ({1:N0} bytes)" -f $asset.Name, $asset.Length)

if (-not (Test-Path "frontend\dist\config.js")) {
    Bad "frontend\dist\config.js is missing after the build."
    Bad "Check that frontend\public\config.js exists - Vite copies public/ into dist/."
    exit 1
}
Good "  dist\config.js present."

if ($NoPush) {
    Info ""
    Info "-NoPush set: built only, nothing committed."
    exit 0
}

# --- 4. Commit and push -----------------------------------------------------
$changed = git status --porcelain
if (-not $changed) {
    Warn ""
    Warn "Nothing changed - the committed bundle already matches this build."
    Warn "If a deployed site still looks stale, it is browser cache: Ctrl+Shift+R."
    exit 0
}

Info ""
Info "Committing:"
$changed | Select-Object -First 20 | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }

git add -A
git commit -m $Message | Out-Null
Good "Committed."

Info "Pushing..."
git push
if ($LASTEXITCODE -ne 0) {
    Bad "The push failed. Fix the error above, then run: git push"
    exit 1
}

Good ""
Good "Pushed. Render and Vercel both auto-deploy - give them a couple of minutes,"
Good "then hard-refresh (Ctrl+Shift+R)."
Write-Host ""
Write-Host "If the deployed page shows an orange 'Backend unreachable' bar, type the" -ForegroundColor Cyan
Write-Host "backend URL into it and press Connect. That works immediately, with no"  -ForegroundColor Cyan
Write-Host "rebuild, and tells you whether the address or CORS is the problem."      -ForegroundColor Cyan
