# Stock Investing Model - Dev mode (hot reload)
# Usage: .\scripts\dev.ps1

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $ProjectRoot

Write-Host "Starting dev environment with hot reload..." -ForegroundColor Cyan
Write-Host "Backend: changes auto-restart | Web: Next.js hot-reloads" -ForegroundColor Gray
docker compose -f docker-compose.dev.yml up --build
