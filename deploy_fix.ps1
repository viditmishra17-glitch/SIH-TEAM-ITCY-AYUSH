# ---------------------------------------------------------------------------
# Rebuild the frontend bundle and push it, so Render stops serving a stale UI.
#
# Render serves frontend/dist straight from the repository, so the bundle has
# to be COMMITTED — building locally is not enough.
#
# Run from the repository root:
#     powershell -ExecutionPolicy Bypass -File deploy_fix.ps1
#
# Build and check, but do not commit or push:
#     powershell -ExecutionPolicy Bypass -File deploy_fix.ps1 -NoPush
# ---------------------------------------------------------------------------

param(
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

# --- 2. Build ---------------------------------------------------------------
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

if ($NoPush) {
    Info ""
    Info "-NoPush set: built only, nothing committed."
    exit 0
}

# --- 3. Commit and push -----------------------------------------------------
$changed = git status --porcelain
if (-not $changed) {
    Warn ""
    Warn "Nothing changed - the committed bundle already matches this build."
    Warn "If Render is still showing an old UI, it is browser cache: Ctrl+Shift+R."
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
Good "Pushed. Render auto-deploys - give it a couple of minutes, then hard-refresh (Ctrl+Shift+R)."
Write-Host ""
Write-Host "Still to do on Vercel (dashboard only, I cannot do it from here):" -ForegroundColor Cyan
Write-Host "  1. Settings -> Environment Variables"
Write-Host "  2. VITE_API_BASE_URL = https://<your-service>.onrender.com   (no trailing slash, scope Production)"
Write-Host "  3. Deployments -> ... -> Redeploy       <- required; env vars only apply to NEW builds"
Write-Host ""
Write-Host "To confirm the backend URL is baked in, after redeploying:" -ForegroundColor Cyan
Write-Host "  open the Vercel site, DevTools -> Network, reload, and check that"
Write-Host "  the /health request goes to onrender.com and not to vercel.app."