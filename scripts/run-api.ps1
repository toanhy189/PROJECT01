# Chạy API từ gốc dự án và bật UTF-8 để console hiển thị đúng tiếng Việt.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$env:PYTHONUTF8 = '1'
& (Join-Path $projectRoot '.venv\Scripts\python.exe') -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
