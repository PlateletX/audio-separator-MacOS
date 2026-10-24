"""Create and validate the project-local Apple Silicon runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import venv
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = BASE_DIR / ".runtime" / "macos"
VENV_PYTHON = RUNTIME_DIR / "bin" / "python"
REQUIREMENTS_FILE = BASE_DIR / "requirements.macos.txt"
MARKER_FILE = RUNTIME_DIR / ".macos_setup.json"
TORCH_VERSION = "2.4.1"
TORCH_PACKAGES = (
    f"torch=={TORCH_VERSION}",
    "torchaudio==2.4.1",
    "torchvision==0.19.1",
)


def run(command: list[str], *, description: str) -> None:
    print(f"\n[*] {description}", flush=True)
    subprocess.run(command, check=True, cwd=BASE_DIR)


def requirements_fingerprint(base_python: str) -> str:
    digest = hashlib.sha256()
    digest.update(REQUIREMENTS_FILE.read_bytes())
    digest.update(f"\npython={base_python}\ntorch={' '.join(TORCH_PACKAGES)}".encode())
    return digest.hexdigest()


def runtime_is_ready(fingerprint: str) -> bool:
    if not VENV_PYTHON.is_file() or not MARKER_FILE.is_file():
        return False
    try:
        marker = json.loads(MARKER_FILE.read_text(encoding="utf-8"))
        if marker.get("fingerprint") != fingerprint:
            return False
        subprocess.run(
            [
                str(VENV_PYTHON),
                "-c",
                "import audio_separator, imageio_ffmpeg, onnxruntime, torch, torchaudio, torchvision, PySide6",
            ],
            check=True,
            cwd=BASE_DIR,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except (OSError, ValueError, subprocess.CalledProcessError):
        return False


def verify_runtime() -> None:
    probe = (
        "import platform, torch; "
        "print('PyTorch:', torch.__version__); "
        "print('Architecture:', platform.machine()); "
        "print('MPS built:', bool(getattr(torch.backends, 'mps', None) and torch.backends.mps.is_built())); "
        "print('MPS available:', bool(getattr(torch.backends, 'mps', None) and torch.backends.mps.is_available()))"
    )
    run([str(VENV_PYTHON), "-c", probe], description="检查 PyTorch 与 Apple Metal 支持")
    import_result = subprocess.run(
        [
            str(VENV_PYTHON),
            "-c",
            "import audio_separator; import onnxruntime; import imageio_ffmpeg; "
            "import torch; import torchaudio; import torchvision; import PySide6; "
            "print('依赖导入检查通过'); print('ONNX Runtime providers:', onnxruntime.get_available_providers())",
        ],
        cwd=BASE_DIR,
        text=True,
        capture_output=True,
    )
    if import_result.returncode:
        raise RuntimeError(import_result.stderr.strip() or "依赖导入检查失败")
    print(import_result.stdout.strip())


def setup(base_python: str) -> None:
    if platform.system() != "Darwin":
        raise RuntimeError("此安装器只支持 macOS。")
    if platform.machine() != "arm64":
        raise RuntimeError(
            "当前安装器面向 Apple Silicon (arm64) Mac。此项目锁定的 PyTorch 版本没有适用的 Intel Mac wheel；"
            "请使用 Apple Silicon Mac，或另行构建 Intel 兼容的 PyTorch 环境。"
        )

    base_python = str(Path(base_python).resolve())
    version = subprocess.check_output(
        [base_python, "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
        text=True,
    ).strip()
    if version != "3.12":
        raise RuntimeError(f"需要 Python 3.12，当前解释器版本为 {version}：{base_python}")
    fingerprint = requirements_fingerprint(base_python)

    if runtime_is_ready(fingerprint):
        print("[+] macOS 运行环境已就绪，跳过依赖安装。")
        verify_runtime()
        return

    if RUNTIME_DIR.exists() and not VENV_PYTHON.exists():
        shutil.rmtree(RUNTIME_DIR)
    if not VENV_PYTHON.exists():
        RUNTIME_DIR.parent.mkdir(parents=True, exist_ok=True)
        print(f"[*] 创建项目隔离环境：{RUNTIME_DIR}")
        venv.EnvBuilder(with_pip=True, clear=False).create(RUNTIME_DIR)

    run([str(VENV_PYTHON), "-m", "pip", "install", "--upgrade", "pip"], description="更新项目环境中的 pip")
    run(
        [str(VENV_PYTHON), "-m", "pip", "install", *TORCH_PACKAGES],
        description=f"安装 Apple Silicon 版 PyTorch {TORCH_VERSION}、TorchAudio 与 TorchVision（MPS）",
    )
    run(
        [str(VENV_PYTHON), "-m", "pip", "install", "-r", str(REQUIREMENTS_FILE)],
        description="安装 audio-separator、CoreML 运行时、FFmpeg 与 PySide6 原生 GUI",
    )
    verify_runtime()
    MARKER_FILE.write_text(
        json.dumps({"fingerprint": fingerprint, "python": base_python}, indent=2) + "\n",
        encoding="utf-8",
    )
    print("\n[+] macOS 环境准备完成。首次启动还会检查并下载缺失的模型权重。")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default=sys.executable, help="Python 3.12 interpreter")
    args = parser.parse_args()
    try:
        setup(args.python)
    except (OSError, subprocess.CalledProcessError, RuntimeError) as exc:
        print(f"\n[ERROR] macOS 环境准备失败：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
