$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'scripts\project_environment.ps1')
foreach ($meshRequiredCommand in @('ffmpeg', 'ffprobe')) {
    if (-not (Test-MeshCommand $meshRequiredCommand)) { throw "$meshRequiredCommand is missing or cannot run" }
}
& (Join-Path $PSScriptRoot '.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'scripts\check_environment.py')
if ($LASTEXITCODE -ne 0) { throw "Environment check failed with exit code $LASTEXITCODE" }
