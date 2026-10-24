"""Small macOS hardware helpers used by the GUI."""


def is_mps_available(torch_module):
    """Return whether PyTorch can use Apple's Metal Performance Shaders backend."""
    if torch_module is None:
        return False
    backends = getattr(torch_module, "backends", None)
    mps = getattr(backends, "mps", None)
    is_available = getattr(mps, "is_available", None)
    try:
        return bool(is_available()) if callable(is_available) else False
    except Exception:
        return False


def ffmpeg_binary_name(platform_name):
    """Return the executable name used by FFmpeg on macOS."""
    if platform_name != "darwin":
        raise ValueError("此 macOS 版本只支持 darwin FFmpeg")
    return "ffmpeg"
