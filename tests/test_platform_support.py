import unittest
from types import SimpleNamespace

from platform_support import ffmpeg_binary_name, is_mps_available
from init_env import _format_bytes, _progress_bar


class PlatformSupportTests(unittest.TestCase):
    def test_mps_is_detected_when_available(self):
        torch = SimpleNamespace(backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: True)))
        self.assertTrue(is_mps_available(torch))

    def test_cpu_only_torch_does_not_claim_gpu_acceleration(self):
        torch = SimpleNamespace(backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: False)))
        self.assertFalse(is_mps_available(torch))

    def test_missing_torch_is_supported(self):
        self.assertFalse(is_mps_available(None))


    def test_ffmpeg_binary_name_is_macos_specific(self):
        self.assertEqual(ffmpeg_binary_name("darwin"), "ffmpeg")
        with self.assertRaises(ValueError):
            ffmpeg_binary_name("win32")

    def test_download_progress_helpers_format_values(self):
        self.assertEqual(_format_bytes(1024 * 1024), "1.0 MB")
        self.assertEqual(len(_progress_bar(50)), 24)
        self.assertEqual(_progress_bar(0), "-" * 24)


if __name__ == "__main__":
    unittest.main()
