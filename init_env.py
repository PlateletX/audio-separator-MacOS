"""
init_env.py - Project-specific dependency installer

Handles packages and tools that need platform detection or project-specific
logic that should NOT live in generic bootstrap.ps1:
  1. PyTorch (CUDA vs CPU auto-detection)
  2. audio-separator (metadata says numpy>=2, but works fine with numpy 1.x)
  3. numpy version pin (onnxruntime 1.17.x needs numpy 1.x ABI)
  4. FFmpeg runtime via imageio-ffmpeg from domestic PyPI mirror
  5. Model files download (HuggingFace CN mirror)

Standard packages go in requirements.txt (handled by bootstrap.ps1).
Called automatically by bootstrap.ps1 during deployment.
"""
import os
import sys
import subprocess
import shutil
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

# FFmpeg runtime version (domestic PyPI mirror)
IMAGEIO_FFMPEG_VERSION = "0.6.0"

# NumPy constraint (onnxruntime 1.17.x was compiled against numpy 1.x ABI)
NUMPY_CONSTRAINT = "numpy>=1.21.6,<2.0"

# Download mirrors
MIRROR_URL = "https://mirrors.aliyun.com/pypi/simple/"
TORCH_CUDA_INDEX = f"https://download.pytorch.org/whl/{CUDA_VERSION}"
TORCH_ALIYUN_INDEX = f"https://mirrors.aliyun.com/pytorch-wheels/{CUDA_VERSION}/"
TORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"

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
FFMPEG_RUNTIME_DIR = os.path.join(BASE_DIR, "ffmpeg_runtime")
FFMPEG_RUNTIME_EXE = os.path.join(FFMPEG_RUNTIME_DIR, "ffmpeg.exe")


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


def ensure_ffmpeg():
    """Validate FFmpeg runtime provided by imageio-ffmpeg."""
    try:
        import imageio_ffmpeg
    except Exception as e:
        raise RuntimeError(
            f"imageio-ffmpeg unavailable: {e}. "
            f"Please install imageio-ffmpeg=={IMAGEIO_FFMPEG_VERSION} from domestic PyPI mirror."
        ) from e

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    if not ffmpeg_exe or not os.path.exists(ffmpeg_exe):
        raise RuntimeError("imageio-ffmpeg did not provide a usable ffmpeg executable")

    os.makedirs(FFMPEG_RUNTIME_DIR, exist_ok=True)

    should_copy = True
    if os.path.exists(FFMPEG_RUNTIME_EXE):
        try:
            should_copy = (
                os.path.getsize(FFMPEG_RUNTIME_EXE) != os.path.getsize(ffmpeg_exe)
                or os.path.getmtime(FFMPEG_RUNTIME_EXE) < os.path.getmtime(ffmpeg_exe)
            )
        except OSError:
            should_copy = True

    if should_copy:
        shutil.copy2(ffmpeg_exe, FFMPEG_RUNTIME_EXE)

    print(f"[+] Using imageio-ffmpeg runtime: {FFMPEG_RUNTIME_EXE}")
    return FFMPEG_RUNTIME_EXE


def check_nvidia_gpu():
    """Detect NVIDIA GPU presence"""
    try:
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        ps_exe = os.path.join(system_root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
        if not os.path.exists(ps_exe):
            ps_exe = shutil.which("pwsh") or shutil.which("powershell") or "powershell"

        cmd = f'"{ps_exe}" -Command "Get-CimInstance win32_VideoController | Select-Object -ExpandProperty Name"'
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

    # Step 2: Install PyTorch with CUDA/CPU suffix
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

    # Step 3: Install audio-separator (pulls in numpy 2.x via its dependency)
    run_pip(py_exe, ["-i", MIRROR_URL, f"audio-separator=={AUDIO_SEPARATOR_VERSION}"],
            f"Installing audio-separator {AUDIO_SEPARATOR_VERSION}...")

    # Step 4: Install FFmpeg runtime from domestic PyPI mirror
    run_pip(py_exe, ["-i", MIRROR_URL, f"imageio-ffmpeg=={IMAGEIO_FFMPEG_VERSION}"],
            f"Installing imageio-ffmpeg {IMAGEIO_FFMPEG_VERSION}...")

    # Step 5: Force-downgrade numpy to 1.x (onnxruntime 1.17.x ABI requirement)
    # audio-separator's metadata says numpy>=2 but it works fine with numpy 1.x (verified).
    # onnxruntime-gpu 1.17.1 CRASHES with numpy 2.x due to C extension ABI mismatch.
    run_pip(py_exe, ["-i", MIRROR_URL, NUMPY_CONSTRAINT],
            "Pinning numpy<2 (required for onnxruntime 1.17.x compatibility)...")

    # Step 6: Validate FFmpeg runtime after package installation
    ensure_ffmpeg()

    print("[+] All project-specific dependencies installed.")


if __name__ == "__main__":
    print("=" * 50)
    print("  Project-specific dependency installer")
    print("  (PyTorch CUDA/CPU + audio-separator + imageio-ffmpeg + numpy pin)")
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
