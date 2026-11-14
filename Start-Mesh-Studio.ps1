param(
    [ValidateRange(1024,65535)][int]$Port = 8765,
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'Ensure-Environment.ps1')
. (Join-Path $PSScriptRoot 'scripts\project_environment.ps1')
$meshPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $meshPython)) { throw 'The local Python environment is missing. Run scripts\setup.ps1 first.' }
Push-Location $PSScriptRoot
try {
    $meshServerArguments = @((Join-Path $PSScriptRoot 'scripts\web_server.py'), '--port', $Port)
    if (-not $NoBrowser) { $meshServerArguments += '--open' }
    & $meshPython @meshServerArguments
    if ($LASTEXITCODE -ne 0) { throw "Mesh Studio stopped with exit code $LASTEXITCODE. If the port is already in use, try -Port 8766." }
}
finally { Pop-Location }
