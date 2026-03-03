import os
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_YAML_NAME = "BS-Rofo-SW-Fixed-roformer.yaml"


def ensure_local_model_files():
    """
    启动前确保本地模型文件存在。
    解决 bootstrap 已完成后（.deploy_complete）不会再次执行 init_env.py，
    但用户手动删除模型文件导致运行时回退网络下载失败的问题。
    """
    try:
        from init_env import ensure_model_files
        ensure_model_files()
    except Exception as e:
        raise RuntimeError(f"模型文件检查/下载失败: {e}") from e


def ensure_local_model_yaml():
    """确保仓库内已提供模型 YAML 文件（不做下载/改名）。"""
    yaml_path = os.path.join(BASE_DIR, MODEL_YAML_NAME)
    if not os.path.exists(yaml_path):
        raise RuntimeError(f"缺少本地 YAML 配置文件: {MODEL_YAML_NAME}")

def auto_register_model():
    """
    自动将自定义模型注册到 audio_separator 的 models.json 中。
    这样无需手动修改库文件，代码可以直接分发给他人使用。
    """
    try:
        import audio_separator
        pkg_dir = os.path.dirname(audio_separator.__file__)
        models_json_path = os.path.join(pkg_dir, "models.json")

        # 需要注册的自定义模型列表（可按需扩展）
        # 注意：文件名必须与项目下载文件保持一致。
        expected_model_name = "Rofo Model: BS Rofo SW Fixed"
        expected_model_info = {
            "BS-Rofo-SW-Fixed.ckpt": MODEL_YAML_NAME
        }

        with open(models_json_path, "r", encoding="utf-8") as f:
            models_data = json.load(f)

        roformer_list = models_data.get("roformer_download_list", {})
        modified = False

        current_info = roformer_list.get(expected_model_name)
        if current_info != expected_model_info:
            roformer_list[expected_model_name] = expected_model_info
            modified = True

        # 清理错误命名：不做兼容，直接移除 Roformer 错名条目
        wrong_names = [name for name in list(roformer_list.keys()) if "Roformer" in name]
        for name in wrong_names:
            roformer_list.pop(name, None)
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
    # 1. 启动前确保模型文件存在（ckpt 缺失时自动下载）
    ensure_local_model_files()

    # 2. 确保仓库内模型 YAML 存在（不下载、不改名）
    ensure_local_model_yaml()

    # 3. 自动注册自定义模型到 audio-separator（首次运行时写入，之后跳过）
    auto_register_model()

    # 4. 启动 GUI
    try:
        from tkinterdnd2 import TkinterDnD
        from gui import AudioSplitterGUI
        
        root = TkinterDnD.Tk()
        app = AudioSplitterGUI(root)
        root.mainloop()
    except ImportError:
        print("请先执行: pip install tkinterdnd2")
