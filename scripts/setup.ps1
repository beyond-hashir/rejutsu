param([switch]$SkipCheck, [switch]$PreferLocalTools)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$previousInstallDir = $env:UV_PYTHON_INSTALL_DIR
$previousBinDir = $env:UV_PYTHON_BIN_DIR
. (Join-Path $PSScriptRoot 'bootstrap_tools.ps1')

function Invoke-ProjectUv {
    param([string[]]$UvArguments)
    & uv --cache-dir (Join-Path $projectRoot '.cache\uv') @UvArguments
    if ($LASTEXITCODE -ne 0) { throw "uv failed with exit code $LASTEXITCODE" }
}

function Get-VerifiedAsset {
    param([string]$Url, [string]$RelativePath, [string]$ExpectedSha256)
    $targetPath = Join-Path $projectRoot $RelativePath
    if (Test-Path -LiteralPath $targetPath) {
        if ((Get-FileHash -LiteralPath $targetPath -Algorithm SHA256).Hash.ToLower() -eq $ExpectedSha256) {
            return
        }
        Move-Item -LiteralPath $targetPath -Destination ($targetPath + '.invalid-' + [guid]::NewGuid().ToString('N'))
    }
    $temporaryPath = "$targetPath.download"
    Write-Host "Downloading $RelativePath"
    Invoke-WebRequest -UseBasicParsing -TimeoutSec 120 -Uri $Url -OutFile $temporaryPath
    if ((Get-FileHash -LiteralPath $temporaryPath -Algorithm SHA256).Hash.ToLower() -ne $ExpectedSha256) {
        throw "Downloaded asset failed its hash check: $RelativePath"
    }
    Move-Item -LiteralPath $temporaryPath -Destination $targetPath
}

Push-Location $projectRoot
try {
    Install-MeshTools -PreferLocal:$PreferLocalTools
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $projectRoot '.runtime\python'
    $env:UV_PYTHON_BIN_DIR = Join-Path $projectRoot '.runtime\bin'
    New-Item -ItemType Directory -Path 'models','assets','outputs\setup' -Force | Out-Null
    $runtimePython = Join-Path $env:UV_PYTHON_INSTALL_DIR 'cpython-3.12.13-windows-x86_64-none\python.exe'
    if (-not (Test-Path -LiteralPath $runtimePython)) {
        Invoke-ProjectUv -UvArguments @('python', 'install', '3.12.13')
    }
    $environmentPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
    $environmentHealthy = $false
    if (Test-Path -LiteralPath $environmentPython) {
        try {
            & $environmentPython -I -c "import pathlib,sys; root=pathlib.Path(sys.argv[1]).resolve(); sys.exit(0 if sys.version_info[:3] == (3,12,13) and pathlib.Path(sys.base_prefix).resolve().is_relative_to(root / '.runtime' / 'python') else 1)" $projectRoot
            $environmentHealthy = ($LASTEXITCODE -eq 0)
        }
        catch { $environmentHealthy = $false }
    }
    if ((Test-Path -LiteralPath (Join-Path $projectRoot '.venv')) -and -not $environmentHealthy) {
        # A copied venv contains absolute paths. Preserve it and rebuild locally.
        $oldEnvironment = [IO.Path]::GetFullPath((Join-Path $projectRoot '.venv'))
        $backupEnvironment = [IO.Path]::GetFullPath((Join-Path $projectRoot ('tmp\venv-before-setup-' + [guid]::NewGuid().ToString('N'))))
        $projectBoundary = [IO.Path]::GetFullPath($projectRoot).TrimEnd('\') + '\'
        if (-not $oldEnvironment.StartsWith($projectBoundary, [StringComparison]::OrdinalIgnoreCase) -or
            -not $backupEnvironment.StartsWith($projectBoundary, [StringComparison]::OrdinalIgnoreCase)) { throw 'Environment path escaped project' }
        New-Item -ItemType Directory -Path (Join-Path $projectRoot 'tmp') -Force | Out-Null
        Move-Item -LiteralPath $oldEnvironment -Destination $backupEnvironment
    }
    if (-not (Test-Path -LiteralPath $environmentPython)) {
        Invoke-ProjectUv -UvArguments @('venv', '--python', $runtimePython, '.venv')
    }
    Invoke-ProjectUv -UvArguments @('pip', 'sync', '--python', $environmentPython,
        '--require-hashes', '--only-binary', ':all:', '--link-mode', 'copy', 'requirements.lock')
    Invoke-ProjectUv -UvArguments @('pip', 'check', '--python', $environmentPython)

    $modelUrl = 'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task'
    $sampleUrl = 'https://storage.googleapis.com/mediapipe-assets/portrait.jpg'
    $modelHash = '64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff'
    $sampleHash = 'a6f11efaa834706db23f275b6115058fa87fc7f14362681e6abe14e82749de3e'
    Get-VerifiedAsset -Url $modelUrl -RelativePath 'models\face_landmarker.task' -ExpectedSha256 $modelHash
    Get-VerifiedAsset -Url $sampleUrl -RelativePath 'assets\portrait.jpg' -ExpectedSha256 $sampleHash
    # Rewrite provenance from the verified assets, including after a repair.
    & {
        [ordered]@{
            downloaded_at_utc = (Get-Date).ToUniversalTime().ToString('o')
            model = [ordered]@{path='models/face_landmarker.task';url=$modelUrl;version='float16/1';bytes=(Get-Item -LiteralPath 'models\face_landmarker.task').Length;sha256=$modelHash}
            smoke_test_image = [ordered]@{path='assets/portrait.jpg';url=$sampleUrl;bytes=(Get-Item -LiteralPath 'assets\portrait.jpg').Length;sha256=$sampleHash}
        } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath 'models\manifest.json' -Encoding utf8
    }
    if (-not $SkipCheck) {
        & $environmentPython (Join-Path $PSScriptRoot 'check_environment.py')
        if ($LASTEXITCODE -ne 0) { throw "Environment check failed with exit code $LASTEXITCODE" }
    }
}
finally {
    $env:UV_PYTHON_INSTALL_DIR = $previousInstallDir
    $env:UV_PYTHON_BIN_DIR = $previousBinDir
    Pop-Location
}
