# Audio Separation GUI — macOS (Apple Silicon)

基于 **BS-Rofo-SW-Fixed** 的六轨分离 GUI，可输出 piano、guitar、bass、drums、vocals、other；也支持人声/和声分离、批量任务和伴奏导出。

## 支持环境

- Apple Silicon Mac（M1 或更新），macOS Sonoma 14 或更新版本。
- Python 3.12（启动器会通过 Homebrew 准备 Python 和 Tk 支持）。
- PyTorch 2.4.1 的 MPS/Metal 后端。实际速度和内存使用会因芯片、音频及模型而变化。Intel Mac 不在当前安装配置的支持范围内。

## 安装与启动

1. 安装 [Homebrew](https://brew.sh/)（如尚未安装）。
2. 在 Finder 中打开项目文件夹，双击 `启动Mac版.command`。
3. 首次启动会创建 `.runtime/macos` 隔离环境并安装项目依赖。随后会检查模型文件；缺失的 `.ckpt` 权重会下载到 `models/`，需要稳定网络和足够的磁盘空间。

如 Finder 未能启动脚本，打开“终端”，执行：

```bash
cd "/path/to/audio-separation"
chmod u+x "启动Mac版.command"
./启动Mac版.command
```

GUI 底部显示硬件状态。Apple Silicon 可显示 Metal (MPS) 加速；CPU 也可运行，但会较慢。界面的 CUDA 混合精度选项仅供 NVIDIA CUDA 使用，不会在 MPS 或 CPU 下启用。

## 模型及依赖

Mac 依赖单独列在 `requirements.macos.txt`，安装器不会安装 CUDA 或 NVIDIA 专用的 `onnxruntime-gpu`。`.ckpt` 权重和 `.yaml` 架构配置由 PyTorch/audio-separator 读取，并非 Windows 可执行文件。RoFormer 的实际推理以运行时选择的设备为准。

模型权重基于 MUSDB18-HQ 等数据训练，可能受 `CC BY-NC-SA 4.0` 等条款限制，禁止商业用途。权重版权归原作者所有；处理受版权保护的音频时请自行遵守法律规定。本软件按“原样”提供，不保证稳定性。
