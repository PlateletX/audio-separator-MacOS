# bootstrap.ps1 - Universal Portable Python Environment Deployer
# Uses python-build-standalone (github.com/indygreg/python-build-standalone)
# for a truly portable Python with ZERO system impact:
#   - Full stdlib including tkinter, sqlite3, ssl, etc.
#   - ZERO registry entries
#   - ZERO PATH modification
#   - ZERO file association changes
#   - Just extract and use
#
# Deployment flow (generic for any Python project):
#   Step 1: Download python-build-standalone archive
#   Step 2: Extract to python_env/
#   Step 3: Run init_env.py if exists (project-specific optional hook)
#   Step 4: pip install -r requirements.txt if exists (standard packages)
#   Then write .deploy_complete marker. Does NOT launch the app.
#
# Usage: Called from project-level BAT, or: pwsh -File bootstrap.ps1

$ErrorActionPreference = "Stop"

# ===== PYTHON VERSION CONFIG (developers: modify here) =====
# Available versions: https://github.com/indygreg/python-build-standalone/releases
# Format: $PythonVersion = full version, $ReleaseTag = release date tag
#
# Common combinations:
#   3.10.11 / 20230507   (stable, wide compatibility with ML/AI libs)
#   3.10.14 / 20240415   (latest 3.10.x patch)
#   3.11.9  / 20240415   (newer features, good compat)
#   3.12.3  / 20240415   (latest, some libs may not support yet)
#
$PythonVersion = "3.11.9"
$ReleaseTag    = "20240415"
# ============================================================

# ===== PATHS =====
$BasePath      = $PSScriptRoot
$EnvDir        = Join-Path $BasePath "python_env"
$MarkerFile    = Join-Path $EnvDir ".deploy_complete"
$PythonExe     = Join-Path $EnvDir "python.exe"
$InitScript    = Join-Path $BasePath "init_env.py"
$ReqFile       = Join-Path $BasePath "requirements.txt"
$PipMirror     = "https://mirrors.aliyun.com/pypi/simple/"

# ===== PYTHON DOWNLOAD CONFIG =====
$ArchiveName = "cpython-$PythonVersion+$ReleaseTag-x86_64-pc-windows-msvc-shared-install_only.tar.gz"
$GitHubUrl   = "https://github.com/indygreg/python-build-standalone/releases/download/$ReleaseTag/$ArchiveName"

$DownloadUrls = @(
    "https://ghproxy.net/$GitHubUrl",    # GitHub proxy (fast in China)
    "https://gh-proxy.com/$GitHubUrl",   # Fallback proxy
    $GitHubUrl                             # Direct GitHub (overseas / VPN)
)

$ArchiveLocal = Join-Path $BasePath $ArchiveName

# ===== FUNCTIONS =====
function Exit-WithError {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# ---- Skip python deployment if already fully deployed ----
if (Test-Path $MarkerFile) {
    Write-Host "[bootstrap] Already deployed. Skipping python deployment." -ForegroundColor Green
    exit 0
}

Write-Host "========================================"
Write-Host "  Portable Python Deployer (standalone)"
Write-Host "  Python $PythonVersion | Zero registry impact"
Write-Host "========================================"

# ---- Step 1: Download python-build-standalone archive ----
if (-not (Test-Path $PythonExe)) {
    if (-not (Test-Path $ArchiveLocal)) {
        Write-Host "[1/4] Downloading Python $PythonVersion standalone (~40MB)..." -ForegroundColor Yellow
        $downloaded = $false
        foreach ($url in $DownloadUrls) {
            Write-Host "      Source: $url" -ForegroundColor DarkGray
            try {
                Invoke-WebRequest -Uri $url -OutFile $ArchiveLocal -UseBasicParsing
                if ((Get-Item $ArchiveLocal).Length -lt 1MB) {
                    throw "Downloaded file too small, likely an error page"
                }
                $downloaded = $true
                Write-Host "      Download complete." -ForegroundColor Green
                break
            }
            catch {
                Write-Host "      Failed: $($_.Exception.Message)" -ForegroundColor DarkYellow
                if (Test-Path $ArchiveLocal) { Remove-Item $ArchiveLocal -Force }
            }
        }
        if (-not $downloaded) {
            Exit-WithError ("All download sources failed. Check your network.`n" +
                "You can also download manually and place it here:`n" +
                "  File: $ArchiveName`n" +
                "  URL:  $GitHubUrl")
        }
    }
    else {
        Write-Host "[1/4] Found local archive: $ArchiveName" -ForegroundColor Green
    }

    # ---- Step 2: Extract archive to python_env/ ----
    Write-Host "[2/4] Extracting Python to python_env/ ..." -ForegroundColor Yellow

    # python-build-standalone archives extract to a "python/" subdirectory
    $TempExtractDir = Join-Path $BasePath "_python_extract_temp"
    if (Test-Path $TempExtractDir) { Remove-Item $TempExtractDir -Recurse -Force }
    New-Item -ItemType Directory -Path $TempExtractDir | Out-Null

    try {
        # Windows 10 1803+ and Windows 11 have native tar.exe
        $tarExe = Join-Path $env:SystemRoot "System32\tar.exe"
        if (-not (Test-Path $tarExe)) {
            throw "tar.exe not found. Requires Windows 10 version 1803 or later."
        }
        & $tarExe -xzf $ArchiveLocal -C $TempExtractDir 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "tar extraction failed with exit code $LASTEXITCODE" }
    }
    catch {
        if (Test-Path $TempExtractDir) { Remove-Item $TempExtractDir -Recurse -Force }
        Exit-WithError "Failed to extract archive: $($_.Exception.Message)"
    }

    # Locate the extracted python directory
    $ExtractedPythonDir = Join-Path $TempExtractDir "python"
    if (-not (Test-Path (Join-Path $ExtractedPythonDir "python.exe"))) {
        # Fallback: python.exe might be directly in temp dir
        if (Test-Path (Join-Path $TempExtractDir "python.exe")) {
            $ExtractedPythonDir = $TempExtractDir
        }
        else {
            if (Test-Path $TempExtractDir) { Remove-Item $TempExtractDir -Recurse -Force }
            Exit-WithError "Unexpected archive structure: python.exe not found after extraction."
        }
    }

    # Move to final location
    if (Test-Path $EnvDir) { Remove-Item $EnvDir -Recurse -Force }
    Move-Item -Path $ExtractedPythonDir -Destination $EnvDir

    # Cleanup temp files
    if (Test-Path $TempExtractDir) { Remove-Item $TempExtractDir -Recurse -Force }
    # 保留 Python 安装包压缩文件，便于后续重复部署或离线复用

    Write-Host "      Python extracted to python_env/" -ForegroundColor Green
}
else {
    Write-Host "[1-2/4] Python already present in python_env/" -ForegroundColor Green
}

# ***************---- Step 3: Run project-specific init script (if exists) ----****************
# This handles platform-dependent packages or project extras.
if (Test-Path $InitScript) {
    Write-Host "[3/4] Running init_env.py (project-specific setup)..." -ForegroundColor Yellow
    $p = Start-Process -FilePath $PythonExe -ArgumentList "-X utf8 `"$InitScript`"" -WorkingDirectory $BasePath -NoNewWindow -Wait -PassThru
    if ($p.ExitCode -ne 0) {
        Exit-WithError "init_env.py failed with exit code $($p.ExitCode)."
    }
}
else {
    Write-Host "[3/4] No init_env.py found, skipping." -ForegroundColor DarkGray
}

# ---- Step 4: Install standard requirements.txt (if exists) ----
# This is the universal pip install step, works for ANY Python project.
if (Test-Path $ReqFile) {
    Write-Host "[4/4] Installing requirements.txt ..." -ForegroundColor Yellow
    $p = Start-Process -FilePath $PythonExe -ArgumentList "-X utf8 -m pip install --isolated --no-user -i $PipMirror -r `"$ReqFile`"" -WorkingDirectory $BasePath -NoNewWindow -Wait -PassThru
    if ($p.ExitCode -ne 0) {
        Exit-WithError "pip install -r requirements.txt failed with exit code $($p.ExitCode)."
    }
}
else {
    Write-Host "[4/4] No requirements.txt found, skipping." -ForegroundColor DarkGray
}

# ---- Mark deployment as complete ----
$markerContent = "Deployed: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') | Python $PythonVersion (standalone, zero-registry)"
$markerContent | Set-Content -Path $MarkerFile -Encoding UTF8

Write-Host ""
Write-Host "========================================"
Write-Host "[bootstrap] Deployment complete!" -ForegroundColor Green
Write-Host "========================================"
exit 0
