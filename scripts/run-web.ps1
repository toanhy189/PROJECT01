# Chạy Vite trong thư mục frontend, giữ terminal để xem trạng thái và dừng server.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath (Join-Path $projectRoot 'frontend')
npm run dev
