# Run before every processing session, including agent-driven CLI use.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'scripts\project_environment.ps1')
$meshEnvironmentReady = $false
$meshEnvironmentPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $meshEnvironmentPython) {
    try {
        & (Join-Path $PSScriptRoot 'Check-Environment.ps1')
        $meshEnvironmentReady = $true
    }
    catch { Write-Host "Environment needs setup: $($_.Exception.Message)" }
}
if (-not $meshEnvironmentReady) {
    Write-Host 'Setting up the local runtime, tools, locked packages and face model...'
    & (Join-Path $PSScriptRoot 'scripts\setup.ps1')
    # Setup adjusts this process PATH; refresh discovery as well.
    . (Join-Path $PSScriptRoot 'scripts\project_environment.ps1')
}
