# Cài môi trường local, giữ nguyên cấu hình .env nếu người dùng đã tạo.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$env:PYTHONUTF8 = '1'
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Khong tao duoc moi truong Python.' }
}
$pythonMinor = & '.\.venv\Scripts\python.exe' -c 'import sys; print(str(sys.version_info.major) + chr(46) + str(sys.version_info.minor))'
# Bản khóa đã được kiểm thử trên Python 3.13; bản khác để pip chọn phiên bản tương thích.
$dependencyFile = if ($pythonMinor -eq '3.13') { 'requirements.lock.txt' } else { 'requirements.txt' }
& '.\.venv\Scripts\python.exe' -m pip install -r $dependencyFile
if ($LASTEXITCODE -ne 0) { throw 'Cai dependencies Python that bai.' }
if (-not (Test-Path -LiteralPath '.env')) {
    Copy-Item -LiteralPath '.env.example' -Destination '.env'
}
Push-Location -LiteralPath 'frontend'
try {
    npm ci --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw 'Cai dependencies React that bai.' }
} finally {
    Pop-Location
}
Write-Output 'Da cai xong. Chay scripts/run-api.ps1 va scripts/run-web.ps1 trong hai terminal.'
