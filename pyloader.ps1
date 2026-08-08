# pyloader.ps1 - Universal Portable Python Environment Deployer
# Uses python-build-standalone (github.com/astral-sh/python-build-standalone)
# for a truly portable Python with ZERO system impact:
#   - Full stdlib including tkinter, sqlite3, ssl, etc.
#   - ZERO registry entries
#   - ZERO PATH modification
#   - ZERO file association changes
#   - Just extract and use
#
# Deployment flow (generic for any Python project):
#   Step 1: Download python-build-standalone archive
#   Step 2: Extract to .runtime/python/ (pure .NET, no tar.exe needed)
#   Step 3: Run init_env.py if exists (project-specific optional hook)
#   Step 4: pip install -r requirements.txt if exists (standard packages)
#   Then write .deploy_complete marker. Does NOT launch the app.
#
# Minimum: Windows 10 1507 (PowerShell 5.0, .NET 4.6)
# Usage: Called from project-level BAT, or: pwsh -File pyloader.ps1

$ErrorActionPreference = "Stop"

# ===== PYTHON VERSION CONFIG =====
# 目标：稳定获取任意可用的 Python 3.11.x，而不是锁死某个小版本或发布标签。
$PythonMajorMinor = "3.11"
# ============================================================

# ===== PATHS =====
$BasePath      = $PSScriptRoot
$RuntimeRoot   = Join-Path $BasePath ".runtime"
$EnvDir        = Join-Path $RuntimeRoot "python"
$MarkerFile    = Join-Path $EnvDir ".deploy_complete"
$ReqHashFile   = Join-Path $EnvDir ".requirements.sha256"
$PythonExe     = Join-Path $EnvDir "python.exe"
$InitScript    = Join-Path $BasePath "init_env.py"
$ReqFile       = Join-Path $BasePath "requirements.txt"
$PipMirror     = "https://mirrors.aliyun.com/pypi/simple/"

# ===== Python 下载配置 =====
# 南京大学镜像同步 python-build-standalone 最新发行版，保持 Python 3.11 大版本不变。
$MirrorLatestUrl   = "https://mirrors.nju.edu.cn/github-release/astral-sh/python-build-standalone/LatestRelease/"
$ArchiveName       = $null
$ArchiveLocal      = $null
$ResolvedPythonVersion = $null
$ResolvedReleaseTag    = $null

# ===== FUNCTIONS =====
function Exit-WithError {
    param([string]$Message)
    Write-Host ""
    Write-Host "[ERROR] 部署没有完成。" -ForegroundColor Red
    Write-Host $Message -ForegroundColor Red
    Write-Host ""
    Write-Host "请先按上面的处理建议重试；仍然失败时，请把本窗口中从 [ERROR] 开始的完整内容提供给维护者。" -ForegroundColor Yellow
    Write-Host "必读说明：$BasePath\必看说明.txt" -ForegroundColor Yellow
    Read-Host "按 Enter 键退出"
    exit 1
}

function Get-CurrentPythonVersion {
    if (-not (Test-Path $PythonExe)) {
        return $null
    }

    try {
        $version = & $PythonExe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')" 2>$null
        if ($LASTEXITCODE -ne 0) {
            return $null
        }
        return ($version | Select-Object -First 1).Trim()
    }
    catch {
        return $null
    }
}

function Get-RequirementsHash {
    if (-not (Test-Path $ReqFile)) {
        return $null
    }

    try {
        return (Get-FileHash -Path $ReqFile -Algorithm SHA256).Hash
    }
    catch {
        return $null
    }
}

function Resolve-PythonArchive {
    $escaped = [regex]::Escape($PythonMajorMinor)
    $pattern = "^cpython-($escaped\.\d+)\+(\d+)-x86_64-pc-windows-msvc-install_only\.tar\.gz$"
    $candidates = @()

    $local_archives = Get-ChildItem -LiteralPath $BasePath -File -Filter "cpython-$PythonMajorMinor.*-x86_64-pc-windows-msvc-install_only.tar.gz" -ErrorAction SilentlyContinue
    foreach ($archive in $local_archives) {
        if ($archive.Length -lt 1MB) {
            continue
        }

        $filename = [string]$archive.Name
        if ($filename -match $pattern) {
            $candidates += [pscustomobject]@{
                Href       = $null
                Version    = $matches[1]
                ReleaseTag = $matches[2]
                Filename   = $filename
                SourcePath = $archive.FullName
            }
        }
    }

    if (-not $candidates) {
        Write-Host "[scan] Querying latest standalone Python mirror..." -ForegroundColor Yellow

        try {
            $resp = Invoke-WebRequest -Uri $MirrorLatestUrl -UseBasicParsing
        }
        catch {
            Exit-WithError (
                "无法连接到 Python 下载站点。`n`n" +
                "这通常是网络、代理/VPN 或安全软件暂时中断了连接，不代表 Python 已损坏。`n`n" +
                "请按顺序尝试：`n" +
                "1. 关闭代理、VPN 和下载加速器，然后重新双击“一键启动GUI.bat”。`n" +
                "2. 检查安全软件是否拦截本程序访问网络；如果文件来源可信，请选择允许。`n" +
                "3. 换用手机热点等其他网络重试。`n`n" +
                "下载站点：$MirrorLatestUrl`n" +
                "技术信息：$($_.Exception.Message)"
            )
        }

        foreach ($link in $resp.Links) {
            $href = [System.Net.WebUtility]::HtmlDecode([string]$link.href).Trim()
            if ([string]::IsNullOrWhiteSpace($href)) {
                continue
            }

            # 不同镜像站可能返回完整路径，也可能只返回文件名；统一按文件名匹配。
            $filename = ($href -split '/')[-1]
            $filename = [System.Uri]::UnescapeDataString($filename)
            if ($filename -match $pattern) {
                $candidates += [pscustomobject]@{
                    Href       = $href
                    Version    = $matches[1]
                    ReleaseTag = $matches[2]
                    Filename   = $filename
                    SourcePath = $null
                }
            }
        }
    }

    if (-not $candidates) {
        Exit-WithError (
            "下载站点暂时没有找到适用于 Windows 64 位的 Python $PythonMajorMinor.x 便携包。`n`n" +
            "这通常是镜像同步延迟或镜像暂时异常，不是你的项目文件损坏。请稍后重新启动；如果持续出现，请按“必看说明.txt”中的离线方法准备 Python 压缩包。"
        )
    }

    $best = $candidates |
        Sort-Object -Property @{
            Expression = {
                $parts = $_.Version.Split('.') | ForEach-Object { [int]$_ }
                ($parts[0] * 1000000) + ($parts[1] * 1000) + $parts[2]
            }
        }, @{
            Expression = { [int64]$_.ReleaseTag }
        } -Descending |
        Select-Object -First 1

    $script:ResolvedPythonVersion = $best.Version
    $script:ResolvedReleaseTag = $best.ReleaseTag
    $script:ArchiveName = "cpython-$ResolvedPythonVersion+$ResolvedReleaseTag-x86_64-pc-windows-msvc-install_only.tar.gz"
    $script:ArchiveLocal = Join-Path $RuntimeRoot $ArchiveName
    $archiveUri = $null
    if ($best.Href) {
        $archiveUri = [System.Uri]::new([System.Uri]$MirrorLatestUrl, $best.Href)
    }

    if ($best.SourcePath) {
        Write-Host "[scan] Found bundled standalone Python archive: $($best.Filename)" -ForegroundColor Green
    }

    return [pscustomobject]@{
        Version     = $ResolvedPythonVersion
        ReleaseTag  = $ResolvedReleaseTag
        ArchiveName = $ArchiveName
        SourcePath  = $best.SourcePath
        MirrorUrl   = if ($archiveUri) { $archiveUri.AbsoluteUri } else { $null }
    }
}

function Download-ResolvedArchive {
    param(
        [Parameter(Mandatory = $true)]
        [pscustomobject]$ResolvedInfo
    )

    if ($ResolvedInfo.SourcePath) {
        Write-Host "[1/4] Using bundled Python $($ResolvedInfo.Version) standalone..." -ForegroundColor Yellow
        Write-Host "      Source: $($ResolvedInfo.SourcePath)" -ForegroundColor DarkGray

        try {
            Copy-Item -LiteralPath $ResolvedInfo.SourcePath -Destination $ArchiveLocal -Force
            if ((Get-Item $ArchiveLocal).Length -lt 1MB) {
                throw "Bundled file too small, likely incomplete"
            }
            Write-Host "      Bundled archive ready." -ForegroundColor Green
            return
        }
        catch {
            if (Test-Path $ArchiveLocal) { Remove-Item $ArchiveLocal -Force }
            Exit-WithError ("Bundled Python archive failed. Check the local file.`n" +
                "  File: $($ResolvedInfo.SourcePath)")
        }
    }

    Write-Host "[1/4] Downloading Python $($ResolvedInfo.Version) standalone (~40MB)..." -ForegroundColor Yellow
    Write-Host "      Source: $($ResolvedInfo.MirrorUrl)" -ForegroundColor DarkGray

    try {
        $mirrorHost = ([uri]$ResolvedInfo.MirrorUrl).Host
        $session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
        # 中科大镜像需要线路选择 Cookie；其他镜像不发送该站点专用 Cookie。
        if ($mirrorHost -eq "mirrors.ustc.edu.cn") {
            $session.Cookies.Add((New-Object System.Net.Cookie("addr", "122.195.16.144", "/", $mirrorHost)))
        }

        Invoke-WebRequest -Uri $ResolvedInfo.MirrorUrl -WebSession $session -OutFile $ArchiveLocal -UseBasicParsing
        if ((Get-Item $ArchiveLocal).Length -lt 1MB) {
            throw "Downloaded file too small, likely an error page"
        }
        Write-Host "      Download complete." -ForegroundColor Green
    }
    catch {
        if (Test-Path $ArchiveLocal) { Remove-Item $ArchiveLocal -Force }
        Exit-WithError (
            "Python 运行时下载失败，压缩包没有完整保存。`n`n" +
            "常见原因是网络不稳定、代理/VPN 或安全软件中断了大文件下载。请关闭代理/VPN/下载加速器，换网络后重新启动。`n" +
            "如果多次失败，请按“必看说明.txt”中的离线方法手动准备此文件：`n" +
            "  文件名：$ArchiveName`n" +
            "  下载地址：$($ResolvedInfo.MirrorUrl)`n`n" +
            "技术信息：$($_.Exception.Message)"
        )
    }
}

# ===== PURE .NET TAR EXTRACTOR (no tar.exe dependency) =====
# Compiled once per process via Add-Type; works on any Windows with .NET 4.5+ (Win8+).
if (-not ([System.Management.Automation.PSTypeName]'SparkArc.TarExtractor').Type) {
    Add-Type -TypeDefinition @"
using System;
using System.IO;
using System.Text;

namespace SparkArc {
    public class TarExtractor {
        public static int Extract(string tarPath, string destDir) {
            int count = 0;
            using (var fs = File.OpenRead(tarPath)) {
                byte[] header = new byte[512];
                while (true) {
                    int read = ReadFull(fs, header, 512);
                    if (read < 512) break;

                    bool allZero = true;
                    for (int i = 0; i < 512; i++) { if (header[i] != 0) { allZero = false; break; } }
                    if (allZero) break;

                    StringBuilder sb = new StringBuilder(256);
                    for (int i = 0; i < 100 && header[i] != 0; i++) sb.Append((char)header[i]);
                    string name = sb.ToString();

                    sb.Clear();
                    for (int i = 124; i < 136 && header[i] != 0 && header[i] != 32; i++) sb.Append((char)header[i]);
                    long fileSize = 0;
                    string sizeStr = sb.ToString().Trim();
                    if (sizeStr.Length > 0) {
                        try { fileSize = Convert.ToInt64(sizeStr, 8); } catch { }
                    }

                    char typeFlag = (char)header[156];

                    if (header[257] == 0x75 && header[258] == 0x73 && header[259] == 0x74 &&
                        header[260] == 0x61 && header[261] == 0x72) {
                        sb.Clear();
                        for (int i = 345; i < 500 && header[i] != 0; i++) sb.Append((char)header[i]);
                        string prefix = sb.ToString().Trim();
                        if (prefix.Length > 0) name = prefix + "/" + name;
                    }

                    if (typeFlag == '5' || typeFlag == 'x' || typeFlag == 'g' || typeFlag == 'L') {
                        fs.Seek(((fileSize + 511) / 512) * 512, SeekOrigin.Current);
                        continue;
                    }

                    if (name.Length == 0 || name == "." || name == "./") {
                        fs.Seek(((fileSize + 511) / 512) * 512, SeekOrigin.Current);
                        continue;
                    }

                    name = name.Replace('\\', '/');
                    while (name.StartsWith("/")) name = name.Substring(1);
                    while (name.StartsWith("./")) name = name.Substring(2);
                    if (name.Length == 0) {
                        fs.Seek(((fileSize + 511) / 512) * 512, SeekOrigin.Current);
                        continue;
                    }

                    string destPath = Path.Combine(destDir, name.Replace('/', Path.DirectorySeparatorChar));
                    string parentDir = Path.GetDirectoryName(destPath);
                    if (!string.IsNullOrEmpty(parentDir) && !Directory.Exists(parentDir))
                        Directory.CreateDirectory(parentDir);

                    if (fileSize > 0) {
                        using (var outFs = File.Create(destPath)) {
                            long remaining = fileSize;
                            byte[] buf = new byte[65536];
                            while (remaining > 0) {
                                int toRead = (int)Math.Min(buf.Length, remaining);
                                int n = fs.Read(buf, 0, toRead);
                                if (n == 0) break;
                                outFs.Write(buf, 0, n);
                                remaining -= n;
                            }
                        }
                        count++;
                    }

                    long padding = ((fileSize + 511) / 512 * 512) - fileSize;
                    if (padding > 0) fs.Seek(padding, SeekOrigin.Current);
                }
            }
            return count;
        }

        private static int ReadFull(Stream s, byte[] buf, int count) {
            int offset = 0;
            while (offset < count) {
                int n = s.Read(buf, offset, count - offset);
                if (n == 0) break;
                offset += n;
            }
            return offset;
        }
    }
}
"@
}

# ---- Skip python deployment if already fully deployed ----
$CurrentVersion = Get-CurrentPythonVersion
$CurrentReqHash = Get-RequirementsHash
$StoredReqHash = $null

if (Test-Path $ReqHashFile) {
    try {
        $StoredReqHash = (Get-Content $ReqHashFile -ErrorAction Stop | Select-Object -First 1).Trim()
    }
    catch {
        $StoredReqHash = $null
    }
}

if (
    (Test-Path $MarkerFile) -and
    $CurrentVersion -and
    $CurrentVersion.StartsWith("$PythonMajorMinor.") -and
    (($null -eq $CurrentReqHash) -or ($CurrentReqHash -eq $StoredReqHash))
) {
    Write-Host "[pyloader] Already deployed with Python $CurrentVersion. Skipping python deployment." -ForegroundColor Green
    exit 0
}

if (Test-Path $MarkerFile) {
    if ($CurrentVersion -and $CurrentVersion.StartsWith("$PythonMajorMinor.") -and ($CurrentReqHash -ne $StoredReqHash)) {
        Write-Host "[pyloader] requirements.txt changed. Refreshing environment packages." -ForegroundColor Yellow
    }
    else {
        Write-Host "[pyloader] Deployment marker exists, but Python version is not $PythonMajorMinor.x. Rebuilding environment." -ForegroundColor Yellow
    }
}

# ---- Step 1-2: Ensure python-build-standalone archive and environment ----
$NeedsRebuild = (-not (Test-Path $PythonExe)) -or (-not $CurrentVersion) -or (-not $CurrentVersion.StartsWith("$PythonMajorMinor."))
$Resolved = $null

if ($NeedsRebuild) {
    # 只有本地 Python 不存在或版本不匹配时，才解析 standalone 镜像。
    $Resolved = Resolve-PythonArchive
}
else {
    # 已有可用运行环境时，不需要依赖 standalone 压缩包或其镜像。
    $script:ResolvedPythonVersion = $CurrentVersion
    $script:ResolvedReleaseTag = "existing"
    Write-Host "[pyloader] Local Python $CurrentVersion is usable. Skipping standalone archive resolution." -ForegroundColor Green
}

Write-Host "========================================"
Write-Host "  Portable Python Deployer (standalone)"
Write-Host "  Python $(if ($Resolved) { $Resolved.Version } else { $CurrentVersion }) | Zero registry impact"
Write-Host "========================================"

if ($NeedsRebuild) {
    if (Test-Path $PythonExe) {
        Write-Host "[1-2/4] Existing .runtime/python is not Python $PythonMajorMinor.x. Rebuilding..." -ForegroundColor Yellow
        if (Test-Path $EnvDir) { Remove-Item $EnvDir -Recurse -Force }
        if (Test-Path $MarkerFile) { Remove-Item $MarkerFile -Force }
    }

    if (-not (Test-Path $RuntimeRoot)) { New-Item -ItemType Directory -Path $RuntimeRoot | Out-Null }

    if (-not (Test-Path $ArchiveLocal)) {
        Download-ResolvedArchive -ResolvedInfo $Resolved
    }
    else {
        Write-Host "[1/4] Found local archive: $ArchiveName" -ForegroundColor Green
    }

    Write-Host "[2/4] Extracting Python to .runtime/python/ ..." -ForegroundColor Yellow

    $TempExtractDir = Join-Path $BasePath "_python_extract_temp"
    if (Test-Path $TempExtractDir) { Remove-Item $TempExtractDir -Recurse -Force }
    New-Item -ItemType Directory -Path $TempExtractDir | Out-Null

    try {
        $tarTempFile = Join-Path $BasePath "_temp_python.tar"

        Write-Host "      Decompressing gzip..."
        $inStream  = [System.IO.File]::OpenRead($ArchiveLocal)
        $gzip      = New-Object System.IO.Compression.GzipStream($inStream, [System.IO.Compression.CompressionMode]::Decompress)
        $outStream = [System.IO.File]::Create($tarTempFile)
        $gzip.CopyTo($outStream)
        $outStream.Close(); $gzip.Close(); $inStream.Close()

        Write-Host "      Extracting tar..."
        $fileCount = [SparkArc.TarExtractor]::Extract($tarTempFile, $TempExtractDir)
        Write-Host "      Extracted $fileCount files."

        if (Test-Path $tarTempFile) { Remove-Item $tarTempFile -Force }
    }
    catch {
        if (Test-Path $tarTempFile)    { Remove-Item $tarTempFile -Force }
        if (Test-Path $TempExtractDir) { Remove-Item $TempExtractDir -Recurse -Force }
        $detail = $_.Exception.Message
        if ($detail -match "访问被拒绝|拒绝访问|Access.*denied") {
            Exit-WithError (
                "无法读取 Python 压缩包，Windows 拒绝了文件访问。`n`n" +
                "常见原因是压缩包正被其他程序占用，或安全软件正在扫描/拦截它。`n`n" +
                "请按顺序尝试：`n" +
                "1. 关闭其他部署窗口、压缩软件和正在扫描此文件的安全软件窗口。`n" +
                "2. 右键压缩包打开“属性”；如果看到“解除锁定”，勾选后点击“确定”。`n" +
                "3. 如果文件来源可信，请在安全软件中允许本程序读取，或将整个项目文件夹移到普通可写目录后重试。`n" +
                "4. 仍失败时，删除下面列出的压缩包，再重新启动；不要删除整个项目文件夹。`n`n" +
                "文件：$ArchiveLocal`n" +
                "技术信息：$detail"
            )
        }

        Exit-WithError (
            "Python 压缩包无法解压，文件可能没有下载完整或已经损坏。`n`n" +
            "请删除下面列出的压缩包后重新启动；如果程序根目录还有同名的离线包，也请换一份完整文件。`n`n" +
            "文件：$ArchiveLocal`n" +
            "技术信息：$detail"
        )
    }

    $ExtractedPythonDir = Join-Path $TempExtractDir "python"
    if (-not (Test-Path (Join-Path $ExtractedPythonDir "python.exe"))) {
        if (Test-Path (Join-Path $TempExtractDir "python.exe")) {
            $ExtractedPythonDir = $TempExtractDir
        }
        else {
            if (Test-Path $TempExtractDir) { Remove-Item $TempExtractDir -Recurse -Force }
            Exit-WithError (
                "Python 压缩包已解压，但里面没有找到 python.exe。`n`n" +
                "这通常表示下载到的文件不完整、被镜像返回成网页，或文件格式不适用。请按“必看说明.txt”重新下载并替换压缩包后重试。`n`n" +
                "文件：$ArchiveLocal"
            )
        }
    }

    if (-not (Test-Path $RuntimeRoot)) { New-Item -ItemType Directory -Path $RuntimeRoot | Out-Null }
    if (Test-Path $EnvDir) { Remove-Item $EnvDir -Recurse -Force }
    Move-Item -Path $ExtractedPythonDir -Destination $EnvDir

    if (Test-Path $TempExtractDir) { Remove-Item $TempExtractDir -Recurse -Force }
    if (Test-Path $ArchiveLocal)   { Remove-Item $ArchiveLocal -Force }

    Write-Host "      Python extracted to .runtime/python/" -ForegroundColor Green
}
else {
    Write-Host "[1-2/4] Python $CurrentVersion already present in .runtime/python/" -ForegroundColor Green
}

# ***************---- Step 3: Run project-specific init script (if exists) ----****************
# This handles platform-dependent packages or project extras.
if (Test-Path $InitScript) {
    Write-Host "[3/4] Running init_env.py (project-specific setup)..." -ForegroundColor Yellow
    $p = Start-Process -FilePath $PythonExe -ArgumentList "-X utf8 `"$InitScript`"" -WorkingDirectory $BasePath -NoNewWindow -Wait -PassThru
    if ($p.ExitCode -ne 0) {
        Exit-WithError (
            "项目依赖初始化没有完成（退出码 $($p.ExitCode)）。`n`n" +
            "请先查看上方以 [ERROR] 开头的具体原因。常见原因包括网络超时、下载校验不一致、镜像暂时不可用或安全软件拦截。`n" +
            "如果上方没有具体说明，请阅读“必看说明.txt”后重试。"
        )
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
        Exit-WithError (
            "通用依赖安装没有完成（退出码 $($p.ExitCode)）。`n`n" +
            "请先查看上方 pip 的红色报错，并按其中的关键词处理：超时/连接中断请换网络；Expected/Got 或 hash 请关闭代理后重试；拒绝访问请检查安全软件和文件权限。`n" +
            "如果仍然无法判断，请阅读“必看说明.txt”，再提供从 [ERROR] 开始的完整窗口内容。"
        )
    }
}
else {
    Write-Host "[4/4] No requirements.txt found, skipping." -ForegroundColor DarkGray
}

# ---- Mark deployment as complete ----
$markerContent = "Deployed: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') | Python $ResolvedPythonVersion (standalone, zero-registry) | Release $ResolvedReleaseTag"
$markerContent | Set-Content -Path $MarkerFile -Encoding UTF8

if ($CurrentReqHash) {
    $CurrentReqHash | Set-Content -Path $ReqHashFile -Encoding UTF8
}
elseif (Test-Path $ReqHashFile) {
    Remove-Item $ReqHashFile -Force
}

Write-Host ""
Write-Host "========================================"
Write-Host "[pyloader] Deployment complete!" -ForegroundColor Green
Write-Host "========================================"
exit 0
