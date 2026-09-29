# One-time setup on Windows (PowerShell). Requires Python >= 3.10 and Node >= 20.9.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\pip.exe install --index-url https://download.pytorch.org/whl/cpu torch
.\.venv\Scripts\pip.exe install -r backend\requirements-dev.txt
Push-Location frontend; npm ci --no-audit --no-fund; Pop-Location
Write-Host "setup done - next: .\scripts\run.ps1" -ForegroundColor Green
