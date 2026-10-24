"""macOS Qt GUI for local audio stem separation."""

from __future__ import annotations

import locale
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal, QSize, QLibraryInfo
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent, QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from platform_support import is_mps_available

BASE_DIR = Path(__file__).resolve().parent
MODELS_DIR = BASE_DIR / "models"
PRIMARY_MODEL_NAME = "BS-Rofo-SW-Fixed.ckpt"
HARMONY_MODEL_NAME = "mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt"
AUDIO_EXTENSIONS = {".wav", ".flac", ".mp3", ".m4a", ".ogg"}


class SeparatorWorker(QObject):
    log = Signal(str, str)
    finished = Signal(bool, str)

    def __init__(self, window, files, output_root, settings, harmony_only=False):
        super().__init__()
        self.window = window
        self.files = files
        self.output_root = output_root
        self.settings = settings
        self.harmony_only = harmony_only

    def run(self):
        try:
            self.window.run_separation(
                self.files,
                self.output_root,
                self.settings,
                self.log.emit,
                self.harmony_only,
            )
            self.finished.emit(True, "任务完成")
        except Exception as exc:
            self.finished.emit(False, str(exc))


class AudioSeparatorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("音轨分离")
        self.setMinimumSize(980, 720)
        self.resize(1180, 820)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAcceptDrops(True)
        self.input_files: list[str] = []
        self.output_root = ""
        self.worker_thread: QThread | None = None
        self.worker: SeparatorWorker | None = None
        self._build_ui()
        self._apply_theme()
        self._update_hardware()

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("音轨分离")
        title.setObjectName("Title")
        subtitle = QLabel("Apple Silicon · RoFormer · 本地处理")
        subtitle.setObjectName("Subtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch()
        self.hardware = QLabel("正在检测 MPS…")
        self.hardware.setObjectName("Hardware")
        header.addWidget(self.hardware)
        layout.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(18)
        body.addWidget(self._build_settings(), 0)
        body.addWidget(self._build_activity(), 1)
        layout.addLayout(body, 1)

    def _build_settings(self):
        panel = QFrame()
        panel.setObjectName("Panel")
        panel.setMinimumWidth(390)
        panel.setMaximumWidth(470)
        grid = QGridLayout(panel)
        grid.setContentsMargins(22, 22, 22, 22)
        grid.setVerticalSpacing(12)
        grid.setHorizontalSpacing(12)

        section = QLabel("输入与输出")
        section.setObjectName("Section")
        grid.addWidget(section, 0, 0, 1, 2)

        self.file_summary = QLabel("尚未选择音频")
        self.file_summary.setObjectName("Muted")
        grid.addWidget(self.file_summary, 1, 0, 1, 2)

        choose = QPushButton("选择音频")
        choose.clicked.connect(self.choose_files)
        grid.addWidget(choose, 2, 0)
        batch = QPushButton("批量选择")
        batch.clicked.connect(self.choose_files)
        grid.addWidget(batch, 2, 1)

        self.output_label = QLabel("输出目录：与源文件相同")
        self.output_label.setObjectName("Muted")
        grid.addWidget(self.output_label, 3, 0, 1, 2)
        output = QPushButton("选择输出目录")
        output.clicked.connect(self.choose_output)
        grid.addWidget(output, 4, 0, 1, 2)

        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setObjectName("Divider")
        grid.addWidget(divider, 5, 0, 1, 2)

        section2 = QLabel("处理参数")
        section2.setObjectName("Section")
        grid.addWidget(section2, 6, 0, 1, 2)

        grid.addWidget(QLabel("模型分析窗口"), 7, 0)
        self.segment = QComboBox()
        self.segment.addItems(["自动", "256", "512", "768", "1024"])
        grid.addWidget(self.segment, 7, 1)

        grid.addWidget(QLabel("窗口步长"), 8, 0)
        self.overlap = QComboBox()
        self.overlap.addItems(["2", "4", "8"])
        self.overlap.setCurrentText("4")
        grid.addWidget(self.overlap, 8, 1)

        grid.addWidget(QLabel("导出格式"), 9, 0)
        self.format = QComboBox()
        self.format.addItems(["WAV", "FLAC", "MP3"])
        grid.addWidget(self.format, 9, 1)

        self.accompaniment = QCheckBox("额外生成伴奏音轨")
        self.accompaniment.setChecked(True)
        grid.addWidget(self.accompaniment, 10, 0, 1, 2)
        self.harmony_split = QCheckBox("继续分离干声 / 和声")
        self.harmony_split.setChecked(False)
        grid.addWidget(self.harmony_split, 11, 0, 1, 2)

        grid.addItem(self._spacer(), 12, 0, 1, 2)
        self.start_button = QPushButton("开始分离")
        self.start_button.setObjectName("Primary")
        self.start_button.setMinimumHeight(52)
        self.start_button.clicked.connect(self.start_processing)
        grid.addWidget(self.start_button, 13, 0, 1, 2)

        self.vocal_button = QPushButton("只分离人声：干声 / 和声")
        self.vocal_button.clicked.connect(self.manual_vocal)
        grid.addWidget(self.vocal_button, 14, 0, 1, 2)
        return panel

    def _build_activity(self):
        panel = QFrame()
        panel.setObjectName("Panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)
        row = QHBoxLayout()
        heading = QLabel("活动日志")
        heading.setObjectName("Section")
        row.addWidget(heading)
        row.addStretch()
        clear = QPushButton("清空")
        clear.setObjectName("Quiet")
        clear.clicked.connect(lambda: self.log.clear())
        row.addWidget(clear)
        layout.addLayout(row)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setLineWrapMode(QPlainTextEdit.NoWrap)
        layout.addWidget(self.log, 1)
        hint = QLabel("支持将音频文件拖入窗口。模型下载会在首次启动时显示进度。")
        hint.setObjectName("Muted")
        layout.addWidget(hint)
        self.append_log("系统就绪。等待音频文件。", "info")
        return panel

    @staticmethod
    def _spacer():
        from PySide6.QtWidgets import QSpacerItem
        return QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding)

    def _apply_theme(self):
        self.setStyleSheet("""
            QWidget#Root { background: rgba(16, 22, 29, 235); color: #e8eef4; border-radius: 20px; }
            QFrame#Panel { background: rgba(28, 40, 51, 228); border: 1px solid rgba(164, 205, 220, 55); border-radius: 16px; }
            QLabel#Title { color: #f3f7fa; font-size: 30px; font-weight: 700; }
            QLabel#Subtitle, QLabel#Muted { color: #91a4b3; font-size: 13px; }
            QLabel#Section { color: #8bd4db; font-size: 14px; font-weight: 700; }
            QLabel#Hardware { background: #203c42; color: #9ee8e5; border: 1px solid #32646b; border-radius: 12px; padding: 9px 14px; }
            QLabel { color: #dbe5eb; }
            QFrame#Divider { color: #2a3a48; }
            QPushButton { background: #22313e; color: #e7f0f4; border: 1px solid #385063; border-radius: 9px; padding: 9px 12px; font-size: 13px; }
            QPushButton:hover { background: #2b4352; border-color: #61b8c0; }
            QPushButton:pressed { background: #182a35; }
            QPushButton#Primary { background: #57c8c2; color: #102127; border: 0; font-size: 16px; font-weight: 700; }
            QPushButton#Primary:hover { background: #7be1d8; }
            QPushButton#Quiet { background: transparent; border: 0; color: #91cfd1; padding: 4px 8px; }
            QComboBox, QSpinBox { background: #111b23; color: #e7f0f4; border: 1px solid #385063; border-radius: 8px; padding: 8px; }
            QComboBox QAbstractItemView { background: #18232d; color: #e7f0f4; selection-background-color: #2c646b; }
            QCheckBox { color: #dbe5eb; spacing: 8px; }
            QCheckBox::indicator { width: 17px; height: 17px; }
            QCheckBox::indicator:unchecked { border: 1px solid #557080; border-radius: 5px; background: #111b23; }
            QCheckBox::indicator:checked { border: 1px solid #57c8c2; border-radius: 5px; background: #57c8c2; }
            QPlainTextEdit { background: #0d141b; color: #a9e2df; border: 1px solid #2e4555; border-radius: 10px; padding: 12px; selection-background-color: #28525b; }
        """)

    def _update_hardware(self):
        try:
            import torch
            if is_mps_available(torch):
                self.hardware.setText("MPS 已启用")
            else:
                self.hardware.setText("CPU 模式")
        except ImportError:
            self.hardware.setText("PyTorch 未安装")

    def append_log(self, text, level="info"):
        prefix = {"ok": "✓", "warn": "!", "info": "·"}.get(level, "·")
        self.log.appendPlainText(f"{prefix} {text}")

    def choose_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "选择音频文件", str(Path.home()), "音频文件 (*.wav *.flac *.mp3 *.m4a *.ogg)")
        if files:
            self.input_files = files
            self.file_summary.setText(f"已选择 {len(files)} 个音频文件")
            self.append_log(f"已载入 {len(files)} 个音频文件。")

    def choose_output(self):
        folder = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if folder:
            self.output_root = folder
            self.output_label.setText(f"输出目录：{folder}")

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        files = [url.toLocalFile() for url in event.mimeData().urls()]
        files = [f for f in files if Path(f).suffix.lower() in AUDIO_EXTENSIONS]
        if files:
            self.input_files = files
            self.file_summary.setText(f"已选择 {len(files)} 个音频文件")
            self.append_log(f"拖入 {len(files)} 个音频文件。")

    def start_processing(self):
        if not self.input_files:
            QMessageBox.warning(self, "缺少输入", "请先选择或拖入音频文件。")
            return
        self._start_worker(self.input_files)

    def manual_vocal(self):
        files, _ = QFileDialog.getOpenFileNames(self, "选择人声音频", str(Path.home()), "音频文件 (*.wav *.flac *.mp3 *.m4a *.ogg)")
        if files:
            self._start_worker(files[:1], harmony_only=True)

    def _start_worker(self, files, harmony_only=False):
        output = getattr(self, "output_root", "") or str(Path(files[0]).parent)
        self.start_button.setEnabled(False)
        self.vocal_button.setEnabled(False)
        self.append_log("开始处理，请保持窗口打开。")
        self.worker_thread = QThread(self)
        settings = {
            "format": self.format.currentText(),
            "overlap": self.overlap.currentText(),
            "segment": self.segment.currentText(),
            "accompaniment": self.accompaniment.isChecked(),
            "harmony": self.harmony_split.isChecked(),
        }
        self.worker = SeparatorWorker(self, files, output, settings, harmony_only)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.moveToThread(self.worker_thread)
        self.worker.log.connect(self.append_log)
        self.worker.finished.connect(self._worker_finished)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.start()

    def _worker_finished(self, success, message):
        self.start_button.setEnabled(True)
        self.vocal_button.setEnabled(True)
        self.append_log(message, "ok" if success else "warn")
        if not success:
            QMessageBox.critical(self, "处理失败", message)

    def run_separation(self, files, output_root, settings, emit, harmony_only=False):
        separator = shutil.which("audio-separator")
        if not separator:
            candidate = Path(sys.executable).parent / "audio-separator"
            if candidate.exists():
                separator = str(candidate)
        if not separator:
            raise RuntimeError("未找到 audio-separator，请重新运行启动器安装依赖。")

        from init_env import ensure_ffmpeg, validate_model_file, MODEL_FILES
        ffmpeg = ensure_ffmpeg()
        env = os.environ.copy()
        env["PATH"] = str(Path(ffmpeg).parent) + os.pathsep + env.get("PATH", "")
        env["AUDIO_SEPARATOR_MODEL_DIR"] = str(MODELS_DIR)
        env["PYTHONUNBUFFERED"] = "1"

        for index, source in enumerate(files, 1):
            source_path = Path(source)
            target = Path(output_root) / source_path.stem
            if harmony_only:
                target = target / "02_干声和声"
            target.mkdir(parents=True, exist_ok=True)
            model_name = HARMONY_MODEL_NAME if harmony_only else PRIMARY_MODEL_NAME
            info = MODEL_FILES[model_name]
            valid, reason = validate_model_file(
                str(MODELS_DIR / model_name),
                info.get("min_size_bytes", 1),
                info.get("require_zip", False),
                info.get("sha256"),
            )
            if not valid:
                raise RuntimeError(f"模型文件不可用：{model_name} ({reason})")
            emit(f"处理 {index}/{len(files)}：{source_path.name}", "info")
            command = [
                separator,
                str(source_path),
                "--model_filename", model_name,
                "--model_file_dir", str(MODELS_DIR),
                "--output_dir", str(target),
                "--output_format", settings["format"],
                "--mdxc_overlap", settings["overlap"],
            ]
            if settings["segment"] != "自动":
                command += ["--mdxc_segment_size", settings["segment"], "--mdxc_override_model_segment_size"]
            process = subprocess.Popen(command, cwd=str(BASE_DIR), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            if process.stdout is None:
                raise RuntimeError("无法读取分离引擎日志")
            for raw in iter(process.stdout.readline, b""):
                line = raw.decode(locale.getpreferredencoding(False) or "utf-8", errors="replace").strip()
                if line:
                    emit(line, "info")
            code = process.wait()
            if code != 0:
                raise RuntimeError(f"分离引擎退出码：{code}")
            if settings["accompaniment"] and not harmony_only:
                self.merge_accompaniment(target, source_path.stem, settings["format"], emit)
            if settings["harmony"] and not harmony_only:
                vocal = self.find_vocal_track(target, source_path.stem)
                harmony_target = target / "02_干声和声"
                harmony_target.mkdir(parents=True, exist_ok=True)
                harmony_info = MODEL_FILES[HARMONY_MODEL_NAME]
                valid, reason = validate_model_file(
                    str(MODELS_DIR / HARMONY_MODEL_NAME),
                    harmony_info.get("min_size_bytes", 1),
                    harmony_info.get("require_zip", False),
                    harmony_info.get("sha256"),
                )
                if not valid:
                    raise RuntimeError(f"模型文件不可用：{HARMONY_MODEL_NAME} ({reason})")
                harmony_command = [
                    separator, str(vocal), "--model_filename", HARMONY_MODEL_NAME,
                    "--model_file_dir", str(MODELS_DIR), "--output_dir", str(harmony_target),
                    "--output_format", settings["format"], "--mdxc_overlap", settings["overlap"],
                ]
                emit("正在分离干声与和声…", "info")
                harmony_process = subprocess.Popen(
                    harmony_command, cwd=str(BASE_DIR), env=env,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                )
                if harmony_process.stdout is None:
                    raise RuntimeError("无法读取干声 / 和声分离日志")
                for raw in iter(harmony_process.stdout.readline, b""):
                    line = raw.decode(locale.getpreferredencoding(False) or "utf-8", errors="replace").strip()
                    if line:
                        emit(line, "info")
                if harmony_process.wait() != 0:
                    raise RuntimeError("干声 / 和声分离引擎执行失败")

    @staticmethod
    def find_vocal_track(target, source_base_name):
        candidates = [
            path for path in target.iterdir()
            if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS
            and not path.name.startswith("【伴奏】")
        ]
        if not candidates:
            raise RuntimeError("六轨分离完成，但输出目录中没有找到人声轨。")
        source_name = source_base_name.lower()
        def score(path):
            name = path.name.lower()
            value = 4 if source_name in name else 0
            value += 5 if "vocals" in name else 4 if "vocal" in name else 3 if "voice" in name else 0
            value -= 6 if any(token in name for token in ("instrumental", "inst", "karaoke", "no_vocals")) else 0
            return value, path.stat().st_mtime
        result = max(candidates, key=score)
        if score(result)[0] <= 0:
            raise RuntimeError("无法自动识别人声轨，请检查分离输出文件。")
        return result

    @staticmethod
    def merge_accompaniment(target, base_name, output_format, emit: Callable[[str, str], None]):
        """Mix non-vocal stems after the engine has produced the six tracks."""
        from pydub import AudioSegment

        vocal_tokens = ("vocal", "vocals", "voice")
        tracks = []
        for path in target.iterdir():
            if not path.is_file() or path.suffix.lower() not in AUDIO_EXTENSIONS:
                continue
            if path.name.startswith("【伴奏】") or any(token in path.name.lower() for token in vocal_tokens):
                continue
            tracks.append(path)
        if not tracks:
            emit("未找到非人声音轨，跳过伴奏合并。", "warn")
            return

        emit(f"正在合并 {len(tracks)} 条音轨为伴奏…", "info")
        mixed = None
        for path in tracks:
            segment = AudioSegment.from_file(path)
            mixed = segment if mixed is None else mixed.overlay(segment)
        output = target / f"【伴奏】{base_name}.{output_format.lower()}"
        mixed.export(output, format=output_format.lower())
        emit(f"伴奏已生成：{output.name}", "ok")


def main():
    plugin_root = QLibraryInfo.path(QLibraryInfo.PluginsPath)
    os.environ.setdefault("QT_PLUGIN_PATH", plugin_root)
    os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", str(Path(plugin_root) / "platforms"))
    # Set the library search path before QApplication loads the Cocoa platform.
    from PySide6.QtCore import QCoreApplication
    QCoreApplication.setLibraryPaths([plugin_root])
    app = QApplication(sys.argv)
    app.setApplicationName("音轨分离")
    app.setStyle("Fusion")
    window = AudioSeparatorWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
