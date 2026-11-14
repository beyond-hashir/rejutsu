# Shared, project-local tool discovery. Dot-source before launching Python.
$meshProjectRoot = Split-Path -Parent $PSScriptRoot
foreach ($meshToolDirectory in @('.runtime\uv', '.runtime\ffmpeg\bin')) {
    $meshToolPath = Join-Path $meshProjectRoot $meshToolDirectory
    if ((Test-Path -LiteralPath $meshToolPath) -and (($env:PATH -split ';') -notcontains $meshToolPath)) {
        $env:PATH = "$meshToolPath;$env:PATH"
    }
}

function Test-MeshCommand {
    param([string]$Name)
    $meshCommand = Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $meshCommand) { return $false }
    try {
        $meshVersionArgument = if ($Name -eq 'uv') { '--version' } else { '-version' }
        & $meshCommand.Source $meshVersionArgument *> $null
        return ($LASTEXITCODE -eq 0)
    }
    catch { return $false }
}
