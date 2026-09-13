# One-command demo for Windows PowerShell.
# Run from the repository root:
#     powershell -ExecutionPolicy Bypass -File backend\scripts\demo.ps1
#
# Activate the virtualenv first if you have one:
#     .\.venv\Scripts\Activate.ps1

$ErrorActionPreference = "Stop"

# scripts\ -> backend\ : run everything from the backend directory.
$BackendDir = Split-Path $PSScriptRoot -Parent
Set-Location $BackendDir

Write-Host "==> Seeding the four golden cases..." -ForegroundColor Cyan
python -m app.seed

Write-Host ""
Write-Host "==> Starting TriVerify on http://127.0.0.1:8000" -ForegroundColor Cyan
Write-Host "    The React dashboard (frontend/dist) is served from the same address." -ForegroundColor DarkGray
Write-Host "    Press Ctrl+C to stop." -ForegroundColor DarkGray
Write-Host ""
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
