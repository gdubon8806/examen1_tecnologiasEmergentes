# Uso (PowerShell, dentro de la carpeta data-platform):  .\setup.ps1
# Si da error de permisos:  Set-ExecutionPolicy -Scope Process Bypass
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".env")) { throw "Falta el archivo .env (copia .env.example y renombralo a .env)" }

# Leer la contraseña del .env
$pass = (Get-Content .env | Where-Object { $_ -match '^MSSQL_SA_PASSWORD=' }) -replace '^MSSQL_SA_PASSWORD=', ''
if (-not $pass) { throw "No encontre MSSQL_SA_PASSWORD en .env" }

$bak = "database\backups\WideWorldImporters-Full.bak"
$url = "https://github.com/Microsoft/sql-server-samples/releases/download/wide-world-importers-v1.0/WideWorldImporters-Full.bak"
if (-not (Test-Path $bak)) {
    Write-Host ">> Descargando WideWorldImporters (~120 MB)..."
    curl.exe -L -o $bak $url
}

Write-Host ">> Levantando SQL Server en Docker..."
docker compose up -d

Write-Host ">> Esperando a que SQL Server este listo (puede tardar 1-2 min)..."
do {
    Start-Sleep -Seconds 5
    $status = docker inspect -f "{{.State.Health.Status}}" dp_sqlserver
} while ($status -ne "healthy")

$sqlcmd = "/opt/mssql-tools18/bin/sqlcmd"
Write-Host ">> Restaurando WideWorldImporters (puede tardar varios minutos, es normal)..."
docker compose exec -T sqlserver $sqlcmd -S localhost -U sa -P $pass -C -b -i /scripts/01_restore_wwi.sql
Write-Host ">> Creando AnalyticsDW (raw, clean, dw, audit)..."
docker compose exec -T sqlserver $sqlcmd -S localhost -U sa -P $pass -C -b -i /scripts/02_create_dw_structure.sql

Write-Host ">> LISTO. En SSMS conectate a: localhost,1434  usuario: sa"
