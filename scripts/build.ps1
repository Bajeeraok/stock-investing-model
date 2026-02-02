# Stock Investing Model - Docker Build Script
# Usage: .\scripts\build.ps1 [backend|web|all]

param(
    [Parameter(Position=0)]
    [ValidateSet("backend", "web", "all")]
    [string]$Target = "all"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

function Build-Backend {
    Write-Host "Building backend..." -ForegroundColor Cyan
    docker build -t stock-investing-backend $ProjectRoot/backend
}

function Build-Web {
    Write-Host "Building web..." -ForegroundColor Cyan
    docker build -t stock-investing-web $ProjectRoot/web
}

function Build-All {
    Build-Backend
    Build-Web
    Write-Host "`nBuild complete. Run: docker compose up" -ForegroundColor Green
}

switch ($Target) {
    "backend" { Build-Backend }
    "web"     { Build-Web }
    "all"     { Build-All }
}
