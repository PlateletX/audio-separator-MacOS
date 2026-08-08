import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinterdnd2 import DND_FILES
import threading
import subprocess
import os
import shutil
import ctypes
import sys
import locale
import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "models")


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


def resolve_audio_separator_executable():
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    candidates = [
        os.path.join(exe_dir, "Scripts", "audio-separator.exe"),
        os.path.join(exe_dir, "Scripts", "audio-separator"),
        os.path.join(exe_dir, "audio-separator.exe"),
        os.path.join(exe_dir, "audio-separator"),
        shutil.which("audio-separator"),
    ]

    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate

    raise RuntimeError("未找到 audio-separator 启动程序，请通过一键启动GUI.bat 启动，或重新部署环境。")


def validate_runtime_model_file(model_name):
    try:
        from init_env import MODEL_FILES, validate_model_file
    except Exception:
        return

    file_info = MODEL_FILES.get(model_name)
    if not file_info:
        return

    model_path = os.path.join(MODELS_DIR, model_name)
    is_valid, invalid_reason = validate_model_file(
        model_path,
        file_info.get("min_size_bytes", 1),
        file_info.get("require_zip", False),
    )
    if not is_valid:
        raise RuntimeError(f"模型文件损坏或不完整：{model_name} ({invalid_reason})。请删除该文件后重新启动程序以自动下载。")

try:
    import torch
except ImportError:
    torch = None

BG_COLOR = "#121212"         
PANEL_BG = "#1E1E1E"         
TEXT_COLOR = "#CCCCCC"        
ACCENT_COLOR = "#00FFAA"     
ACCENT_HOVER = "#00CC88"      
BORDER_COLOR = "#333333"    
WARN_COLOR = "#FF5555"       
PRIMARY_MODEL_NAME = "BS-Rofo-SW-Fixed.ckpt"
HARMONY_MODEL_NAME = "mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt"
AUDIO_EXTENSIONS = {".wav", ".flac", ".mp3", ".m4a", ".ogg"}

FONT_BASE = ("Microsoft YaHei UI", 13)
FONT_BOLD = ("Microsoft YaHei UI", 13, "bold")
FONT_TITLE = ("Microsoft YaHei UI", 15, "bold")
FONT_CODE = ("Consolas", 13)

class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        self.id = None
        self.widget.bind("<Enter>", self.schedule)
        self.widget.bind("<Leave>", self.unschedule)

    def schedule(self, event=None):
        self.unschedule()
        self.id = self.widget.after(500, self.showtip)

    def unschedule(self, event=None):
        id = self.id
        self.id = None
        if id:
            self.widget.after_cancel(id)
        self.hidetip()

    def showtip(self, event=None):
        x, y, cx, cy = self.widget.bbox("insert") or (0, 0, 0, 0)
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 25
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        
        # 深色 Tooltip 样式
        label = tk.Label(tw, text=self.text, justify=tk.LEFT,
                      background="#252526", foreground="#D4D4D4", 
                      relief=tk.SOLID, borderwidth=1, highlightbackground=ACCENT_COLOR,
                      highlightthickness=1, highlightcolor=ACCENT_COLOR,
                      font=FONT_BASE, padx=10, pady=5)
        label.pack()

    def hidetip(self):
        tw = self.tipwindow
        self.tipwindow = None
        if tw:
            tw.destroy()

class AudioSplitterGUI:
    def __init__(self, root):
        self.root = root
        self.setup_dpi()
        
        self.root.title("音轨分离")
        self.root.geometry("960x1040")
        self.root.minsize(900, 1040)
        self.root.configure(bg=BG_COLOR)
        self.center_window(960, 1040)

        # 变量存储
        self.input_path = tk.StringVar()
        self.input_files = []
        self.input_summary = tk.StringVar(value="未选择音频文件")
        self.output_path = tk.StringVar()
        self.model_name = PRIMARY_MODEL_NAME
        self.harmony_model_name = HARMONY_MODEL_NAME
        
        self.out_format = tk.StringVar(value="WAV")
        self.segment_size = tk.StringVar(value="自动")
        self.overlap = tk.StringVar(value="8")
        self.autocast_enabled = tk.BooleanVar(value=True)
        
        self.hardware_info = tk.StringVar(value="正在扫描硬件...")
        self.accompaniment_mode = tk.BooleanVar(value=True)

        self.setup_style()
        self.setup_ui()
        
        # 异步检测硬件
        threading.Thread(target=self.check_hardware, daemon=True).start()

    def setup_dpi(self):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

    def setup_style(self):
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
            
        # 基础框架
        style.configure("TFrame", background=BG_COLOR)
        style.configure("Panel.TFrame", background=PANEL_BG)
        
        # 标签框
        style.configure("TLabelframe", background=PANEL_BG, borderwidth=1, bordercolor=BORDER_COLOR)
        style.configure("TLabelframe.Label", background=PANEL_BG, foreground=ACCENT_COLOR, font=FONT_TITLE)
        
        # 文本标签
        style.configure("TLabel", background=PANEL_BG, foreground=TEXT_COLOR, font=FONT_BASE)
        style.configure("Green.TLabel", background=BG_COLOR, foreground=ACCENT_COLOR, font=FONT_BASE)
        style.configure("Hardware.TLabel", background=BORDER_COLOR, foreground=ACCENT_COLOR, font=("Consolas", 13), padding=6)
        
        # 按钮
        style.configure("TButton", font=FONT_BASE, background="#333333", foreground=TEXT_COLOR, borderwidth=1, focuscolor=ACCENT_COLOR)
        style.map("TButton", background=[("active", "#444444")], foreground=[("active", "#FFFFFF")])
        
        # 主操作按钮
        style.configure("Primary.TButton", font=("Microsoft YaHei UI", 16, "bold"), background=ACCENT_COLOR, foreground="#000000", padding=12)
        style.map("Primary.TButton", background=[("active", ACCENT_HOVER), ("disabled", "#555555")], foreground=[("disabled", "#888888")])
        
        # 下拉框和输入框
        style.configure("TEntry", fieldbackground="#2D2D30", foreground="#FFFFFF", borderwidth=1, font=FONT_BASE)
        style.configure("TCombobox", fieldbackground="#FFFFFF", foreground="#000000", selectbackground=ACCENT_COLOR, selectforeground="#000000", font=FONT_BASE)

    def center_window(self, w, h):
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def setup_ui(self):

        main_frame = ttk.Frame(self.root, padding=(24, 8, 24, 12))
        main_frame.pack(fill=tk.BOTH, expand=True)

        # ================= 1. 文件区 =================
        file_frame = ttk.LabelFrame(main_frame, text="文件选择", padding=(20, 12, 20, 16))
        file_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(file_frame, text="待分离音频 (支持拖拽):").grid(row=0, column=0, sticky=tk.W, pady=4)
        entry_input = ttk.Entry(file_frame, textvariable=self.input_path, width=55, font=FONT_BASE)
        entry_input.grid(row=0, column=1, padx=15, pady=4, sticky=tk.EW)
        
        # 注册拖拽
        entry_input.drop_target_register(DND_FILES)
        entry_input.dnd_bind('<<Drop>>', self.handle_drop)
        
        self.btn_browse_input = ttk.Button(file_frame, text="选择文件", command=self.browse_input)
        self.btn_browse_input.grid(row=0, column=2, pady=4, ipadx=5)
        self.btn_browse_batch = ttk.Button(file_frame, text="批量选择", command=self.browse_batch_input)
        self.btn_browse_batch.grid(row=0, column=3, padx=(8, 0), pady=4, ipadx=5)

        ttk.Label(file_frame, text="输出目录:").grid(row=1, column=0, sticky=tk.W, pady=4)
        ttk.Entry(file_frame, textvariable=self.output_path, width=55, font=FONT_BASE).grid(row=1, column=1, padx=15, pady=4, sticky=tk.EW)
        self.btn_browse_output = ttk.Button(file_frame, text="选择目录", command=self.browse_output)
        self.btn_browse_output.grid(row=1, column=2, columnspan=2, pady=4, ipadx=5)

        ttk.Label(
            file_frame,
            textvariable=self.input_summary,
            foreground="#888888",
            font=("Microsoft YaHei UI", 11),
        ).grid(row=2, column=0, columnspan=4, sticky=tk.W, pady=(3, 0))
        
        file_frame.columnconfigure(1, weight=1)

        # ================= 2. 参数区 =================
        param_frame = ttk.LabelFrame(main_frame, text="性能参数", padding=(20, 12, 20, 16))
        param_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 预设挡位按钮
        preset_frame = ttk.Frame(param_frame, style="Panel.TFrame")
        preset_frame.grid(row=0, column=0, columnspan=4, sticky=tk.EW, pady=(0, 12))
        ttk.Label(preset_frame, text="快速加载算力配置:", foreground=TEXT_COLOR).pack(side=tk.LEFT, padx=(0, 15))
        
        btn_fast = ttk.Button(preset_frame, text="⚡ 快速", command=lambda: self.apply_preset("自动", "8", True))
        btn_fast.pack(side=tk.LEFT, padx=5, ipadx=8)
        ToolTip(btn_fast, "自动片段 | 窗口步长 8 秒 | CUDA 自动混合精度\n窗口重叠较少，通常更快；适合先快速试跑，不代表音质更好。")

        btn_bal = ttk.Button(preset_frame, text="⚖️ 推荐", command=lambda: self.apply_preset("自动", "4", True))
        btn_bal.pack(side=tk.LEFT, padx=5, ipadx=8)
        ToolTip(btn_bal, "自动模型窗口 | 窗口步长 4 秒 | CUDA 自动混合精度\n速度、接缝处理和资源占用的甜点档，推荐日常使用。")

        btn_high = ttk.Button(preset_frame, text="💎 质量优先", command=lambda: self.apply_preset("自动", "2", True))
        btn_high.pack(side=tk.LEFT, padx=5, ipadx=8)
        ToolTip(btn_high, "自动模型窗口 | 窗口步长 2 秒 | CUDA 自动混合精度\n窗口最多、通常最慢；可能减少接缝影响，但不保证音质一定提升，显存不足不要选。")

        # 详细参数
        ttk.Label(param_frame, text="模型分析窗口:").grid(row=1, column=0, sticky=tk.W, pady=6)
        seg_combo = ttk.Combobox(param_frame, textvariable=self.segment_size, values=["自动", "256", "512", "768", "1024"], width=12, state="readonly", font=FONT_BASE)
        seg_combo.grid(row=1, column=1, sticky=tk.W, padx=15, pady=6)
        ToolTip(seg_combo, "自动：使用模型自带的分析窗口（推荐）。手动调小：更省显存、更快，但模型一次看到的声音更短，可能影响复杂声音的判断；手动调大：更占显存、更慢，可能改善部分音频，但不保证音质提升。\n它不是音频时长；手动值只在覆盖模型默认值时生效。显存不足优先选自动或较小数值。")

        ttk.Label(param_frame, text="窗口步长（秒）:").grid(row=1, column=2, sticky=tk.W, pady=6, padx=(20, 0))
        ov_combo = ttk.Combobox(param_frame, textvariable=self.overlap, values=["2", "4", "8"], width=12, state="readonly", font=FONT_BASE)
        ov_combo.grid(row=1, column=3, sticky=tk.W, padx=15, pady=6)
        ToolTip(ov_combo, "窗口步长就是相邻窗口开始位置的间隔：8 秒窗口少，通常最快但接缝处理最少；4 秒窗口约多一倍，速度和接缝处理折中；2 秒窗口约多四倍，通常最慢，可能减少接缝影响。\n它不降低单个窗口的峰值显存；过大的步长还可能被模型窗口长度限制。")

        ttk.Label(param_frame, text="导出格式:").grid(row=2, column=0, sticky=tk.W, pady=6)
        fmt_combo = ttk.Combobox(param_frame, textvariable=self.out_format, values=["WAV", "FLAC", "MP3"], width=12, state="readonly", font=FONT_BASE)
        fmt_combo.grid(row=2, column=1, sticky=tk.W, padx=15, pady=6)

        chk_autocast = tk.Checkbutton(
            param_frame, text="CUDA 自动混合精度",
            variable=self.autocast_enabled, font=FONT_BASE,
            bg=PANEL_BG, fg=TEXT_COLOR, selectcolor="#2D2D30",
            activebackground=PANEL_BG, activeforeground=TEXT_COLOR,
            highlightthickness=0, relief=tk.FLAT, bd=0,
        )
        chk_autocast.grid(row=2, column=2, columnspan=2, sticky=tk.W, padx=(20, 0), pady=6)
        ToolTip(chk_autocast, "开启：CUDA 推理通常更快、更省显存，当前模型测试中输出差异很小，建议保持开启。关闭：通常更慢、更占显存，没有测出质量收益；只建议排查兼容性时尝试。CPU 不使用此选项。")

        chk_accomp = tk.Checkbutton(
            param_frame, text="伴奏模式  (保留六轨并额外合并非人声为伴奏)",
            variable=self.accompaniment_mode, font=FONT_BASE,
            bg=PANEL_BG, fg=TEXT_COLOR, selectcolor="#2D2D30",
            activebackground=PANEL_BG, activeforeground=TEXT_COLOR,
            highlightthickness=0, relief=tk.FLAT, bd=0,
        )
        chk_accomp.grid(row=3, column=0, columnspan=4, sticky=tk.W, pady=(6, 0))
        ToolTip(chk_accomp, "六轨文件会正常保留；勾选后会额外将 piano/guitar/bass/drum/other 合成为一条伴奏音轨，\n文件名以【伴奏】开头，输出在同一目录下。")
        
        param_frame.columnconfigure(1, weight=1)
        param_frame.columnconfigure(3, weight=1)

        # ================= 3. 操作区 =================
        op_frame = ttk.Frame(main_frame)
        op_frame.pack(fill=tk.BOTH, expand=True, pady=4)

        self.btn_start = ttk.Button(op_frame, text="开始分离", style="Primary.TButton", command=self.start_thread)
        self.btn_start.pack(pady=(8, 6), ipadx=36, ipady=10)

        btn_row = ttk.Frame(op_frame, style="Panel.TFrame")
        btn_row.pack(fill=tk.X, pady=(0, 8))
        self.btn_vocal = ttk.Button(btn_row, text="手动分离人声", command=self.start_manual_vocal_separation)
        self.btn_vocal.pack(side=tk.LEFT, padx=(0, 10), ipadx=5)
        ToolTip(self.btn_vocal, "选择一条人声音频，直接执行干声/和声分离（跳过六轨阶段）。\n适用于已有现成人声文件的场景。")
        ttk.Label(btn_row, text="← 可单独选择人声文件进行干声/和声分离", foreground="#666666", font=FONT_BASE).pack(side=tk.LEFT)

        # 终端日志框
        terminal_frame = tk.Frame(op_frame, bg="#000000", bd=1, relief=tk.SUNKEN)
        terminal_frame.pack(fill=tk.BOTH, expand=True)
        console_scroll = tk.Scrollbar(terminal_frame)
        console_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.console = tk.Text(
            terminal_frame, bg="#000000", fg=ACCENT_COLOR, font=FONT_CODE,
            height=12, state=tk.DISABLED, wrap=tk.WORD,
            yscrollcommand=console_scroll.set, bd=0, padx=10, pady=8,
            insertbackground=ACCENT_COLOR,
        )
        self.console.pack(fill=tk.BOTH, expand=True)
        console_scroll.config(command=self.console.yview)
        self.console.tag_config("accent", foreground=ACCENT_COLOR)
        self.console.tag_config("warn",   foreground=WARN_COLOR)
        self.console.tag_config("info",   foreground="#FFAA00")
        self.console.tag_config("dim",    foreground="#AAAAAA")
        self._console_append("> 系统就绪。等待音频数据输入...", "accent")

        # ================= 底部状态栏 =================
        bottom_frame = tk.Frame(self.root, bg=BORDER_COLOR)
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X)
        
        hw_label = ttk.Label(bottom_frame, textvariable=self.hardware_info, style="Hardware.TLabel")
        hw_label.pack(side=tk.LEFT, padx=12, pady=4)

    def apply_preset(self, segment, overlap, use_autocast):
        self.segment_size.set(segment)
        self.overlap.set(overlap)
        self.autocast_enabled.set(use_autocast)
        segment_label = "模型默认" if segment == "自动" else f"覆盖 {segment}"
        autocast_label = "CUDA 混合精度开" if use_autocast else "CUDA 混合精度关"
        self._console_append(
            f"> 已加载预设: {segment_label}, 窗口步长 {overlap} 秒, {autocast_label} [就绪]",
            "accent",
        )

    def check_hardware(self):
        info = "GPU: "
        if torch is None:
            info += "未检测到 PyTorch 核心"
        else:
            if torch.cuda.is_available():
                device_name = torch.cuda.get_device_name(0)
                vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
                info += f"NVIDIA {device_name} // {vram_gb:.1f} GB VRAM // CUDA 启用 ✅"
            else:
                info += "仅 CPU 运行 ❌ (未检测到Nvidia GPU或CUDA，将花费较长时间处理！)"
        
        self.root.after(0, lambda: self.hardware_info.set(info))

    def _set_input_files(self, paths):
        """更新待处理文件列表，并同步单文件显示和默认输出目录。"""
        normalized = []
        for raw_path in paths:
            if not raw_path:
                continue

            path = os.path.normpath(os.path.abspath(os.path.expanduser(str(raw_path))))
            if not os.path.isfile(path):
                continue
            if os.path.splitext(path)[1].lower() not in AUDIO_EXTENSIONS:
                continue
            if path not in normalized:
                normalized.append(path)

        self.input_files = normalized
        if not normalized:
            self.input_path.set("")
            self.input_summary.set("未选择音频文件")
            return

        self.input_path.set(normalized[0])
        self.input_summary.set(f"已选择 {len(normalized)} 个音频文件")
        if not self.output_path.get().strip():
            self.output_path.set(os.path.dirname(normalized[0]))

    def _get_selected_input_files(self):
        """读取当前待处理文件列表，并兼容用户手动输入单个路径。"""
        selected = list(self.input_files)
        typed_path = self.input_path.get().strip()

        if not selected and typed_path:
            selected = [typed_path]
        elif len(selected) == 1 and typed_path:
            typed_normalized = os.path.normcase(
                os.path.abspath(os.path.expanduser(typed_path))
            )
            selected_normalized = os.path.normcase(os.path.abspath(selected[0]))
            if typed_normalized != selected_normalized:
                selected = [typed_path]

        return [
            os.path.normpath(os.path.abspath(os.path.expanduser(path)))
            for path in selected
            if path
        ]

    def _set_busy(self, busy, busy_text="分离中... 请勿关闭窗口"):
        """统一切换处理期间的控件状态。"""
        state = tk.DISABLED if busy else tk.NORMAL
        for button in (
            self.btn_browse_input,
            self.btn_browse_batch,
            self.btn_browse_output,
        ):
            button.config(state=state)

        self.btn_start.config(
            state=state,
            text=busy_text if busy else "开始分离",
        )
        self.btn_vocal.config(state=state)

    def handle_drop(self, event):
        paths = self.root.tk.splitlist(event.data)
        self._set_input_files(paths)

    def browse_input(self):
        file = filedialog.askopenfilename(filetypes=[("Audio Files", "*.wav *.flac *.mp3 *.m4a *.ogg")])
        if file:
            self._set_input_files([file])

    def browse_batch_input(self):
        files = filedialog.askopenfilenames(
            title="选择要批量分离的音频文件",
            filetypes=[("Audio Files", "*.wav *.flac *.mp3 *.m4a *.ogg")],
        )
        if files:
            self._set_input_files(files)

    def browse_output(self):
        folder = filedialog.askdirectory()
        if folder:
            self.output_path.set(folder)

    def _console_append(self, text, tag="dim"):
        """向控制台追加一行（可在任意线程调用）."""
        def _do():
            self.console.config(state=tk.NORMAL)
            self.console.insert(tk.END, text + "\n", tag)
            self.console.see(tk.END)
            self.console.config(state=tk.DISABLED)
        self.root.after(0, _do)

    def set_status(self, text, color):
        tag = "info"
        if color == ACCENT_COLOR:
            tag = "accent"
        elif color == WARN_COLOR:
            tag = "warn"
        self._console_append(text, tag)

    def run_separator_command(self, input_file, output_dir, model_name):
        model_dir = MODELS_DIR
        validate_runtime_model_file(model_name)
        separator_exe = resolve_audio_separator_executable()
        cmd = [
            separator_exe,
            input_file,
            "--model_filename", model_name,
            "--model_file_dir", model_dir,
            "--output_dir", output_dir,
            "--output_format", self.out_format.get(),
            "--mdxc_overlap", self.overlap.get(),
        ]

        # 只有手动选择片段长度时才覆盖模型 YAML 默认值。
        if self.segment_size.get() != "自动":
            cmd.extend([
                "--mdxc_segment_size", self.segment_size.get(),
                "--mdxc_override_model_segment_size",
            ])

        # CPU 不传 autocast；CUDA 下由用户开关决定是否启用。
        if self.autocast_enabled.get() and torch is not None and torch.cuda.is_available():
            cmd.append("--use_autocast")

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        ffmpeg_bin = resolve_runtime_ffmpeg_bin()
        current_path = env.get("PATH", "")
        env["PATH"] = ffmpeg_bin if not current_path else ffmpeg_bin + os.pathsep + current_path
        env["AUDIO_SEPARATOR_MODEL_DIR"] = model_dir

        preferred_enc = locale.getpreferredencoding(False) or "utf-8"

        def _decode_line(raw_bytes):
            t = raw_bytes.decode(preferred_enc, errors="replace")
            if "\ufffd\ufffd\ufffd" in t:
                for enc in ("utf-8", "gbk"):
                    try:
                        c = raw_bytes.decode(enc, errors="replace")
                        if c.count("\ufffd\ufffd\ufffd") < t.count("\ufffd\ufffd\ufffd"):
                            t = c
                    except Exception:
                        pass
            return t.rstrip()

        popen_kwargs = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "env": env,
            "cwd": BASE_DIR,
        }
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            popen_kwargs["startupinfo"] = startupinfo
            popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        stderr_lines = []
        stdout_lines = []

        self._console_append(f"> 正在启动分离引擎: {os.path.basename(separator_exe)}", "dim")
        process = subprocess.Popen(cmd, **popen_kwargs)

        def _read_stream(stream, collector):
            for raw_line in iter(stream.readline, b""):
                line = _decode_line(raw_line)
                collector.append(line)
                if line.strip():
                    self._console_append(line, "dim")
            stream.close()

        t_out = threading.Thread(target=_read_stream, args=(process.stdout, stdout_lines), daemon=True)
        t_err = threading.Thread(target=_read_stream, args=(process.stderr, stderr_lines), daemon=True)
        t_out.start()
        t_err.start()
        t_out.join()
        t_err.join()
        process.wait()

        if process.returncode != 0:
            err_text = "\n".join(stderr_lines) or "\n".join(stdout_lines) or f"分离引擎执行失败，退出码: {process.returncode}"
            raise RuntimeError(err_text)

    def find_vocal_track(self, target_dir, source_base_name):
        candidates = []
        preferred_ext = f".{self.out_format.get().lower()}"

        for filename in os.listdir(target_dir):
            file_path = os.path.join(target_dir, filename)
            if not os.path.isfile(file_path):
                continue
            if os.path.splitext(filename)[1].lower() not in AUDIO_EXTENSIONS:
                continue
            if filename.startswith("【伴奏】"):
                continue
            candidates.append(file_path)

        if not candidates:
            raise RuntimeError("第一阶段分离已完成，但输出目录中未找到任何音频文件。")

        source_name = source_base_name.lower()

        def score(path):
            name = os.path.basename(path).lower()
            value = 0
            if source_name in name:
                value += 4
            if "vocals" in name:
                value += 5
            elif "vocal" in name:
                value += 4
            elif "voice" in name:
                value += 3
            if name.endswith(preferred_ext):
                value += 1
            if any(token in name for token in ("instrumental", "inst", "karaoke", "no_vocals")):
                value -= 6
            return value, os.path.getmtime(path)

        best_match = max(candidates, key=score)
        if score(best_match)[0] <= 0:
            available_files = "\n".join(os.path.basename(path) for path in candidates)
            raise RuntimeError(
                "第一阶段分离完成，但未能自动识别人声轨。\n"
                f"当前输出文件:\n{available_files}"
            )

        return best_match

    def confirm_secondary_separation(self, vocal_path, batch_count=1):
        result = {"confirmed": False}
        decision_event = threading.Event()

        def _ask_user():
            self._console_append("> 分离完成。已获取人声轨，等待确认是否继续分离干声和和声...", "info")
            if batch_count > 1:
                question = f"是否对本批次的 {batch_count} 个文件都继续进行干声/和声分离？"
            else:
                question = "是否继续分离人声为干声/和声？"
            result["confirmed"] = messagebox.askyesno(
                "人声分离确认",
                "已完成六轨分离。\n\n"
                f"人声轨已提取：\n{os.path.basename(vocal_path)}\n\n"
                f"{question}"
            )
            decision_event.set()

        self.root.after(0, _ask_user)
        decision_event.wait()
        return result["confirmed"]

    def start_thread(self):
        input_files = self._get_selected_input_files()
        output_dir = self.output_path.get().strip()

        if not input_files or not output_dir:
            messagebox.showwarning("提示", "请输入源文件和输出路径")
            return

        missing_files = [path for path in input_files if not os.path.isfile(path)]
        if missing_files:
            missing_names = "\n".join(os.path.basename(path) for path in missing_files[:5])
            if len(missing_files) > 5:
                missing_names += f"\n以及其他 {len(missing_files) - 5} 个文件"
            messagebox.showwarning("提示", f"以下音频文件不存在或已被移除：\n{missing_names}")
            return
        
        self._set_busy(True)
        self._console_append(f"> 已开始处理 {len(input_files)} 个音频文件，请耐心等待...", "info")
        
        threading.Thread(
            target=self.run_separation,
            args=(tuple(input_files), output_dir, self.accompaniment_mode.get()),
            daemon=True,
        ).start()

    def resolve_output_dir(self, output_root, base_name, reserved_dirs):
        """为批量任务生成不冲突的同名输出目录。"""
        target_dir = os.path.join(output_root, base_name)
        suffix = 2
        while os.path.normcase(os.path.abspath(target_dir)) in reserved_dirs:
            target_dir = os.path.join(output_root, f"{base_name} ({suffix})")
            suffix += 1

        reserved_dirs.add(os.path.normcase(os.path.abspath(target_dir)))
        return target_dir

    def run_separation(self, input_files=None, output_root=None, accompaniment_enabled=None):
        """按顺序处理一个或多个音频文件，并汇总批量任务结果。"""
        input_files = list(input_files or self._get_selected_input_files())
        output_root = (output_root or self.output_path.get()).strip()
        if accompaniment_enabled is None:
            accompaniment_enabled = self.accompaniment_mode.get()

        if not input_files or not output_root:
            self.root.after(0, lambda: self.finish_error("未找到可处理的音频文件或输出目录。"))
            return

        succeeded = []
        failed = []
        reserved_dirs = set()
        secondary_choice = None
        total = len(input_files)

        try:
            os.makedirs(output_root, exist_ok=True)
        except Exception as e:
            self.root.after(0, lambda msg=str(e): self.finish_error(msg))
            return

        for index, input_file in enumerate(input_files, start=1):
            source_base_name = os.path.splitext(os.path.basename(input_file))[0]
            target_dir = self.resolve_output_dir(output_root, source_base_name, reserved_dirs)
            harmony_dir = os.path.join(target_dir, "02_干声和声")

            try:
                os.makedirs(target_dir, exist_ok=True)
                self.set_status(
                    f"> 批量任务 {index}/{total}：正在分离 {os.path.basename(input_file)}...",
                    "#FFAA00",
                )
                self.run_separator_command(input_file, target_dir, self.model_name)

                if accompaniment_enabled:
                    self.merge_accompaniment(target_dir, source_base_name)

                vocal_path = self.find_vocal_track(target_dir, source_base_name)
                did_secondary_split = False

                if secondary_choice is None:
                    secondary_choice = self.confirm_secondary_separation(
                        vocal_path,
                        batch_count=total,
                    )

                if secondary_choice:
                    os.makedirs(harmony_dir, exist_ok=True)
                    self.set_status(
                        f"> 批量任务 {index}/{total}：正在分离干声与和声...",
                        "#FFAA00",
                    )
                    self.run_separator_command(vocal_path, harmony_dir, self.harmony_model_name)
                    did_secondary_split = True

                succeeded.append(
                    {
                        "input_file": input_file,
                        "target_dir": target_dir,
                        "secondary": did_secondary_split,
                    }
                )
                self._console_append(
                    f"> 批量任务 {index}/{total} 完成，输出目录：{target_dir}",
                    "accent",
                )
            except Exception as e:
                error_text = str(e)
                failed.append({"input_file": input_file, "error": error_text})
                self._console_append(
                    f"> 批量任务 {index}/{total} 失败：{os.path.basename(input_file)}\n{error_text}",
                    "warn",
                )

        if not succeeded:
            details = "\n\n".join(
                f"{os.path.basename(item['input_file'])}: {item['error']}"
                for item in failed
            )
            self.root.after(0, lambda msg=details: self.finish_error(msg or "批量任务失败。"))
            return

        if total == 1:
            did_secondary_split = succeeded[0]["secondary"]
            if did_secondary_split:
                status_text = "> 任务完成。六轨文件已保留，并已完成干声/和声二次分离。"
            elif accompaniment_enabled:
                status_text = "> 任务完成。六轨文件已保留，并已额外生成伴奏。"
            else:
                status_text = "> 任务完成。已输出六轨分离结果。"
        else:
            status_text = f"> 批量任务完成：成功 {len(succeeded)} 个，失败 {len(failed)} 个。"
            if failed:
                failed_names = ", ".join(os.path.basename(item["input_file"]) for item in failed)
                self._console_append(f"> 失败文件：{failed_names}", "warn")

        self.root.after(
            0,
            lambda target=output_root, text=status_text: self.finish_success(target, text),
        )

    def merge_accompaniment(self, target_dir, base_name):
        """将六轨中非人声音轨叠加合并为一条伴奏文件。"""
        from pydub import AudioSegment

        vocal_keywords = {"vocal", "vocals", "voice"}

        accompaniment_files = []
        for filename in os.listdir(target_dir):
            file_path = os.path.join(target_dir, filename)
            if not os.path.isfile(file_path):
                continue
            ext = os.path.splitext(filename)[1].lower()
            if ext not in AUDIO_EXTENSIONS:
                continue
            if filename.startswith("【伴奏】"):
                continue
            name_lower = filename.lower()
            if any(kw in name_lower for kw in vocal_keywords):
                continue
            accompaniment_files.append(file_path)

        if not accompaniment_files:
            self._console_append("> 未找到非人声音轨，跳过伴奏合并。", "warn")
            return

        self._console_append(f"> 正在合并 {len(accompaniment_files)} 条音轨为伴奏...", "info")
        mixed = None
        for fp in accompaniment_files:
            seg = AudioSegment.from_file(fp)
            if mixed is None:
                mixed = seg
            else:
                mixed = mixed.overlay(seg)

        fmt = self.out_format.get().lower()
        output_name = f"【伴奏】{base_name}.{fmt}"
        output_path = os.path.join(target_dir, output_name)
        mixed.export(output_path, format=fmt)
        self._console_append(f"> 伴奏已生成: {output_name}", "accent")

    def start_manual_vocal_separation(self):
        """手动选择人声文件，直接进行干声/和声分离。"""
        file = filedialog.askopenfilename(
            title="选择人声音频文件",
            filetypes=[("Audio Files", "*.wav *.flac *.mp3 *.m4a *.ogg")],
        )
        if not file:
            return

        if not self.output_path.get():
            self.output_path.set(os.path.dirname(file))

        self._set_busy(True, "分离中...")
        threading.Thread(target=self._run_manual_vocal_separation, args=(file,), daemon=True).start()

    def _run_manual_vocal_separation(self, vocal_file):
        try:
            base_name = os.path.splitext(os.path.basename(vocal_file))[0]
            output_dir = os.path.join(self.output_path.get(), base_name, "02_干声和声")
            os.makedirs(output_dir, exist_ok=True)

            self.set_status("> 手动模式：正在分离干声与和声，请耐心等待...", "#FFAA00")
            self.run_separator_command(vocal_file, output_dir, self.harmony_model_name)

            self.root.after(0, lambda: self._set_busy(False))
            self.root.after(0, lambda d=output_dir: self.finish_success(d, "> 人声分离完成。已输出干声/和声。"))
        except Exception as e:
            self.root.after(0, lambda: self._set_busy(False))
            self.root.after(0, lambda: self.finish_error(str(e)))

    def finish_success(self, target_dir, status_text):
        self._set_busy(False)
        self._console_append(status_text, "accent")
        
        # 跨平台打开目录
        try:
            if sys.platform == "win32":
                os.startfile(target_dir)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", target_dir])
            else:
                subprocess.Popen(["xdg-open", target_dir])
        except Exception as e:
            print(f"无法打开目录: {e}")

    def finish_error(self, msg):
        self._set_busy(False)
        self._console_append("> 任务中止。错误 🔴", "warn")
        
        if "CUDA out of memory" in msg:
            friendly_msg = "显卡在当前设置下显存不足。\n\n解决办法：\n1. 开启“CUDA 自动混合精度”（通常更省显存）\n2. 将“模型分析窗口”调回“自动”或选择更小的手动值（直接降低单窗口负载）\n3. 仍不足时使用“快速”预设\n\n注意：窗口步长主要减少窗口数量和总耗时，不能解决单个窗口的峰值显存。"
            messagebox.showerror("显存不足", friendly_msg)
        elif "模型文件损坏" in msg or "文件过小" in msg or "无法作为压缩包读取" in msg or "文件不存在" in msg:
            friendly_msg = f"模型文件异常，无法正常加载。\n\n{msg}\n\n解决方法：\n1. 关闭程序\n2. 删除提示中提到的模型文件（.ckpt）\n3. 重新启动程序，会自动重新下载"
            messagebox.showerror("模型文件损坏", friendly_msg)
        else:
            messagebox.showerror("运行错误", f"引擎日志:\n{msg}")
