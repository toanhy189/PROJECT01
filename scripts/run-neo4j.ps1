# Khởi động database local rồi migration snapshot đã kiểm tra, không tạo lại embedding.
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
& $pythonPath -X utf8 -m ingestion.setup_neo4j
if ($LASTEXITCODE -ne 0) { throw "Không chuẩn bị được cấu hình Neo4j." }
docker compose --progress quiet -f compose.neo4j.yml up -d --wait --wait-timeout 90
if ($LASTEXITCODE -ne 0) { throw "Hãy mở Docker Desktop, kiểm tra cổng và chạy lại script." }
& $pythonPath -X utf8 -m ingestion.migrate_neo4j
if ($LASTEXITCODE -ne 0) { throw "Migration chưa đạt; giữ nguyên Chroma và snapshot active." }
Write-Output "Neo4j Browser: http://localhost:17474 (nếu không đổi NEO4J_HTTP_PORT)."
Write-Output "User: neo4j. Mật khẩu nằm trong NEO4J_PASSWORD của .env."
