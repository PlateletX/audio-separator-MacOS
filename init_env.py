"""
init_env.py - Project-specific dependency installer

Handles packages and tools that need platform detection or project-specific
logic that should NOT live in generic pyloader.ps1:
  1. PyTorch (CUDA vs CPU auto-detection)
  2. audio-separator (metadata says numpy>=2, but works fine with numpy 1.x)
  3. numpy version pin (onnxruntime 1.17.x needs numpy 1.x ABI)
  4. FFmpeg runtime via imageio-ffmpeg from domestic PyPI mirror
  5. Model files download (HuggingFace CN mirror)

Standard packages go in requirements.txt (handled by pyloader.ps1).
Called automatically by pyloader.ps1 during deployment.
"""
import os
import sys
import subprocess
import shutil
import urllib.request
import urllib.error
import ssl
import zipfile

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
    "BS-Rofo-SW-Fixed.ckpt": {
        "urls": [
            "https://huggingface.co/jarredou/BS-ROFO-SW-Fixed/blob/main/BS-Rofo-SW-Fixed.ckpt",
        ],
        "min_size_bytes": 600000000,
        "require_zip": True,
    },
    "mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt": {
        "urls": [
            "https://github.com/TRvlvr/model_repo/releases/download/all_public_uvr_models/mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt",
        ],
        "min_size_bytes": 800000000,
        "require_zip": True,
    },
}
# =================================================

ENV_DIR = ".runtime/python"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "models")
FFMPEG_RUNTIME_DIR = os.path.join(BASE_DIR, ".runtime", "ffmpeg")
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
        print("    SSL 证书验证失败，正在跳过证书验证重试...")

    insecure_ctx = ssl._create_unverified_context()
    with urllib.request.urlopen(req, timeout=timeout, context=insecure_ctx) as resp, open(target_path, "wb") as f:
        shutil.copyfileobj(resp, f)


def ensure_model_files():
    """确保必需的模型文件存在于 models 目录；缺失则自动下载。"""
    os.makedirs(MODELS_DIR, exist_ok=True)
    for filename, file_info in MODEL_FILES.items():
        source_urls = file_info["urls"]
        min_size_bytes = file_info.get("min_size_bytes", 1)
        require_zip = file_info.get("require_zip", False)
        local_path = os.path.join(MODELS_DIR, filename)

        is_valid, invalid_reason = validate_model_file(local_path, min_size_bytes, require_zip)
        if is_valid:
            print(f"[+] 模型文件已存在，跳过: {filename}")
            continue

        if os.path.exists(local_path):
            print(f"[!] 检测到损坏的模型文件，正在重新下载: {filename} ({invalid_reason})")
            os.remove(local_path)

        urls = []
        seen_urls = set()
        for source_url in source_urls:
            for candidate_url in (_to_hf_mirror_url(source_url), _to_hf_resolve_url(source_url)):
                if candidate_url not in seen_urls:
                    seen_urls.add(candidate_url)
                    urls.append(candidate_url)

        print(f"[*] 正在下载模型文件: {filename}")

        downloaded = False
        for url in urls:
            print(f"    下载源: {url}")
            try:
                _download_file(url, local_path)
                is_valid, invalid_reason = validate_model_file(local_path, min_size_bytes, require_zip)
                if not is_valid:
                    raise RuntimeError(f"下载的模型文件无效: {invalid_reason}")
                downloaded = True
                print(f"[+] 下载完成: {filename}")
                break
            except Exception as e:
                print(f"    下载失败: {e}")
                if os.path.exists(local_path):
                    os.remove(local_path)

        if not downloaded:
            raise RuntimeError(
                f"模型下载失败: {filename}。请手动下载并放入程序目录，下载地址: {source_urls[0]}"
            )


def validate_model_file(path, min_size_bytes=1, require_zip=False):
    if not os.path.exists(path):
        return False, "文件不存在"

    try:
        size = os.path.getsize(path)
    except OSError as e:
        return False, f"无法读取文件大小: {e}"

    if size < min_size_bytes:
        return False, f"文件过小 ({size} 字节)，可能下载不完整"

    if require_zip:
        try:
            with zipfile.ZipFile(path, "r") as archive:
                if not archive.namelist():
                    return False, "压缩包内容为空"
        except Exception as e:
            return False, f"模型文件损坏，无法作为压缩包读取: {e}"

    return True, ""


def ensure_ffmpeg():
    """Validate FFmpeg runtime provided by imageio-ffmpeg."""
    try:
        import imageio_ffmpeg
    except Exception as e:
        raise RuntimeError(
            f"imageio-ffmpeg 不可用: {e}。"
            f"请安装 imageio-ffmpeg=={IMAGEIO_FFMPEG_VERSION}（可使用国内镜像源）。"
        ) from e

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    if not ffmpeg_exe or not os.path.exists(ffmpeg_exe):
        raise RuntimeError("imageio-ffmpeg 未能提供可用的 ffmpeg 程序")

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

    print(f"[+] 正在使用 imageio-ffmpeg 运行时: {FFMPEG_RUNTIME_EXE}")
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
            print("[+] 检测到 NVIDIA 显卡，将安装 CUDA 版 PyTorch。")
            return True
        else:
            print("[-] 未检测到 NVIDIA 显卡，将安装 CPU 版 PyTorch。")
            return False
    except Exception as e:
        print(f"[-] 显卡检测失败 ({e})，默认安装 CPU 版 PyTorch。")
        return False


def _format_pip_failure(description, error):
    """把 pip 的退出结果转换成面向普通用户的排查说明。"""
    task_name = description.rstrip(".。！!…") or "项目依赖安装"
    return (
        f"{task_name}未完成（pip 退出码 {error.returncode}）。\n\n"
        "请先看上方 pip 的红色文字，并按关键词处理：\n"
        "1. 出现 ReadTimeout、timed out 或“超时”：下载站点响应太慢，请关闭代理/VPN/下载加速器，换网络后重试。\n"
        "2. 出现 hashes、Expected 或 Got：镜像返回的文件内容与校验值不一致。不要手动修改校验值，请关闭代理后换网络重试。\n"
        "3. 出现 No matching distribution found 或“找不到匹配版本”：镜像暂时没有适合当前系统的安装包，请稍后重试或使用“必看说明.txt”中的离线方法。\n"
        "4. 出现 Access is denied、Permission denied 或“拒绝访问”：请关闭占用文件的程序，并检查安全软件是否拦截。\n\n"
        "如果只是下载速度很慢，请耐心等待；PyTorch CUDA 版安装包可能超过 2GB。请同时确认磁盘剩余空间充足。"
    )


def run_pip(py_exe, args, description=""):
    """使用隔离参数运行 pip，并收口为易读的错误提示。"""
    cmd = [py_exe, "-m", "pip", "install", "--isolated", "--no-user"] + args
    if description:
        print(f"[*] {description}")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(_format_pip_failure(description, e)) from e


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
        torch_args += ["--find-links", TORCH_ALIYUN_INDEX]
        run_pip(py_exe, torch_args, f"正在安装 PyTorch {TORCH_VERSION}+{CUDA_VERSION} (CUDA版)...")
    else:
        torch_args += ["--extra-index-url", TORCH_CPU_INDEX]
        run_pip(py_exe, torch_args, f"正在安装 PyTorch {TORCH_VERSION}+cpu (CPU版)...")

    # Step 3: Install audio-separator (pulls in numpy 2.x via its dependency)
    run_pip(py_exe, ["-i", MIRROR_URL, f"audio-separator=={AUDIO_SEPARATOR_VERSION}"],
            f"正在安装 audio-separator {AUDIO_SEPARATOR_VERSION}...")

    # Step 4: Install FFmpeg runtime from domestic PyPI mirror
    run_pip(py_exe, ["-i", MIRROR_URL, f"imageio-ffmpeg=={IMAGEIO_FFMPEG_VERSION}"],
            f"正在安装 imageio-ffmpeg {IMAGEIO_FFMPEG_VERSION}...")

    # Step 5: Force-downgrade numpy to 1.x (onnxruntime 1.17.x ABI requirement)
    # audio-separator's metadata says numpy>=2 but it works fine with numpy 1.x (verified).
    # onnxruntime-gpu 1.17.1 CRASHES with numpy 2.x due to C extension ABI mismatch.
    run_pip(py_exe, ["-i", MIRROR_URL, NUMPY_CONSTRAINT],
            "正在锁定 numpy<2（onnxruntime 1.17.x 兼容性要求）...")

    # Step 6: Validate FFmpeg runtime after package installation
    ensure_ffmpeg()

    print("[+] 所有项目依赖已安装完成。")


def main():
    """执行项目专用环境初始化。"""
    print("=" * 50)
    print("  项目专用依赖安装器")
    print("  (PyTorch CUDA/CPU + audio-separator + imageio-ffmpeg + numpy 版本锁定)")
    print("=" * 50)

    # 隔离运行环境
    os.environ.pop("PYTHONPATH", None)
    os.environ.pop("PYTHONHOME", None)
    os.environ["PYTHONNOUSERSITE"] = "1"
    os.environ["PIP_USER"] = "0"

    # 以脚本所在目录为工作目录
    os.chdir(BASE_DIR)

    py_exe = os.path.abspath(os.path.join(ENV_DIR, "python.exe"))
    if not os.path.exists(py_exe):
        raise RuntimeError(f"未找到 Python ({py_exe})。请先运行“一键启动GUI.bat”完成部署。")

    has_gpu = check_nvidia_gpu()
    install_all(py_exe, has_gpu)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[ERROR] 部署被用户取消。下次请重新运行“一键启动GUI.bat”。")
        sys.exit(1)
    except Exception as e:
        print("\n[ERROR] 环境初始化没有完成。")
        print(f"具体原因：{e}")
        print("\n请阅读程序目录中的“必看说明.txt”，按其中的网络、权限和离线下载建议处理。")
        print("如果仍然失败，请提供本窗口中从 [ERROR] 开始的完整内容。")
        sys.exit(1)
