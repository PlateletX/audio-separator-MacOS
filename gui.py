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

    model_path = os.path.join(BASE_DIR, model_name)
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

FONT_BASE = ("Microsoft YaHei UI", 11)
FONT_BOLD = ("Microsoft YaHei UI", 11, "bold")
FONT_TITLE = ("Microsoft YaHei UI", 13, "bold")
FONT_CODE = ("Consolas", 11)

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
        self.root.geometry("850x900")
        self.root.minsize(800, 900)
        self.root.configure(bg=BG_COLOR)
        self.center_window(850, 900)

        # 变量存储
        self.input_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.model_name = PRIMARY_MODEL_NAME
        self.harmony_model_name = HARMONY_MODEL_NAME
        
        self.out_format = tk.StringVar(value="WAV")
        self.segment_size = tk.StringVar(value="512")
        self.batch_size = tk.StringVar(value="8")
        self.overlap = tk.StringVar(value="8")
        
        self.hardware_info = tk.StringVar(value="正在扫描硬件...")

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
        style.configure("Hardware.TLabel", background=BORDER_COLOR, foreground=ACCENT_COLOR, font=FONT_CODE, padding=4)
        
        # 按钮
        style.configure("TButton", font=FONT_BASE, background="#333333", foreground=TEXT_COLOR, borderwidth=1, focuscolor=ACCENT_COLOR)
        style.map("TButton", background=[("active", "#444444")], foreground=[("active", "#FFFFFF")])
        
        # 主操作按钮
        style.configure("Primary.TButton", font=("Microsoft YaHei UI", 14, "bold"), background=ACCENT_COLOR, foreground="#000000", padding=10)
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

        main_frame = ttk.Frame(self.root, padding=(20, 0, 20, 20))
        main_frame.pack(fill=tk.BOTH, expand=True)

        # ================= 1. 文件区 =================
        file_frame = ttk.LabelFrame(main_frame, text="文件选择", padding=20)
        file_frame.pack(fill=tk.X, pady=(0, 20))

        ttk.Label(file_frame, text="待分离音频 (支持拖拽):").grid(row=0, column=0, sticky=tk.W, pady=8)
        entry_input = ttk.Entry(file_frame, textvariable=self.input_path, width=50, font=FONT_BASE)
        entry_input.grid(row=0, column=1, padx=15, pady=8, sticky=tk.EW)
        
        # 注册拖拽
        entry_input.drop_target_register(DND_FILES)
        entry_input.dnd_bind('<<Drop>>', self.handle_drop)
        
        ttk.Button(file_frame, text="选择文件", command=self.browse_input).grid(row=0, column=2, pady=8, ipadx=5)

        ttk.Label(file_frame, text="输出目录:").grid(row=1, column=0, sticky=tk.W, pady=8)
        ttk.Entry(file_frame, textvariable=self.output_path, width=50, font=FONT_BASE).grid(row=1, column=1, padx=15, pady=8, sticky=tk.EW)
        ttk.Button(file_frame, text="选择目录", command=self.browse_output).grid(row=1, column=2, pady=8, ipadx=5)
        
        file_frame.columnconfigure(1, weight=1)

        # ================= 2. 参数区 =================
        param_frame = ttk.LabelFrame(main_frame, text="性能参数", padding=20)
        param_frame.pack(fill=tk.X, pady=(0, 20))
        
        # 预设挡位按钮
        preset_frame = ttk.Frame(param_frame, style="Panel.TFrame")
        preset_frame.grid(row=0, column=0, columnspan=4, sticky=tk.EW, pady=(0, 20))
        ttk.Label(preset_frame, text="快速加载算力配置:", foreground=TEXT_COLOR).pack(side=tk.LEFT, padx=(0, 15))
        
        btn_fast = ttk.Button(preset_frame, text="⚡ 快速", command=lambda: self.apply_preset("256", "2", "4"))
        btn_fast.pack(side=tk.LEFT, padx=5, ipadx=5)
        ToolTip(btn_fast, "Segment: 256 | Overlap: 4 | Batch: 4\n速度最快，适合快速提取或无CUDA设备。")

        btn_bal = ttk.Button(preset_frame, text="⚖️ 均衡", command=lambda: self.apply_preset("512", "8", "8"))
        btn_bal.pack(side=tk.LEFT, padx=5, ipadx=5)
        ToolTip(btn_bal, "Segment: 512 | Overlap: 8 | Batch: 8\n推荐日常使用，完美平衡质量与速度。")

        btn_high = ttk.Button(preset_frame, text="💎 极致 (约3.0G 显存)", command=lambda: self.apply_preset("1024", "8", "16"))
        btn_high.pack(side=tk.LEFT, padx=5, ipadx=5)
        ToolTip(btn_high, "Segment: 1024 | Overlap: 8 | Batch: 16\n捕获更宽频段，音质最高。")

        # 详细参数
        ttk.Label(param_frame, text="Segment Size:").grid(row=1, column=0, sticky=tk.W, pady=10)
        seg_combo = ttk.Combobox(param_frame, textvariable=self.segment_size, values=["256", "512", "768", "1024"], width=12, state="readonly", font=FONT_BASE)
        seg_combo.grid(row=1, column=1, sticky=tk.W, padx=15, pady=10)
        ToolTip(seg_combo, "音频频段分析块大小。数值越大，模型能看到的上下文越长，分离更精准，但显存占用线性增加。")

        ttk.Label(param_frame, text="Overlap:").grid(row=1, column=2, sticky=tk.W, pady=10, padx=(20, 0))
        ov_combo = ttk.Combobox(param_frame, textvariable=self.overlap, values=["2", "4", "8", "16"], width=12, state="readonly", font=FONT_BASE)
        ov_combo.grid(row=1, column=3, sticky=tk.W, padx=15, pady=10)
        ToolTip(ov_combo, "段与段之间的重叠淡入淡出次数。值越大接缝伪影越少。8以上几乎无收益，且会增加处理时间。")

        ttk.Label(param_frame, text="Batch Size:").grid(row=2, column=0, sticky=tk.W, pady=10)
        batch_combo = ttk.Combobox(param_frame, textvariable=self.batch_size, values=["1", "2", "4", "8", "12", "16", "24"], width=12, state="readonly", font=FONT_BASE)
        batch_combo.grid(row=2, column=1, sticky=tk.W, padx=15, pady=10)
        ToolTip(batch_combo, "并发处理批次数。越大计算效率越高，对音质无影响，但会消耗显存。遇到显存耗尽时请调小。")

        ttk.Label(param_frame, text="Export Format:").grid(row=2, column=2, sticky=tk.W, pady=10, padx=(20, 0))
        fmt_combo = ttk.Combobox(param_frame, textvariable=self.out_format, values=["WAV", "FLAC", "MP3"], width=12, state="readonly", font=FONT_BASE)
        fmt_combo.grid(row=2, column=3, sticky=tk.W, padx=15, pady=10)
        
        param_frame.columnconfigure(1, weight=1)
        param_frame.columnconfigure(3, weight=1)

        # ================= 3. 操作区 =================
        op_frame = ttk.Frame(main_frame)
        op_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        self.btn_start = ttk.Button(op_frame, text="开始分离", style="Primary.TButton", command=self.start_thread)
        self.btn_start.pack(pady=(15, 25), ipadx=30, ipady=10)

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
        hw_label.pack(side=tk.LEFT, padx=10, pady=2)

    def apply_preset(self, segment, overlap, batch):
        self.segment_size.set(segment)
        self.overlap.set(overlap)
        self.batch_size.set(batch)
        self._console_append(f"> 已加载预设: Seg={segment}, Overlap={overlap}, Batch={batch} [就绪]", "accent")

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

    def handle_drop(self, event):
        file_path = event.data.strip('{}')
        self.input_path.set(file_path)
        if not self.output_path.get():
            self.output_path.set(os.path.dirname(file_path))

    def browse_input(self):
        file = filedialog.askopenfilename(filetypes=[("Audio Files", "*.wav *.flac *.mp3 *.m4a *.ogg")])
        if file:
            self.input_path.set(file)
            if not self.output_path.get():
                self.output_path.set(os.path.dirname(file))

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
        model_dir = BASE_DIR
        validate_runtime_model_file(model_name)
        separator_exe = resolve_audio_separator_executable()
        cmd = [
            separator_exe,
            input_file,
            "--model_filename", model_name,
            "--model_file_dir", model_dir,
            "--output_dir", output_dir,
            "--output_format", self.out_format.get(),
            "--mdxc_segment_size", self.segment_size.get(),
            "--mdxc_overlap", self.overlap.get(),
            "--mdxc_batch_size", self.batch_size.get()
        ]

        env = os.environ.copy()
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

    def confirm_secondary_separation(self, vocal_path):
        result = {"confirmed": False}
        decision_event = threading.Event()

        def _ask_user():
            self._console_append("> 分离完成。已获取人声轨，等待确认是否继续分离干声和和声...", "info")
            result["confirmed"] = messagebox.askyesno(
                "人声分离确认",
                "已完成六轨分离。\n\n"
                f"人声轨已提取：\n{os.path.basename(vocal_path)}\n\n"
                "是否继续分离人声为干声/和声？"
            )
            decision_event.set()

        self.root.after(0, _ask_user)
        decision_event.wait()
        return result["confirmed"]

    def start_thread(self):
        if not self.input_path.get() or not self.output_path.get():
            messagebox.showwarning("提示", "请输入源文件和输出路径")
            return
        
        self.btn_start.config(state=tk.DISABLED, text="分离中... 请勿关闭窗口")
        self._console_append("> 正在进行分离任务，请耐心等待...", "info")
        
        threading.Thread(target=self.run_separation, daemon=True).start()

    def run_separation(self):
        try:
            input_file = self.input_path.get()
            base_name = os.path.splitext(os.path.basename(input_file))[0]
            target_dir = os.path.join(self.output_path.get(), base_name)
            harmony_dir = os.path.join(target_dir, "02_干声和声")
            
            os.makedirs(target_dir, exist_ok=True)

            self.set_status("> 第一阶段：正在分离人声与伴奏，请耐心等待...", "#FFAA00")
            self.run_separator_command(input_file, target_dir, self.model_name)

            vocal_path = self.find_vocal_track(target_dir, base_name)
            did_secondary_split = False

            if self.confirm_secondary_separation(vocal_path):
                os.makedirs(harmony_dir, exist_ok=True)
                self.set_status("> 第二阶段：正在分离干声与和声，请耐心等待...", "#FFAA00")
                self.run_separator_command(vocal_path, harmony_dir, self.harmony_model_name)
                did_secondary_split = True

            status_text = (
                "> 任务完成。已输出人声/伴奏，并完成干声/和声二次分离。"
                if did_secondary_split
                else "> 任务完成。已输出人声/伴奏结果。"
            )
            self.root.after(0, lambda target=target_dir, text=status_text: self.finish_success(target, text))
                
        except Exception as e:
            self.root.after(0, lambda: self.finish_error(str(e)))

    def finish_success(self, target_dir, status_text):
        self.btn_start.config(state=tk.NORMAL, text="开始分离")
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
        self.btn_start.config(state=tk.NORMAL, text="开始分离")
        self._console_append("> 任务中止。错误 🔴", "warn")
        
        if "CUDA out of memory" in msg:
            friendly_msg = "显存溢出！您的参数设置超出了当前显存容量。\n\n解决办法：\n1. 降低 Batch Size（这是最耗显存的）\n2. 尝试使用[快速]或[均衡]预设"
            messagebox.showerror("显存不足", friendly_msg)
        elif "模型文件损坏" in msg or "文件过小" in msg or "无法作为压缩包读取" in msg or "文件不存在" in msg:
            friendly_msg = f"模型文件异常，无法正常加载。\n\n{msg}\n\n解决方法：\n1. 关闭程序\n2. 删除提示中提到的模型文件（.ckpt）\n3. 重新启动程序，会自动重新下载"
            messagebox.showerror("模型文件损坏", friendly_msg)
        else:
            messagebox.showerror("运行错误", f"引擎日志:\n{msg}")
