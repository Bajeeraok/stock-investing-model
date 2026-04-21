# Windows Task Scheduler: run daily after market close.
# Action: Program = powershell.exe
#         Arguments = -ExecutionPolicy Bypass -File "C:\path\to\stock-investing-model\backend\scripts\run_eod_snapshot.ps1"
#         Start in = C:\path\to\stock-investing-model\backend
#
# Or: Program = python / py  Arguments = scripts\run_eod_snapshot.py  Start in = ...\backend

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

$py = $null
if (Get-Command py -ErrorAction SilentlyContinue) { $py = "py" }
elseif (Get-Command python -ErrorAction SilentlyContinue) { $py = "python" }
else {
    Write-Error "Python not found on PATH."
    exit 1
}

& $py scripts/run_eod_snapshot.py
exit $LASTEXITCODE
