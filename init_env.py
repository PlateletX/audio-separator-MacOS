"""Model download and FFmpeg helpers shared by the macOS application."""
import os
import sys
import shutil
import urllib.request
import urllib.error
import ssl
import zipfile
import hashlib
import time

from platform_support import ffmpeg_binary_name

# ============ Project-specific config ============
# FFmpeg runtime version
IMAGEIO_FFMPEG_VERSION = "0.6.0"

# Model files (project-specific)
# Keep local filenames consistent with original upstream names.
MODEL_FILES = {
    "BS-Rofo-SW-Fixed.ckpt": {
        "urls": [
            "https://huggingface.co/enerjazzer/BS-ROFO-SW-Fixed/resolve/main/BS-Rofo-SW-Fixed.ckpt?download=true",
            "https://huggingface.co/FractalSurfer/BS-RoFormer-SW-6stem/resolve/main/BS-Rofo-SW-Fixed.ckpt?download=true",
        ],
        "min_size_bytes": 600000000,
        "sha256": "24e7d35ee9c64415673d3fd33e06a67cac2c103c5df6267ba1576459c775916e",
    },
    "mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt": {
        "urls": [
            "https://huggingface.co/Sucial/MSST-WebUI/resolve/main/All_Models/vocal_models/model_mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt?download=true",
            "https://huggingface.co/Derur/UVR-models/resolve/279480b466747a114c2fb166d308bca3ae4e3d6d/mel_band_roformer_karaoke_aufr33_viperx_sdr_10/mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt?download=true",
        ],
        "min_size_bytes": 800000000,
        "sha256": "1de20d459332fe8869aeb01327a31df0032262706e1365114e852dc271779813",
    },
}
# =================================================

ENV_DIR = ".runtime/python"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "models")
FFMPEG_RUNTIME_DIR = os.path.join(BASE_DIR, ".runtime", "ffmpeg")
FFMPEG_RUNTIME_EXE = os.path.join(FFMPEG_RUNTIME_DIR, ffmpeg_binary_name(sys.platform))


def _to_hf_resolve_url(url: str) -> str:
    """Convert HuggingFace page URL to direct file resolve URL."""
    return url.replace("/blob/", "/resolve/")


def _to_hf_mirror_url(url: str) -> str:
    """Convert HuggingFace URL to hf-mirror (domestic mirror) URL."""
    resolve_url = _to_hf_resolve_url(url)
    return resolve_url.replace("https://huggingface.co", "https://hf-mirror.com")


def _download_file(url: str, target_path: str, timeout: int = 600):
    """Download with a terminal progress bar and resumable partial files."""
    partial_path = f"{target_path}.part"
    downloaded = os.path.getsize(partial_path) if os.path.exists(partial_path) else 0
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "audio-separation-macos",
            **({"Range": f"bytes={downloaded}-"} if downloaded else {}),
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if downloaded and resp.status != 206:
                downloaded = 0
                resp.close()
                if os.path.exists(partial_path):
                    os.remove(partial_path)
                return _download_file(url, target_path, timeout)

            total = resp.headers.get("Content-Length")
            total = int(total) + downloaded if total and resp.status == 206 else int(total or 0)
            mode = "ab" if downloaded else "wb"
            started = time.monotonic()
            last_update = 0.0
            with open(partial_path, mode) as f:
                while True:
                    block = resp.read(1024 * 1024)
                    if not block:
                        break
                    f.write(block)
                    downloaded += len(block)
                    now = time.monotonic()
                    if now - last_update >= 0.25:
                        elapsed = max(now - started, 0.001)
                        speed = downloaded / elapsed
                        if total:
                            percent = min(downloaded / total * 100, 100)
                            remaining = max(total - downloaded, 0) / max(speed, 1)
                            eta = f"剩余 {remaining:.0f} 秒"
                            print(
                                f"\r      [{_progress_bar(percent)}] {percent:5.1f}% | "
                                f"{_format_bytes(downloaded)} / {_format_bytes(total)} | "
                                f"{_format_bytes(speed)}/s | {eta}",
                                end="",
                                flush=True,
                            )
                        else:
                            print(
                                f"\r      已下载 {_format_bytes(downloaded)} | "
                                f"{_format_bytes(speed)}/s",
                                end="",
                                flush=True,
                            )
                        last_update = now
            print()
        os.replace(partial_path, target_path)
        return
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.reason}") from e
    except urllib.error.URLError as e:
        is_cert_error = isinstance(e.reason, ssl.SSLCertVerificationError)
        if not is_cert_error:
            raise
        print("    SSL 证书验证失败，正在跳过证书验证重试...")

    insecure_ctx = ssl._create_unverified_context()
    with urllib.request.urlopen(req, timeout=timeout, context=insecure_ctx) as resp, open(partial_path, "wb") as f:
        shutil.copyfileobj(resp, f)
    os.replace(partial_path, target_path)


def _format_bytes(value):
    units = ("B", "KB", "MB", "GB")
    value = float(value)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}"
        value /= 1024


def _progress_bar(percent, width=24):
    filled = int(width * percent / 100)
    return "#" * filled + "-" * (width - filled)


def ensure_model_files():
    """确保必需的模型文件存在于 models 目录；缺失则自动下载。"""
    os.makedirs(MODELS_DIR, exist_ok=True)
    for filename, file_info in MODEL_FILES.items():
        source_urls = file_info["urls"]
        min_size_bytes = file_info.get("min_size_bytes", 1)
        require_zip = file_info.get("require_zip", False)
        expected_sha256 = file_info.get("sha256")
        local_path = os.path.join(MODELS_DIR, filename)

        is_valid, invalid_reason = validate_model_file(
            local_path, min_size_bytes, require_zip, expected_sha256
        )
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
                is_valid, invalid_reason = validate_model_file(
                    local_path, min_size_bytes, require_zip, expected_sha256
                )
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
                f"模型下载失败: {filename}。请手动下载并放入 models 目录。下载地址: {source_urls[0]}"
            )


def validate_model_file(path, min_size_bytes=1, require_zip=False, expected_sha256=None):
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

    if expected_sha256:
        digest = hashlib.sha256()
        try:
            with open(path, "rb") as model_file:
                for block in iter(lambda: model_file.read(1024 * 1024), b""):
                    digest.update(block)
        except OSError as e:
            return False, f"无法校验模型文件: {e}"
        actual_sha256 = digest.hexdigest()
        if actual_sha256 != expected_sha256:
            return False, f"SHA-256 校验失败 ({actual_sha256})"

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