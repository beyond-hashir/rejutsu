param(
    [ValidateSet('inspect','track','render','run')][string]$Action = 'run',
    [string]$Original = 'original.mp4',
    [string]$Depth = 'depth video.mp4',
    [string]$OutputDirectory = 'outputs\finished',
    [string]$Alignment = '',
    [ValidateRange(1,8)][int]$MaxFaces = 4,
    [ValidateSet('mesh','contours','dots')][string]$Style = 'mesh',
    [ValidateRange(0.0,1.0)][double]$Opacity = 0.8,
    [ValidateRange(1,8)][int]$Thickness = 1,
    [ValidatePattern('^#?[0-9a-fA-F]{6}$')][string]$Color = '00FFFF',
    [ValidateRange(0.0,1000.0)][double]$SmoothingMs = 12,
    [int[]]$OnlyTracks,
    [switch]$Dots,
    [switch]$NoPreview
)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'Ensure-Environment.ps1')
. (Join-Path $PSScriptRoot 'scripts\project_environment.ps1')
Push-Location $PSScriptRoot
try {
    $meshArguments = @($Action, '--original', $Original, '--depth', $Depth, '--out', $OutputDirectory,
        '--max-faces', $MaxFaces, '--style', $Style, '--opacity', $Opacity.ToString([cultureinfo]::InvariantCulture),
        '--thickness', $Thickness, '--color', $Color, '--smoothing-ms', $SmoothingMs.ToString([cultureinfo]::InvariantCulture))
    if ($Alignment) { $meshArguments += @('--alignment', $Alignment) }
    if ($OnlyTracks) { $meshArguments += '--only-tracks'; $meshArguments += $OnlyTracks }
    if ($Dots) { $meshArguments += '--dots' }
    if ($NoPreview) { $meshArguments += '--no-preview' }
    & (Join-Path $PSScriptRoot '.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'scripts\mesh_video.py') `
        @meshArguments
    if ($LASTEXITCODE -ne 0) { throw "Mesh workflow failed with exit code $LASTEXITCODE" }
}
finally { Pop-Location }
