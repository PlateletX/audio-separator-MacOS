"""
init_env.py - Project-specific dependency installer

Handles packages and tools that need platform detection or project-specific
logic that should NOT live in generic bootstrap.ps1:
  1. PyTorch (CUDA vs CPU auto-detection)
  2. audio-separator (metadata says numpy>=2, but works fine with numpy 1.x)
  3. numpy version pin (onnxruntime 1.17.x needs numpy 1.x ABI)
  4. FFmpeg provisioning for this project only
    5. Model files download (HuggingFace CN mirror)

Standard packages go in requirements.txt (handled by bootstrap.ps1).
Called automatically by bootstrap.ps1 during deployment.
"""
import os
import sys
import subprocess
import shutil
import zipfile
import urllib.request
import urllib.error
import ssl

# ============ Project-specific config ============
# PyTorch versions
TORCH_VERSION = "2.4.1"
TORCHAUDIO_VERSION = "2.4.1"
TORCHVISION_VERSION = "0.19.1"
CUDA_VERSION = "cu118"

# Audio separator version
AUDIO_SEPARATOR_VERSION = "0.41.1"

# NumPy constraint (onnxruntime 1.17.x was compiled against numpy 1.x ABI)
NUMPY_CONSTRAINT = "numpy>=1.21.6,<2.0"

# Download mirrors
MIRROR_URL = "https://mirrors.aliyun.com/pypi/simple/"
TORCH_CUDA_INDEX = f"https://download.pytorch.org/whl/{CUDA_VERSION}"
TORCH_ALIYUN_INDEX = f"https://mirrors.aliyun.com/pytorch-wheels/{CUDA_VERSION}/"
TORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"

# FFmpeg config (project-specific)
FFMPEG_ARCHIVE_NAME = "ffmpeg-master-latest-win64-gpl-shared.zip"
FFMPEG_GITHUB_URL = f"https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/{FFMPEG_ARCHIVE_NAME}"
FFMPEG_DOWNLOAD_URLS = [
    f"https://ghproxy.net/{FFMPEG_GITHUB_URL}",
    f"https://gh-proxy.com/{FFMPEG_GITHUB_URL}",
    FFMPEG_GITHUB_URL,
]

# Model files (project-specific)
# Keep local filenames consistent with original upstream names.
MODEL_FILES = {
    "BS-Rofo-SW-Fixed.ckpt": [
        "https://huggingface.co/jarredou/BS-ROFO-SW-Fixed/blob/main/BS-Rofo-SW-Fixed.ckpt",
    ],
}
# =================================================

ENV_DIR = "python_env"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FFMPEG_ROOT = os.path.join(BASE_DIR, "ffmpeg")
FFMPEG_BIN = os.path.join(FFMPEG_ROOT, "bin")
FFMPEG_EXE = os.path.join(FFMPEG_BIN, "ffmpeg.exe")
FFMPEG_PATH_FILE = os.path.join(BASE_DIR, "ffmpeg_path.txt")


def _to_hf_resolve_url(url: str) -> str:
    """Convert HuggingFace page URL to direct file resolve URL."""
    return url.replace("/blob/", "/resolve/")


def _to_hf_mirror_url(url: str) -> str:
    """Convert HuggingFace URL to hf-mirror (domestic mirror) URL."""
    resolve_url = _to_hf_resolve_url(url)
    return resolve_url.replace("https://huggingface.co", "https://hf-mirror.com")


def _download_file(url: str, target_path: str, timeout: int = 120):
    """Download file with SSL fallback for some Windows machines lacking CA chain."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp, open(target_path, "wb") as f:
            shutil.copyfileobj(resp, f)
        return
    except urllib.error.URLError as e:
        is_cert_error = isinstance(e.reason, ssl.SSLCertVerificationError)
        if not is_cert_error:
            raise
        print("    SSL certificate verify failed, retrying without certificate verification...")

    insecure_ctx = ssl._create_unverified_context()
    with urllib.request.urlopen(req, timeout=timeout, context=insecure_ctx) as resp, open(target_path, "wb") as f:
        shutil.copyfileobj(resp, f)


def ensure_model_files():
    """Ensure required model files exist in project root; download if missing."""
    for filename, source_urls in MODEL_FILES.items():
        local_path = os.path.join(BASE_DIR, filename)

        if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
            print(f"[+] Model exists, skip: {filename}")
            continue

        urls = []
        for source_url in source_urls:
            urls.append(_to_hf_mirror_url(source_url))
            urls.append(_to_hf_resolve_url(source_url))

        print(f"[*] Downloading model file: {filename}")

        downloaded = False
        for url in urls:
            print(f"    Source: {url}")
            try:
                _download_file(url, local_path)
                if os.path.getsize(local_path) == 0:
                    raise RuntimeError("Downloaded empty file")
                downloaded = True
                print(f"[+] Downloaded: {filename}")
                break
            except Exception as e:
                print(f"    Failed: {e}")
                if os.path.exists(local_path):
                    os.remove(local_path)

        if not downloaded:
            raise RuntimeError(
                f"Model download failed: {filename}. Please download manually from: {source_urls[0]}"
            )


def write_ffmpeg_path(path: str):
    # ASCII to avoid BOM when BAT uses set /p
    with open(FFMPEG_PATH_FILE, "w", encoding="ascii", errors="ignore") as f:
        f.write(path)


def check_system_ffmpeg():
    """Return ffmpeg bin dir if system ffmpeg exists, else None."""
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path and os.path.exists(ffmpeg_path):
        return os.path.dirname(ffmpeg_path)
    return None


def ensure_ffmpeg():
    """Project-specific FFmpeg provisioning."""
    # 1) Prefer system ffmpeg
    system_bin = check_system_ffmpeg()
    if system_bin:
        write_ffmpeg_path(system_bin)
        print(f"[+] Using system ffmpeg: {os.path.join(system_bin, 'ffmpeg.exe')}")
        return

    # 2) Use existing local ffmpeg
    if os.path.exists(FFMPEG_EXE):
        write_ffmpeg_path(FFMPEG_BIN)
        print(f"[+] Using local ffmpeg: {FFMPEG_EXE}")
        return

    # 3) Download local ffmpeg
    print("[*] System ffmpeg not found, downloading local portable ffmpeg...")
    archive_local = os.path.join(BASE_DIR, FFMPEG_ARCHIVE_NAME)
    extract_temp = os.path.join(BASE_DIR, "_ffmpeg_extract_temp")

    downloaded = False
    for url in FFMPEG_DOWNLOAD_URLS:
        print(f"    Source: {url}")
        try:
            _download_file(url, archive_local)
            if os.path.getsize(archive_local) < 10 * 1024 * 1024:
                raise RuntimeError("Downloaded archive too small, likely an error page")
            downloaded = True
            break
        except Exception as e:
            print(f"    Failed: {e}")
            if os.path.exists(archive_local):
                os.remove(archive_local)

    if not downloaded:
        raise RuntimeError(
            "FFmpeg download failed from all sources. "
            f"Please install ffmpeg manually or download: {FFMPEG_GITHUB_URL}"
        )

    try:
        if os.path.exists(extract_temp):
            shutil.rmtree(extract_temp, ignore_errors=True)
        os.makedirs(extract_temp, exist_ok=True)

        with zipfile.ZipFile(archive_local, "r") as zf:
            zf.extractall(extract_temp)

        found_exe = None
        for root, _, files in os.walk(extract_temp):
            if "ffmpeg.exe" in files:
                found_exe = os.path.join(root, "ffmpeg.exe")
                break

        if not found_exe:
            raise RuntimeError("ffmpeg.exe not found after extraction")

        found_bin = os.path.dirname(found_exe)
        found_root = os.path.dirname(found_bin)

        if os.path.exists(FFMPEG_ROOT):
            shutil.rmtree(FFMPEG_ROOT, ignore_errors=True)
        shutil.copytree(found_root, FFMPEG_ROOT)

        if not os.path.exists(FFMPEG_EXE):
            raise RuntimeError(f"Local ffmpeg install failed: {FFMPEG_EXE} not found")

        write_ffmpeg_path(FFMPEG_BIN)
        print(f"[+] Local ffmpeg installed: {FFMPEG_EXE}")
    finally:
        if os.path.exists(extract_temp):
            shutil.rmtree(extract_temp, ignore_errors=True)
        if os.path.exists(archive_local):
            os.remove(archive_local)


def check_nvidia_gpu():
    """Detect NVIDIA GPU presence"""
    try:
        cmd = 'powershell -Command "Get-CimInstance win32_VideoController | Select-Object -ExpandProperty Name"'
        output = subprocess.check_output(cmd, shell=True).decode('utf-8', errors='ignore')
        if "NVIDIA" in output.upper():
            print("[+] NVIDIA GPU detected. Installing CUDA-enabled PyTorch.")
            return True
        else:
            print("[-] No NVIDIA GPU. Installing CPU-only PyTorch.")
            return False
    except Exception as e:
        print(f"[-] GPU detection failed ({e}). Defaulting to CPU PyTorch.")
        return False


def run_pip(py_exe, args, description=""):
    """Run pip with isolation flags"""
    cmd = [py_exe, "-m", "pip", "install", "--isolated", "--no-user"] + args
    if description:
        print(f"[*] {description}")
    subprocess.run(cmd, check=True)


def install_all(py_exe, has_gpu):
    """Install all project-specific packages in the correct order"""

    # Step 1: Ensure model files for this project
    ensure_model_files()

    # Step 2: Ensure FFmpeg for this project
    ensure_ffmpeg()

    # Step 3: Install PyTorch with CUDA/CPU suffix
    suffix = f"+{CUDA_VERSION}" if has_gpu else "+cpu"
    torch_pkgs = [
        f"torch=={TORCH_VERSION}{suffix}",
        f"torchaudio=={TORCHAUDIO_VERSION}{suffix}",
        f"torchvision=={TORCHVISION_VERSION}{suffix}",
    ]

    torch_args = ["-i", MIRROR_URL] + torch_pkgs
    if has_gpu:
        torch_args += ["--extra-index-url", TORCH_CUDA_INDEX, "--extra-index-url", TORCH_ALIYUN_INDEX]
        run_pip(py_exe, torch_args, f"Installing PyTorch {TORCH_VERSION}+{CUDA_VERSION} (CUDA)...")
    else:
        torch_args += ["--extra-index-url", TORCH_CPU_INDEX]
        run_pip(py_exe, torch_args, f"Installing PyTorch {TORCH_VERSION}+cpu...")

    # Step 4: Install audio-separator (pulls in numpy 2.x via its dependency)
    run_pip(py_exe, ["-i", MIRROR_URL, f"audio-separator=={AUDIO_SEPARATOR_VERSION}"],
            f"Installing audio-separator {AUDIO_SEPARATOR_VERSION}...")

    # Step 5: Force-downgrade numpy to 1.x (onnxruntime 1.17.x ABI requirement)
    # audio-separator's metadata says numpy>=2 but it works fine with numpy 1.x (verified).
    # onnxruntime-gpu 1.17.1 CRASHES with numpy 2.x due to C extension ABI mismatch.
    run_pip(py_exe, ["-i", MIRROR_URL, NUMPY_CONSTRAINT],
            "Pinning numpy<2 (required for onnxruntime 1.17.x compatibility)...")

    print("[+] All project-specific dependencies installed.")


if __name__ == "__main__":
    print("=" * 50)
    print("  Project-specific dependency installer")
    print("  (FFmpeg + PyTorch CUDA/CPU + audio-separator + numpy pin)")
    print("=" * 50)

    # Isolate environment
    os.environ.pop("PYTHONPATH", None)
    os.environ.pop("PYTHONHOME", None)
    os.environ["PYTHONNOUSERSITE"] = "1"
    os.environ["PIP_USER"] = "0"

    # Work from script directory
    os.chdir(BASE_DIR)

    py_exe = os.path.abspath(os.path.join(ENV_DIR, "python.exe"))
    if not os.path.exists(py_exe):
        print(f"[-] Error: Python not found at {py_exe}. Run bootstrap.ps1 first.")
        sys.exit(1)

    has_gpu = check_nvidia_gpu()
    install_all(py_exe, has_gpu)
