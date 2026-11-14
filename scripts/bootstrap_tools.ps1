# Publisher downloads stay inside the project; no admin or global PATH edits.
. (Join-Path $PSScriptRoot 'project_environment.ps1')

function Get-MeshVerifiedDownload {
    param([string]$Url, [string]$Destination, [string]$Sha256)
    if ((Test-Path -LiteralPath $Destination) -and
        ((Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash -eq $Sha256)) { return }
    New-Item -ItemType Directory -Path (Split-Path -Parent $Destination) -Force | Out-Null
    $meshDownload = "$Destination.download"
    # TLS 1.2 is needed by the stock Windows PowerShell 5.1 launcher.
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    Write-Host "Downloading $Url"
    $meshOldProgress = $ProgressPreference
    try {
        $ProgressPreference = 'SilentlyContinue'
        Invoke-WebRequest -UseBasicParsing -TimeoutSec 180 -Uri $Url -OutFile $meshDownload
    }
    finally { $ProgressPreference = $meshOldProgress }
    if ((Get-FileHash -LiteralPath $meshDownload -Algorithm SHA256).Hash -ne $Sha256) {
        throw "Publisher checksum mismatch: $Url. Nothing from this download was executed."
    }
    Move-Item -LiteralPath $meshDownload -Destination $Destination -Force
}

function Install-MeshTools {
    param([switch]$PreferLocal)
    if ($env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitOperatingSystem -or
        $env:PROCESSOR_ARCHITECTURE -eq 'ARM64' -or $env:PROCESSOR_ARCHITEW6432 -eq 'ARM64') {
        throw 'The bundled installer supports Windows x64. This project has not been validated on other platforms.'
    }
    $meshCache = Join-Path $meshProjectRoot '.cache\downloads'
    if ($PreferLocal -or -not (Test-MeshCommand 'uv')) {
        $meshUvTarget = Join-Path $meshProjectRoot '.runtime\uv'
        $meshLocalUvHealthy = $false
        if (Test-Path -LiteralPath (Join-Path $meshUvTarget 'uv.exe')) {
            try { & (Join-Path $meshUvTarget 'uv.exe') --version *> $null; $meshLocalUvHealthy = ($LASTEXITCODE -eq 0) } catch { }
        }
        if (-not $meshLocalUvHealthy) {
            $meshUvZip = Join-Path $meshCache 'uv-0.11.26-windows-x64.zip'
            Get-MeshVerifiedDownload -Url 'https://releases.astral.sh/github/uv/releases/download/0.11.26/uv-x86_64-pc-windows-msvc.zip' `
                -Destination $meshUvZip -Sha256 '4e1278ede866be6c0bf32d2f466cc6de7a9fb399ecf20c9ce2d186e52424be47'
            Expand-Archive -LiteralPath $meshUvZip -DestinationPath $meshUvTarget -Force
        }
        $env:PATH = "$meshUvTarget;$env:PATH"
        if (-not (Test-MeshCommand 'uv')) { throw 'Downloaded uv could not run.' }
    }
    if ($PreferLocal -or -not (Test-MeshCommand 'ffmpeg') -or -not (Test-MeshCommand 'ffprobe')) {
        $meshFfmpegTarget = Join-Path $meshProjectRoot '.runtime\ffmpeg'
        $meshFfmpegZip = Join-Path $meshCache 'ffmpeg-9.0.2-essentials_build.zip'
        Get-MeshVerifiedDownload -Url 'https://github.com/GyanD/codexffmpeg/releases/download/9.0.2/ffmpeg-9.0.2-essentials_build.zip' `
            -Destination $meshFfmpegZip -Sha256 '60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba'
        # Preserve publisher README/license alongside the executables.
        Expand-Archive -LiteralPath $meshFfmpegZip -DestinationPath $meshFfmpegTarget -Force
        $meshExtractedBin = Join-Path $meshFfmpegTarget 'ffmpeg-9.0.2-essentials_build\bin'
        $meshLocalBin = Join-Path $meshFfmpegTarget 'bin'
        New-Item -ItemType Directory -Path $meshLocalBin -Force | Out-Null
        foreach ($meshExe in @('ffmpeg.exe', 'ffprobe.exe')) {
            Copy-Item -LiteralPath (Join-Path $meshExtractedBin $meshExe) -Destination (Join-Path $meshLocalBin $meshExe) -Force
        }
        $env:PATH = "$meshLocalBin;$env:PATH"
        if (-not (Test-MeshCommand 'ffmpeg') -or -not (Test-MeshCommand 'ffprobe')) {
            throw 'Downloaded FFmpeg tools could not run.'
        }
    }
}
