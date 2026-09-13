# ---------------------------------------------------------------------------
# Push TriVerify to GitHub.
#
# Run from the repository root:
#     powershell -ExecutionPolicy Bypass -File push_to_github.ps1
#
# See exactly what would happen, without touching anything:
#     powershell -ExecutionPolicy Bypass -File push_to_github.ps1 -DryRun
#
# Push somewhere else:
#     powershell -ExecutionPolicy Bypass -File push_to_github.ps1 -RemoteUrl "https://github.com/<owner>/<repo>.git"
# ---------------------------------------------------------------------------

param(
    [string]$RemoteUrl = "https://github.com/viditmishra17-glitch/SIH-TEAM-ITCY-AYUSH.git",
    [string]$Branch    = "main",
    [string]$Message   = "TriVerify: three-layer Legal Metrology compliance scanner",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Say  ($t) { Write-Host $t }
function Info ($t) { Write-Host $t -ForegroundColor Cyan }
function Good ($t) { Write-Host $t -ForegroundColor Green }
function Warn ($t) { Write-Host $t -ForegroundColor Yellow }
function Bad  ($t) { Write-Host $t -ForegroundColor Red }

# --- 1. Sanity: is git here, and is this the project? ----------------------
try { git --version | Out-Null }
catch { Bad "git is not installed or not on PATH. Install Git for Windows first."; exit 1 }

$required = @(
    "backend\app\main.py",
    "backend\requirements.txt",
    "frontend\src\App.jsx",
    "README.md"
)
$missing = $required | Where-Object { -not (Test-Path $_) }
if ($missing) {
    Bad "This does not look like the TriVerify root. Missing:"
    $missing | ForEach-Object { Bad "  $_" }
    exit 1
}
Good "Project structure looks right."

# --- 2. Warn if the old layout is still lying around -----------------------
$stale = @("api", "engine", "pipeline", "db", "web", "config.py") | Where-Object { Test-Path $_ }
if ($stale) {
    Warn ""
    Warn "The OLD folder layout is still present: $($stale -join ', ')"
    Warn "Pushing now would commit two copies of the project."
    Warn "Run this first:  powershell -ExecutionPolicy Bypass -File cleanup_old_layout.ps1"
    Warn ""
    $go = Read-Host "Continue anyway? (y/N)"
    if ($go -ne "y") { Say "Stopped."; exit 1 }
}

# --- 3. Git identity -------------------------------------------------------
$who   = (git config user.name)  2>$null
$email = (git config user.email) 2>$null
if (-not $who -or -not $email) {
    Warn "Git identity is not set. Setting it is a one-time thing:"
    Say  '  git config --global user.name  "Your Name"'
    Say  '  git config --global user.email "you@example.com"'
    exit 1
}
Say "Committing as $who <$email>"

# --- 4. Repository + remote ------------------------------------------------
if (-not (Test-Path ".git")) {
    Info "No git repository here yet - initialising."
    if (-not $DryRun) {
        git init | Out-Null
        git branch -M $Branch
    }
}

$current = (git remote get-url origin) 2>$null
if ($current) {
    if ($current -ne $RemoteUrl) {
        Warn ""
        Warn "origin currently points at:"
        Warn "    $current"
        Warn "and this script will point it at:"
        Warn "    $RemoteUrl"
        Warn ""
        $go = Read-Host "Change the remote? (y/N)"
        if ($go -ne "y") { Say "Stopped. Nothing changed."; exit 1 }
        if (-not $DryRun) { git remote set-url origin $RemoteUrl }
    }
    else { Say "origin already points at $RemoteUrl" }
}
else {
    Info "Adding origin -> $RemoteUrl"
    if (-not $DryRun) { git remote add origin $RemoteUrl }
}

# --- 5. Show what is about to be committed ---------------------------------
Info ""
Info "Staging files (respecting .gitignore)..."
if (-not $DryRun) { git add -A }

$staged = if ($DryRun) { git status --porcelain } else { git diff --cached --name-only }
$count  = ($staged | Measure-Object).Count

if ($count -eq 0) {
    Warn "Nothing to commit - the working tree already matches the last commit."
}
else {
    Say ""
    Say "$count file(s) staged. First 25:"
    $staged | Select-Object -First 25 | ForEach-Object { Say "  $_" }
    if ($count -gt 25) { Say "  ... and $($count - 25) more" }
}

# Guard: these must never reach a public repository.
$danger = $staged | Where-Object {
    $_ -match '(^|/)\.venv/' -or $_ -match '(^|/)node_modules/' -or
    $_ -match '(^|/)\.env$'  -or $_ -match '\.db$'
}
if ($danger) {
    Bad ""
    Bad "STOPPING - these should not be committed:"
    $danger | Select-Object -First 15 | ForEach-Object { Bad "  $_" }
    Bad "Check .gitignore, then run:  git reset"
    exit 1
}
Good "No virtualenv, node_modules, .env or database files staged."

if ($DryRun) {
    Info ""
    Info "DRY RUN - nothing was committed or pushed."
    Info "Re-run without -DryRun to push to $RemoteUrl"
    exit 0
}

# --- 6. Commit -------------------------------------------------------------
if ($count -gt 0) {
    git commit -m $Message | Out-Null
    Good "Committed: $Message"
}

# --- 7. Push ---------------------------------------------------------------
Info ""
Info "Pushing to $RemoteUrl ($Branch)..."
Say  "A browser or credential prompt may appear - sign in as the repo owner."
Say  ""

git push -u origin $Branch
if ($LASTEXITCODE -eq 0) {
    Good ""
    Good "Pushed. Open:  $($RemoteUrl -replace '\.git$','')"
    exit 0
}

# --- 8. Push failed - explain the usual cause ------------------------------
Bad ""
Bad "The push was rejected."
Say ""
Say "The usual cause is that the GitHub repo already has a commit (a README"
Say "created with the repo) and your local history is separate. Pick one:"
Say ""
Say "  A) Keep both histories - merge theirs in, then push again:"
Say "       git pull origin $Branch --allow-unrelated-histories --no-rebase"
Say "       git push -u origin $Branch"
Say ""
Say "  B) Make this the repo's content, discarding what is on GitHub."
Say "     Only if you are certain nobody else has pushed work there:"
Say "       git push -u origin $Branch --force"
Say ""
Say "If instead it failed on authentication, sign in as the account that owns"
Say "the repository, or ask its owner to add you as a collaborator."
exit 1
