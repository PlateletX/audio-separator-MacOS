import os
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "models")
DOWNLOAD_CHECKS_NAME = "download_checks.json"
MODEL_REGISTRATIONS = [
    {
        "display_name": "Rofo Model: BS Rofo SW Fixed",
        "filename": "BS-Rofo-SW-Fixed.ckpt",
        "yaml_name": "BS-Rofo-SW-Fixed-roformer.yaml",
    },
    {
        "display_name": "Roformer Model: Karaoke MelBand Roformer | (by aufr33 & viperx)",
        "filename": "mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt",
        "yaml_name": "mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956_config.yaml",
    },
]


def ensure_local_model_files():
    """
    启动前确保本地模型文件存在。
    解决 pyloader 已完成后（.deploy_complete）不会再次执行 init_env.py，
    但用户手动删除模型文件导致运行时回退网络下载失败的问题。
    """
    try:
        from init_env import ensure_model_files
        ensure_model_files()
    except Exception as e:
        raise RuntimeError(f"模型文件检查/下载失败: {e}") from e


def ensure_local_model_yamls():
    """确保仓库内已提供本地模型 YAML 文件（不做下载/改名）。"""
    for model in MODEL_REGISTRATIONS:
        yaml_name = model["yaml_name"]
        yaml_path = os.path.join(MODELS_DIR, yaml_name)
        if not os.path.exists(yaml_path):
            raise RuntimeError(f"缺少本地 YAML 配置文件: {yaml_name}")


def ensure_local_download_checks():
    """确保仓库内已提供本地模型索引文件。"""
    download_checks_path = os.path.join(MODELS_DIR, DOWNLOAD_CHECKS_NAME)
    if not os.path.exists(download_checks_path) or os.path.getsize(download_checks_path) <= 0:
        raise RuntimeError(f"缺少本地模型索引文件: {DOWNLOAD_CHECKS_NAME}")


def prepend_env_path(path: str):
    """将指定路径前置到 PATH，避免依赖系统环境。"""
    normalized_target = os.path.normcase(os.path.abspath(path))
    current_path = os.environ.get("PATH", "")
    current_entries = [entry for entry in current_path.split(os.pathsep) if entry]
    normalized_entries = {os.path.normcase(os.path.abspath(entry)) for entry in current_entries}

    if normalized_target in normalized_entries:
        return

    os.environ["PATH"] = path if not current_path else path + os.pathsep + current_path


def resolve_runtime_ffmpeg_bin():
    """解析项目运行时可用的 ffmpeg 可执行文件目录。"""
    try:
        from init_env import ensure_ffmpeg
    except Exception as e:
        raise RuntimeError(f"缺少 FFmpeg 运行时初始化逻辑：{e}") from e

    ffmpeg_exe = ensure_ffmpeg()
    if not ffmpeg_exe or not os.path.exists(ffmpeg_exe):
        raise RuntimeError("未能初始化可用的 ffmpeg 运行时")

    return os.path.dirname(ffmpeg_exe)


def ensure_runtime_ffmpeg():
    """确保运行时可通过 imageio-ffmpeg 获取 FFmpeg。"""
    prepend_env_path(resolve_runtime_ffmpeg_bin())


def configure_runtime_environment():
    """配置离线运行环境。"""
    ensure_local_download_checks()
    ensure_runtime_ffmpeg()
    os.environ["AUDIO_SEPARATOR_MODEL_DIR"] = MODELS_DIR

def auto_register_model():
    """
    自动将自定义模型注册到 audio_separator 的 models.json 中。
    这样无需手动修改库文件，代码可以直接分发给他人使用。
    """
    try:
        import audio_separator
        pkg_dir = os.path.dirname(audio_separator.__file__)
        models_json_path = os.path.join(pkg_dir, "models.json")

        with open(models_json_path, "r", encoding="utf-8") as f:
            models_data = json.load(f)

        roformer_list = models_data.get("roformer_download_list", {})
        modified = False

        for model in MODEL_REGISTRATIONS:
            expected_model_name = model["display_name"]
            expected_model_info = {
                model["filename"]: model["yaml_name"]
            }
            current_info = roformer_list.get(expected_model_name)
            if current_info != expected_model_info:
                roformer_list[expected_model_name] = expected_model_info
                modified = True

        wrong_mapping_keys = {"BS-Roformer-SW-Fixed.ckpt"}
        wrong_mapping_vals = {"BS-Roformer-SW-Fixed.yaml", "BS-Rofo-SW-Fixed.yaml"}
        for name, info in list(roformer_list.items()):
            if isinstance(info, dict):
                if wrong_mapping_keys.intersection(info.keys()) or wrong_mapping_vals.intersection(info.values()):
                    roformer_list.pop(name, None)
                    modified = True

        if modified:
            models_data["roformer_download_list"] = roformer_list
            with open(models_json_path, "w", encoding="utf-8") as f:
                json.dump(models_data, f, indent=4, ensure_ascii=False)

    except Exception:
        pass  # 静默失败，不影响主程序启动

if __name__ == "__main__":
    # 1. 配置离线运行环境（本地模型索引 + imageio-ffmpeg 运行时）
    configure_runtime_environment()

    # 2. 启动前确保模型文件存在（ckpt 缺失时自动下载）
    ensure_local_model_files()

    # 3. 确保仓库内模型 YAML 存在（不下载、不改名）
    ensure_local_model_yamls()

    # 4. 自动注册自定义模型到 audio-separator（首次运行时写入，之后跳过）
    auto_register_model()

    # 5. 启动 GUI
    try:
        from tkinterdnd2 import TkinterDnD
        from gui import AudioSplitterGUI
        
        root = TkinterDnD.Tk()
        app = AudioSplitterGUI(root)
        root.mainloop()
    except ImportError:
        print("请先执行: pip install tkinterdnd2")
