# Windows: pipeline (first run), API on :8000 in a new window, web app on :3000.
param([switch]$Refresh)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$env:PYTHONPATH = (Join-Path (Get-Location) "backend")
$py = ".\.venv\Scripts\python.exe"
if ($Refresh -or -not (Test-Path "backend\data\lake\plan_latest.parquet")) {
  & $py -m gridalpha.cli run --quick
}
Start-Process -FilePath $py -ArgumentList "-m","uvicorn","gridalpha.api.main:app","--app-dir","backend","--port","8000"
Push-Location frontend
npm run build
npm run start
Pop-Location
