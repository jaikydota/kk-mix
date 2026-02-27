import os
import sys
import json
import time
import gc
import subprocess
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import numpy as np
from PIL import Image
import shutil

class FFmpegVideoEditorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("智能视频剪辑工具 v7.0 - 完整增强版")
        self.root.geometry("900x850")
        
        # 控制变量
        self.is_paused = False
        self.is_stopped = False
        self.current_operation = None
        self.ffmpeg_path = self._find_ffmpeg()
        
        if not self.ffmpeg_path:
            messagebox.showerror("错误", "未找到FFmpeg！请安装FFmpeg并添加到系统PATH")
            sys.exit(1)
        
        # 初始化所有变量
        self.folder1_path = tk.StringVar()
        self.folder2_path = tk.StringVar()
        self.output_path = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Desktop", "视频输出"))
        self.audio_output_path = tk.StringVar(value="")
        self.audio_source = tk.StringVar(value="folder1")
        self.image_duration = tk.StringVar(value="5")
        
        # 转场拼接变量
        self.concat_folders = []
        for i in range(5):
            var = tk.StringVar()
            self.concat_folders.append(var)
        self.concat_output = tk.StringVar()
        self.concat_transition = tk.DoubleVar(value=0.5)
        
        # 画中画变量
        self.pip_bg_folder = tk.StringVar()
        self.pip_fg_folder = tk.StringVar()
        self.pip_output = tk.StringVar()
        self.pip_position = tk.StringVar(value="bottom_right")
        self.pip_scale = tk.DoubleVar(value=0.3)
        
        # 变速变量
        self.speed_folder = tk.StringVar()
        self.speed_output = tk.StringVar()
        self.speed_factor = tk.DoubleVar(value=1.5)
        self.speed_reverse = tk.BooleanVar(value=False)
        
        # 分割变量
        self.split_folder = tk.StringVar()
        self.split_duration = tk.StringVar(value="30")
        self.split_output = tk.StringVar()
        self.keep_remainder = tk.BooleanVar(value=True)
        self.extract_audio = tk.BooleanVar(value=False)
        
        # ===== 新增功能变量 =====
        # 旋转
        self.rotate_folder = tk.StringVar()
        self.rotate_output = tk.StringVar()
        self.rotate_angle = tk.StringVar(value="90")  # 90, 180, 270, hflip, vflip
        
        # 水印
        self.watermark_video_folder = tk.StringVar()
        self.watermark_image_path = tk.StringVar()
        self.watermark_output = tk.StringVar()
        self.watermark_position = tk.StringVar(value="top_right")
        self.watermark_opacity = tk.DoubleVar(value=0.8)
        self.watermark_scale = tk.DoubleVar(value=0.2)
        
        # 音量
        self.volume_folder = tk.StringVar()
        self.volume_output = tk.StringVar()
        self.volume_factor = tk.DoubleVar(value=1.0)
        
        # 格式转换
        self.convert_folder = tk.StringVar()
        self.convert_output = tk.StringVar()
        self.convert_format = tk.StringVar(value="mp4")
        
        # 提取帧
        self.extract_folder = tk.StringVar()
        self.extract_output = tk.StringVar()
        self.extract_interval = tk.StringVar(value="5")  # 秒
        
        # 支持的文件类型
        self.video_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm'}
        self.image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff'}
        self.all_extensions = self.video_extensions | self.image_extensions
        
        self.create_widgets()
        
    def _find_ffmpeg(self):
        """查找FFmpeg"""
        # PyInstaller 打包后优先从捆绑目录查找
        if getattr(sys, 'frozen', False):
            bundled = os.path.join(sys._MEIPASS, 'ffmpeg.exe')
            if os.path.exists(bundled):
                return bundled
            exe_dir = os.path.dirname(sys.executable)
            local = os.path.join(exe_dir, 'ffmpeg.exe')
            if os.path.exists(local):
                return local

        for cmd in ['ffmpeg', 'ffmpeg.exe']:
            try:
                subprocess.run([cmd, '-version'], capture_output=True, check=True)
                return cmd
            except:
                pass
        
        common_paths = [
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
            r"D:\ffmpeg\bin\ffmpeg.exe"
        ]
        for path in common_paths:
            if os.path.exists(path):
                return path
        return None
    
    def create_widgets(self):
        """创建主界面"""
        self.processing_lock = threading.Lock()
        
        # FFmpeg状态
        status_frame = ttk.Frame(self.root)
        status_frame.pack(fill='x', padx=10, pady=5)
        ttk.Label(status_frame, text=f"FFmpeg路径: {self.ffmpeg_path}", foreground='green').pack(side='left')
        ttk.Button(status_frame, text="测试FFmpeg", command=self.test_ffmpeg).pack(side='right', padx=5)
        
        # 标题
        title_label = ttk.Label(self.root, text="智能视频剪辑工具 v7.0 - 完整增强版", font=("Arial", 16, "bold"))
        title_label.pack(pady=10)
        
        # 创建Notebook
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill='both', expand=True, padx=10, pady=5)
        
        # 原有功能标签页
        merge_frame = ttk.Frame(notebook)
        notebook.add(merge_frame, text="左右分屏合并")
        self.create_merge_tab(merge_frame)
        
        split_frame = ttk.Frame(notebook)
        notebook.add(split_frame, text="批量分割视频")
        self.create_split_tab(split_frame)
        
        concat_frame = ttk.Frame(notebook)
        notebook.add(concat_frame, text="视频转场拼接")
        self.create_concat_tab(concat_frame)
        
        pip_frame = ttk.Frame(notebook)
        notebook.add(pip_frame, text="画中画合成")
        self.create_pip_tab(pip_frame)
        
        speed_frame = ttk.Frame(notebook)
        notebook.add(speed_frame, text="批量变速/倒放")
        self.create_speed_tab(speed_frame)
        
        # ===== 新增功能标签页 =====
        rotate_frame = ttk.Frame(notebook)
        notebook.add(rotate_frame, text="批量旋转/翻转")
        self.create_rotate_tab(rotate_frame)
        
        watermark_frame = ttk.Frame(notebook)
        notebook.add(watermark_frame, text="批量添加水印")
        self.create_watermark_tab(watermark_frame)
        
        volume_frame = ttk.Frame(notebook)
        notebook.add(volume_frame, text="批量调整音量")
        self.create_volume_tab(volume_frame)
        
        convert_frame = ttk.Frame(notebook)
        notebook.add(convert_frame, text="批量格式转换")
        self.create_convert_tab(convert_frame)
        
        extract_frame = ttk.Frame(notebook)
        notebook.add(extract_frame, text="批量提取帧")
        self.create_extract_tab(extract_frame)
        
        # 性能设置
        perf_frame = ttk.LabelFrame(self.root, text="性能与稳定性设置", padding=5)
        perf_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(perf_frame, text="并行线程数:").pack(side='left', padx=5)
        self.thread_count = tk.StringVar(value="1")
        ttk.Entry(perf_frame, textvariable=self.thread_count, width=5, state='readonly').pack(side='left', padx=5)
        
        self.speed_priority = tk.BooleanVar(value=True)
        ttk.Checkbutton(perf_frame, text="极速模式（ultrafast）", variable=self.speed_priority).pack(side='left', padx=10)
        
        # 控制按钮
        control_frame = ttk.Frame(self.root)
        control_frame.pack(fill='x', padx=10, pady=5)
        
        self.pause_btn = ttk.Button(control_frame, text="暂停", command=self.toggle_pause, state='disabled')
        self.pause_btn.pack(side='left', padx=5)
        
        self.stop_btn = ttk.Button(control_frame, text="停止", command=self.stop_operation, state='disabled')
        self.stop_btn.pack(side='left', padx=5)
        
        # 进度条
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(self.root, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill='x', padx=10, pady=5)
        
        # 状态标签
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(self.root, textvariable=self.status_var, relief='sunken', anchor='w').pack(fill='x', padx=10, pady=5)
        
        # 日志输出
        log_frame = ttk.LabelFrame(self.root, text="操作日志", padding=5)
        log_frame.pack(fill='x', padx=10, pady=5)
        
        self.log_text = tk.Text(log_frame, height=12, wrap=tk.WORD)
        self.log_text.pack(fill='both')
        
    # ===== 核心方法（保持不变）=====
    
    def log(self, message):
        """线程安全日志记录"""
        with self.processing_lock:
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.log_text.insert('end', f"[{timestamp}] {message}\n")
            self.log_text.see('end')
            self.root.update()
            
    def update_status(self, message):
        """更新状态栏"""
        self.status_var.set(message)
        self.root.update()
        
    def test_ffmpeg(self):
        """测试FFmpeg"""
        self.log("=== 测试FFmpeg ===")
        try:
            result = subprocess.run([self.ffmpeg_path, '-version'], capture_output=True, text=True, 
                                   encoding='utf-8', errors='ignore')
            if result.returncode == 0:
                self.log("✓ FFmpeg测试成功")
                version_line = result.stdout.split('\n')[0]
                self.log(f"  {version_line}")
            else:
                self.log("✗ FFmpeg测试失败")
                self.log(f"  错误: {result.stderr}")
        except Exception as e:
            self.log(f"✗ FFmpeg测试异常: {e}")
    
    def toggle_pause(self):
        """切换暂停/继续"""
        self.is_paused = not self.is_paused
        if self.is_paused:
            self.pause_btn.config(text="继续")
            self.update_status("已暂停")
            self.log("操作已暂停...")
        else:
            self.pause_btn.config(text="暂停")
            self.update_status("处理中...")
            self.log("操作继续...")
            
    def stop_operation(self):
        """停止当前操作"""
        self.is_stopped = True
        self.update_status("正在停止...")
        self.log("正在停止操作...")
        
    def check_pause_stop(self):
        """检查暂停和停止状态"""
        while self.is_paused and not self.is_stopped:
            time.sleep(0.5)
        return self.is_stopped
            
    def set_controls_state(self, processing=True):
        """设置控件状态"""
        if processing:
            self.pause_btn.config(state='normal')
            self.stop_btn.config(state='normal')
        else:
            self.pause_btn.config(state='disabled')
            self.stop_btn.config(state='disabled')
            self.pause_btn.config(text="暂停")
            self.update_status("就绪")
            self.is_paused = False
            self.is_stopped = False
            
    def browse_folder(self, var, is_output=False):
        """浏览文件夹"""
        folder = filedialog.askdirectory(title="选择输出文件夹" if is_output else "选择文件夹")
        if folder:
            var.set(folder)
    
    def browse_file(self, var, filetypes=[("图片文件", "*.png;*.jpg;*.jpeg")]):
        """浏览文件"""
        file = filedialog.askopenfilename(title="选择文件", filetypes=filetypes)
        if file:
            var.set(file)
    
    def get_video_files(self, folder):
        """仅获取视频文件"""
        if not os.path.exists(folder):
            self.log(f"错误：文件夹不存在 {folder}")
            return []
        
        files = [f for f in os.listdir(folder) if Path(f).suffix.lower() in self.video_extensions]
        self.log(f"扫描视频文件夹: 发现 {len(files)} 个视频文件")
        if files:
            self.log(f"  示例: {files[:3]}")
        return sorted(files)
        
    def get_media_files(self, folder):
        """获取所有媒体文件"""
        if not os.path.exists(folder):
            self.log(f"错误：文件夹不存在 {folder}")
            return []
        
        files = [f for f in os.listdir(folder) if Path(f).suffix.lower() in self.all_extensions]
        self.log(f"扫描媒体文件夹: 发现 {len(files)} 个文件")
        if files:
            self.log(f"  示例: {files[:3]}")
        return sorted(files)
        
    def get_video_info_safe(self, video_path):
        """安全获取视频信息"""
        try:
            self.log(f"  正在读取: {os.path.basename(video_path)}")
            
            if not os.path.exists(video_path):
                self.log(f"    ✗ 文件不存在")
                return 0
            
            # 使用ffprobe
            ffprobe_path = self.ffmpeg_path.replace('ffmpeg', 'ffprobe')
            if os.path.exists(ffprobe_path) or shutil.which(ffprobe_path):
                ffprobe_cmd = [ffprobe_path, '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', video_path]
                if sys.platform == 'win32':
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    result = subprocess.run(ffprobe_cmd, capture_output=True, text=True, timeout=30, 
                                           startupinfo=startupinfo, encoding='utf-8', errors='ignore')
                else:
                    result = subprocess.run(ffprobe_cmd, capture_output=True, text=True, timeout=30,
                                           encoding='utf-8', errors='ignore')
                
                if result.returncode == 0 and result.stdout.strip():
                    duration = float(result.stdout.strip())
                    self.log(f"    ✓ 使用ffprobe读取: {duration:.1f}秒")
                    return duration
            
            # 备用方法: 使用ffmpeg -i
            cmd = [self.ffmpeg_path, '-i', video_path]
            if sys.platform == 'win32':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, 
                                       startupinfo=startupinfo, encoding='utf-8', errors='ignore')
            else:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                                       encoding='utf-8', errors='ignore')
            
            output_text = (result.stdout or '') + '\n' + (result.stderr or '')
            
            duration = 0
            for line in output_text.split('\n'):
                if 'Duration:' in line:
                    try:
                        time_str = line.split('Duration:')[1].split(',')[0].strip()
                        h, m, s = time_str.split(':')
                        duration = float(h) * 3600 + float(m) * 60 + float(s)
                        self.log(f"    ✓ 使用ffmpeg读取: {duration:.1f}秒")
                        break
                    except:
                        continue
            
            return duration
            
        except subprocess.TimeoutExpired:
            self.log(f"    ✗ 读取超时（30秒）")
            return 0
        except Exception as e:
            self.log(f"    ✗ 读取异常: {str(e)}")
            return 0
            
    def get_video_resolution(self, video_path):
        """获取视频分辨率"""
        try:
            cmd = [self.ffmpeg_path, '-i', video_path, '-f', 'null', '-']
            if sys.platform == 'win32':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, 
                                       startupinfo=startupinfo, encoding='utf-8', errors='ignore')
            else:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                                       encoding='utf-8', errors='ignore')
            
            for line in result.stderr.split('\n'):
                if 'Stream #0:0' in line and 'Video:' in line:
                    parts = line.split(', ')
                    for part in parts:
                        if 'x' in part and not part.startswith('Duration'):
                            try:
                                w, h = part.strip().split(' ')[0].split('x')
                                return int(w), int(h)
                            except:
                                pass
            return 1920, 1080
        except:
            return 1920, 1080

    # ===== 标签页创建（原有+新增）=====
    
    def create_merge_tab(self, parent):
        """创建分屏合并标签页"""
        ttk.Label(parent, text="文件夹1 (左侧视频/图片):").grid(row=0, column=0, sticky='w', padx=10, pady=5)
        ttk.Entry(parent, textvariable=self.folder1_path, width=45).grid(row=0, column=1, padx=5)
        ttk.Button(parent, text="浏览", command=lambda: self.browse_folder(self.folder1_path)).grid(row=0, column=2, padx=5)
        
        ttk.Label(parent, text="文件夹2 (右侧视频/图片):").grid(row=1, column=0, sticky='w', padx=10, pady=5)
        ttk.Entry(parent, textvariable=self.folder2_path, width=45).grid(row=1, column=1, padx=5)
        ttk.Button(parent, text="浏览", command=lambda: self.browse_folder(self.folder2_path)).grid(row=1, column=2, padx=5)
        
        ttk.Label(parent, text="输出文件夹:").grid(row=2, column=0, sticky='w', padx=10, pady=5)
        ttk.Entry(parent, textvariable=self.output_path, width=45).grid(row=2, column=1, padx=5)
        ttk.Button(parent, text="浏览", command=lambda: self.browse_folder(self.output_path, True)).grid(row=2, column=2, padx=5)
        
        audio_frame = ttk.LabelFrame(parent, text="音频源选择", padding=10)
        audio_frame.grid(row=3, column=0, columnspan=3, sticky='ew', padx=10, pady=5)
        ttk.Radiobutton(audio_frame, text="使用文件夹1音频", variable=self.audio_source, value="folder1").pack(side='left', padx=10)
        ttk.Radiobutton(audio_frame, text="使用文件夹2音频", variable=self.audio_source, value="folder2").pack(side='left', padx=10)
        ttk.Radiobutton(audio_frame, text="无音频", variable=self.audio_source, value="none").pack(side='left', padx=10)
        
        ttk.Label(parent, text="图片显示时长(秒):").grid(row=4, column=0, sticky='w', padx=10, pady=5)
        ttk.Entry(parent, textvariable=self.image_duration, width=10).grid(row=4, column=1, sticky='w', padx=5)
        
        ttk.Button(parent, text="开始分屏合并", command=self.start_merge, style='Accent.TButton').grid(row=5, column=0, columnspan=3, pady=15)
        parent.columnconfigure(1, weight=1)
        
    def create_split_tab(self, parent):
        """创建批量分割标签页"""
        ttk.Label(parent, text="视频文件夹:").grid(row=0, column=0, sticky='w', padx=10, pady=5)
        ttk.Entry(parent, textvariable=self.split_folder, width=45).grid(row=0, column=1, padx=5)
        ttk.Button(parent, text="浏览", command=lambda: self.browse_folder(self.split_folder)).grid(row=0, column=2, padx=5)
        
        ttk.Label(parent, text="每段时长(秒):").grid(row=1, column=0, sticky='w', padx=10, pady=5)
        ttk.Entry(parent, textvariable=self.split_duration, width=20).grid(row=1, column=1, sticky='w', padx=5)
        
        ttk.Label(parent, text="视频输出文件夹:").grid(row=2, column=0, sticky='w', padx=10, pady=5)
        ttk.Entry(parent, textvariable=self.split_output, width=45).grid(row=2, column=1, padx=5)
        ttk.Button(parent, text="浏览", command=lambda: self.browse_folder(self.split_output, True)).grid(row=2, column=2, padx=5)
        
        ttk.Label(parent, text="音频输出文件夹(可选):").grid(row=3, column=0, sticky='w', padx=10, pady=5)
        ttk.Entry(parent, textvariable=self.audio_output_path, width=45).grid(row=3, column=1, padx=5)
        ttk.Button(parent, text="浏览", command=lambda: self.browse_folder(self.audio_output_path, True)).grid(row=3, column=2, padx=5)
        
        options_frame = ttk.Frame(parent)
        options_frame.grid(row=4, column=0, columnspan=3, sticky='w', padx=10, pady=5)
        ttk.Checkbutton(options_frame, text="保留不足时长的最后片段", variable=self.keep_remainder).pack(side='left', padx=5)
        ttk.Checkbutton(options_frame, text="提取音频到独立文件", variable=self.extract_audio).pack(side='left', padx=5)
        
        ttk.Button(parent, text="开始批量分割", command=self.start_split, style='Accent.TButton').grid(row=5, column=0, columnspan=3, pady=15)
        parent.columnconfigure(1, weight=1)
    
    def create_concat_tab(self, parent):
        """创建转场拼接标签页"""
        folders_frame = ttk.LabelFrame(parent, text="视频文件夹（最多5个，按顺序拼接）", padding=10)
        folders_frame.grid(row=0, column=0, columnspan=3, sticky='ew', padx=10, pady=5)
        
        for i in range(5):
            frame = ttk.Frame(folders_frame)
            frame.pack(fill='x', padx=5, pady=2)
            ttk.Label(frame, text=f"文件夹{i+1}:", width=10).pack(side='left')
            ttk.Entry(frame, textvariable=self.concat_folders[i], width=35).pack(side='left', padx=5)
            ttk.Button(frame, text="浏览", command=lambda i=i: self.browse_folder(self.concat_folders[i])).pack(side='left')
        
        ttk.Label(parent, text="输出文件夹:").grid(row=1, column=0, sticky='w', padx=10, pady=5)
        ttk.Entry(parent, textvariable=self.concat_output, width=45).grid(row=1, column=1, padx=5)
        ttk.Button(parent, text="浏览", command=lambda: self.browse_folder(self.concat_output, True)).grid(row=1, column=2, padx=5)
        
        transition_frame = ttk.LabelFrame(parent, text="转场设置", padding=10)
        transition_frame.grid(row=2, column=0, columnspan=3, sticky='ew', padx=10, pady=5)
        
        ttk.Label(transition_frame, text="转场时长(秒):").pack(side='left', padx=5)
        ttk.Entry(transition_frame, textvariable=self.concat_transition, width=10).pack(side='left', padx=5)
        ttk.Label(transition_frame, text=" (0=无转场)", foreground='gray').pack(side='left', padx=5)
        
        ttk.Button(parent, text="开始转场拼接", command=self.start_concat, style='Accent.TButton').grid(row=3, column=0, columnspan=3, pady=15)
        parent.columnconfigure(1, weight=1)
        
    def create_pip_tab(self, parent):
        """创建画中画标签页"""
        ttk.Label(parent, text="背景视频文件夹:").grid(row=0, column=0, sticky='w', padx=10, pady=5)
        ttk.Entry(parent, textvariable=self.pip_bg_folder, width=45).grid(row=0, column=1, padx=5)
        ttk.Button(parent, text="浏览", command=lambda: self.browse_folder(self.pip_bg_folder)).grid(row=0, column=2, padx=5)
        
        ttk.Label(parent, text="前景视频/图片文件夹:").grid(row=1, column=0, sticky='w', padx=10, pady=5)
        ttk.Entry(parent, textvariable=self.pip_fg_folder, width=45).grid(row=1, column=1, padx=5)
        ttk.Button(parent, text="浏览", command=lambda: self.browse_folder(self.pip_fg_folder)).grid(row=1, column=2, padx=5)
        
        ttk.Label(parent, text="输出文件夹:").grid(row=2, column=0, sticky='w', padx=10, pady=5)
        ttk.Entry(parent, textvariable=self.pip_output, width=45).grid(row=2, column=1, padx=5)
        ttk.Button(parent, text="浏览", command=lambda: self.browse_folder(self.pip_output, True)).grid(row=2, column=2, padx=5)
        
        pip_frame = ttk.LabelFrame(parent, text="画中画设置", padding=10)
        pip_frame.grid(row=3, column=0, columnspan=3, sticky='ew', padx=10, pady=5)
        
        ttk.Label(pip_frame, text="位置:").pack(side='left', padx=5)
        ttk.Combobox(pip_frame, textvariable=self.pip_position, values=["top_left", "top_right", "bottom_left", "bottom_right"], width=12, state='readonly').pack(side='left', padx=5)
        
        ttk.Label(pip_frame, text="缩放比例:").pack(side='left', padx=15)
        ttk.Entry(pip_frame, textvariable=self.pip_scale, width=10).pack(side='left', padx=5)
        ttk.Label(pip_frame, text=" (0.1-1.0)", foreground='gray').pack(side='left', padx=5)
        
        ttk.Button(parent, text="开始画中画合成", command=self.start_pip, style='Accent.TButton').grid(row=4, column=0, columnspan=3, pady=15)
        parent.columnconfigure(1, weight=1)
        
    def create_speed_tab(self, parent):
        """创建变速标签页"""
        ttk.Label(parent, text="视频文件夹:").grid(row=0, column=0, sticky='w', padx=10, pady=5)
        ttk.Entry(parent, textvariable=self.speed_folder, width=45).grid(row=0, column=1, padx=5)
        ttk.Button(parent, text="浏览", command=lambda: self.browse_folder(self.speed_folder)).grid(row=0, column=2, padx=5)
        
        ttk.Label(parent, text="输出文件夹:").grid(row=1, column=0, sticky='w', padx=10, pady=5)
        ttk.Entry(parent, textvariable=self.speed_output, width=45).grid(row=1, column=1, padx=5)
        ttk.Button(parent, text="浏览", command=lambda: self.browse_folder(self.speed_output, True)).grid(row=1, column=2, padx=5)
        
        speed_frame = ttk.LabelFrame(parent, text="速度设置", padding=10)
        speed_frame.grid(row=2, column=0, columnspan=3, sticky='ew', padx=10, pady=5)
        
        ttk.Label(speed_frame, text="速度倍数:").pack(side='left', padx=5)
        ttk.Entry(speed_frame, textvariable=self.speed_factor, width=10).pack(side='left', padx=5)
        ttk.Label(speed_frame, text=" (0.5=慢放, 2.0=快放)", foreground='gray').pack(side='left', padx=5)
        
        ttk.Checkbutton(speed_frame, text="倒放视频", variable=self.speed_reverse).pack(side='left', padx=20)
        
        ttk.Button(parent, text="开始批量变速", command=self.start_speed, style='Accent.TButton').grid(row=3, column=0, columnspan=3, pady=15)
        parent.columnconfigure(1, weight=1)
        
    # ===== 新增功能标签页 =====
    
    def create_rotate_tab(self, parent):
        """创建旋转/翻转标签页"""
        ttk.Label(parent, text="视频文件夹:").grid(row=0, column=0, sticky='w', padx=10, pady=5)
        ttk.Entry(parent, textvariable=self.rotate_folder, width=45).grid(row=0, column=1, padx=5)
        ttk.Button(parent, text="浏览", command=lambda: self.browse_folder(self.rotate_folder)).grid(row=0, column=2, padx=5)
        
        ttk.Label(parent, text="输出文件夹:").grid(row=1, column=0, sticky='w', padx=10, pady=5)
        ttk.Entry(parent, textvariable=self.rotate_output, width=45).grid(row=1, column=1, padx=5)
        ttk.Button(parent, text="浏览", command=lambda: self.browse_folder(self.rotate_output, True)).grid(row=1, column=2, padx=5)
        
        rotate_frame = ttk.LabelFrame(parent, text="旋转/翻转选项", padding=10)
        rotate_frame.grid(row=2, column=0, columnspan=3, sticky='ew', padx=10, pady=5)
        
        ttk.Label(rotate_frame, text="选择操作:").pack(side='left', padx=5)
        rotate_combo = ttk.Combobox(rotate_frame, textvariable=self.rotate_angle, 
                                   values=["90", "180", "270", "hflip", "vflip"], 
                                   width=12, state='readonly')
        rotate_combo.pack(side='left', padx=5)
        ttk.Label(rotate_frame, text=" (90/180/270=旋转, hflip=水平翻转, vflip=垂直翻转)", foreground='gray').pack(side='left', padx=5)
        
        ttk.Button(parent, text="开始批量旋转", command=self.start_rotate, style='Accent.TButton').grid(row=3, column=0, columnspan=3, pady=15)
        parent.columnconfigure(1, weight=1)
        
    def create_watermark_tab(self, parent):
        """创建水印标签页"""
        ttk.Label(parent, text="视频文件夹:").grid(row=0, column=0, sticky='w', padx=10, pady=5)
        ttk.Entry(parent, textvariable=self.watermark_video_folder, width=45).grid(row=0, column=1, padx=5)
        ttk.Button(parent, text="浏览", command=lambda: self.browse_folder(self.watermark_video_folder)).grid(row=0, column=2, padx=5)
        
        ttk.Label(parent, text="水印图片:").grid(row=1, column=0, sticky='w', padx=10, pady=5)
        ttk.Entry(parent, textvariable=self.watermark_image_path, width=45).grid(row=1, column=1, padx=5)
        ttk.Button(parent, text="浏览", command=lambda: self.browse_file(self.watermark_image_path, [("图片", "*.png;*.jpg;*.jpeg")])).grid(row=1, column=2, padx=5)
        
        ttk.Label(parent, text="输出文件夹:").grid(row=2, column=0, sticky='w', padx=10, pady=5)
        ttk.Entry(parent, textvariable=self.watermark_output, width=45).grid(row=2, column=1, padx=5)
        ttk.Button(parent, text="浏览", command=lambda: self.browse_folder(self.watermark_output, True)).grid(row=2, column=2, padx=5)
        
        watermark_frame = ttk.LabelFrame(parent, text="水印设置", padding=10)
        watermark_frame.grid(row=3, column=0, columnspan=3, sticky='ew', padx=10, pady=5)
        
        ttk.Label(watermark_frame, text="位置:").pack(side='left', padx=5)
        ttk.Combobox(watermark_frame, textvariable=self.watermark_position, 
                    values=["top_left", "top_right", "bottom_left", "bottom_right", "center"], 
                    width=12, state='readonly').pack(side='left', padx=5)
        
        ttk.Label(watermark_frame, text="透明度:").pack(side='left', padx=15)
        ttk.Entry(watermark_frame, textvariable=self.watermark_opacity, width=10).pack(side='left', padx=5)
        ttk.Label(watermark_frame, text=" (0.1-1.0)", foreground='gray').pack(side='left', padx=5)
        
        ttk.Label(watermark_frame, text="缩放:").pack(side='left', padx=15)
        ttk.Entry(watermark_frame, textvariable=self.watermark_scale, width=10).pack(side='left', padx=5)
        ttk.Label(watermark_frame, text=" (0.05-0.5)", foreground='gray').pack(side='left', padx=5)
        
        ttk.Button(parent, text="开始批量添加水印", command=self.start_watermark, style='Accent.TButton').grid(row=4, column=0, columnspan=3, pady=15)
        parent.columnconfigure(1, weight=1)
        
    def create_volume_tab(self, parent):
        """创建音量调整标签页"""
        ttk.Label(parent, text="视频文件夹:").grid(row=0, column=0, sticky='w', padx=10, pady=5)
        ttk.Entry(parent, textvariable=self.volume_folder, width=45).grid(row=0, column=1, padx=5)
        ttk.Button(parent, text="浏览", command=lambda: self.browse_folder(self.volume_folder)).grid(row=0, column=2, padx=5)
        
        ttk.Label(parent, text="输出文件夹:").grid(row=1, column=0, sticky='w', padx=10, pady=5)
        ttk.Entry(parent, textvariable=self.volume_output, width=45).grid(row=1, column=1, padx=5)
        ttk.Button(parent, text="浏览", command=lambda: self.browse_folder(self.volume_output, True)).grid(row=1, column=2, padx=5)
        
        volume_frame = ttk.LabelFrame(parent, text="音量设置", padding=10)
        volume_frame.grid(row=2, column=0, columnspan=3, sticky='ew', padx=10, pady=5)
        
        ttk.Label(volume_frame, text="音量倍数:").pack(side='left', padx=5)
        ttk.Entry(volume_frame, textvariable=self.volume_factor, width=10).pack(side='left', padx=5)
        ttk.Label(volume_frame, text=" (0.5=减半, 1.0=不变, 2.0=加倍)", foreground='gray').pack(side='left', padx=5)
        
        ttk.Button(parent, text="开始批量调整音量", command=self.start_volume, style='Accent.TButton').grid(row=3, column=0, columnspan=3, pady=15)
        parent.columnconfigure(1, weight=1)
        
    def create_convert_tab(self, parent):
        """创建格式转换标签页"""
        ttk.Label(parent, text="视频文件夹:").grid(row=0, column=0, sticky='w', padx=10, pady=5)
        ttk.Entry(parent, textvariable=self.convert_folder, width=45).grid(row=0, column=1, padx=5)
        ttk.Button(parent, text="浏览", command=lambda: self.browse_folder(self.convert_folder)).grid(row=0, column=2, padx=5)
        
        ttk.Label(parent, text="输出文件夹:").grid(row=1, column=0, sticky='w', padx=10, pady=5)
        ttk.Entry(parent, textvariable=self.convert_output, width=45).grid(row=1, column=1, padx=5)
        ttk.Button(parent, text="浏览", command=lambda: self.browse_folder(self.convert_output, True)).grid(row=1, column=2, padx=5)
        
        convert_frame = ttk.LabelFrame(parent, text="格式设置", padding=10)
        convert_frame.grid(row=2, column=0, columnspan=3, sticky='ew', padx=10, pady=5)
        
        ttk.Label(convert_frame, text="目标格式:").pack(side='left', padx=5)
        ttk.Combobox(convert_frame, textvariable=self.convert_format, 
                    values=["mp4", "avi", "mov", "mkv"], 
                    width=12, state='readonly').pack(side='left', padx=5)
        ttk.Label(convert_frame, text=" (MP4推荐)", foreground='gray').pack(side='left', padx=5)
        
        ttk.Button(parent, text="开始批量转换", command=self.start_convert, style='Accent.TButton').grid(row=3, column=0, columnspan=3, pady=15)
        parent.columnconfigure(1, weight=1)
        
    def create_extract_tab(self, parent):
        """创建提取帧标签页"""
        ttk.Label(parent, text="视频文件夹:").grid(row=0, column=0, sticky='w', padx=10, pady=5)
        ttk.Entry(parent, textvariable=self.extract_folder, width=45).grid(row=0, column=1, padx=5)
        ttk.Button(parent, text="浏览", command=lambda: self.browse_folder(self.extract_folder)).grid(row=0, column=2, padx=5)
        
        ttk.Label(parent, text="输出文件夹:").grid(row=1, column=0, sticky='w', padx=10, pady=5)
        ttk.Entry(parent, textvariable=self.extract_output, width=45).grid(row=1, column=1, padx=5)
        ttk.Button(parent, text="浏览", command=lambda: self.browse_folder(self.extract_output, True)).grid(row=1, column=2, padx=5)
        
        extract_frame = ttk.LabelFrame(parent, text="提取设置", padding=10)
        extract_frame.grid(row=2, column=0, columnspan=3, sticky='ew', padx=10, pady=5)
        
        ttk.Label(extract_frame, text="提取间隔:").pack(side='left', padx=5)
        ttk.Entry(extract_frame, textvariable=self.extract_interval, width=10).pack(side='left', padx=5)
        ttk.Label(extract_frame, text=" 秒/帧 (每N秒提取1帧)", foreground='gray').pack(side='left', padx=5)
        
        ttk.Button(parent, text="开始批量提取帧", command=self.start_extract, style='Accent.TButton').grid(row=3, column=0, columnspan=3, pady=15)
        parent.columnconfigure(1, weight=1)
        
    # ===== 启动方法（新增）=====
    
    def start_rotate(self):
        thread = threading.Thread(target=self.batch_rotate_operation)
        thread.daemon = True
        thread.start()
        
    def start_watermark(self):
        thread = threading.Thread(target=self.batch_watermark_operation)
        thread.daemon = True
        thread.start()
        
    def start_volume(self):
        thread = threading.Thread(target=self.batch_volume_operation)
        thread.daemon = True
        thread.start()
        
    def start_convert(self):
        thread = threading.Thread(target=self.batch_convert_operation)
        thread.daemon = True
        thread.start()
        
    def start_extract(self):
        thread = threading.Thread(target=self.batch_extract_operation)
        thread.daemon = True
        thread.start()
    
    # ===== 新增功能实现 =====
    
    def batch_rotate_operation(self):
        """批量旋转/翻转视频"""
        self.current_operation = "rotate"
        self.set_controls_state(True)
        self.progress_var.set(0)
        
        try:
            folder = self.rotate_folder.get()
            output_folder = self.rotate_output.get()
            angle = self.rotate_angle.get()
            
            if not folder or not output_folder:
                messagebox.showerror("错误", "请选择视频文件夹和输出文件夹！")
                return
            
            os.makedirs(output_folder, exist_ok=True)
            
            video_files = self.get_video_files(folder)
            
            if not video_files:
                messagebox.showerror("错误", "文件夹中没有找到视频文件！")
                return
            
            self.log(f"\n{'='*60}")
            self.log(f"开始批量旋转/翻转")
            self.log(f"视频数: {len(video_files)} 个")
            self.log(f"操作: {angle}")
            self.log(f"{'='*60}\n")
            
            success_count = 0
            
            for idx, video_file in enumerate(video_files, 1):
                if self.check_pause_stop():
                    break
                
                video_path = os.path.join(folder, video_file)
                output_name = f"rotate_{idx:03d}_{angle}_{Path(video_file).stem}.mp4"
                output_path = os.path.join(output_folder, output_name)
                
                self.log(f"\n[{idx}/{len(video_files)}] 处理: {video_file}")
                
                if self._rotate_video_ffmpeg(video_path, output_path, angle):
                    success_count += 1
                    self.log(f"✓ 成功: {output_name}")
                else:
                    self.log(f"✗ 失败: {video_file}")
                
                self.progress_var.set((idx / len(video_files)) * 100)
                self.update_status(f"旋转中... {idx}/{len(video_files)}")
            
            self.log(f"\n{'='*60}")
            self.log(f"完成！成功处理 {success_count}/{len(video_files)} 个视频")
            self.log(f"{'='*60}")
            
            if success_count > 0:
                messagebox.showinfo("完成", f"成功处理 {success_count} 个视频！")
            
        except Exception as e:
            messagebox.showerror("错误", f"旋转处理失败: {str(e)}")
            self.log(f"✗ 错误: {str(e)}")
        finally:
            self.set_controls_state(False)
    
    def _rotate_video_ffmpeg(self, input_path, output_path, angle):
        """FFmpeg旋转/翻转视频"""
        try:
            # 构建旋转滤镜
            if angle == "90":
                vf_filter = "transpose=1"  # 顺时针90度
            elif angle == "180":
                vf_filter = "rotate=PI"  # 180度
            elif angle == "270":
                vf_filter = "transpose=2"  # 逆时针90度
            elif angle == "hflip":
                vf_filter = "hflip"  # 水平翻转
            elif angle == "vflip":
                vf_filter = "vflip"  # 垂直翻转
            else:
                vf_filter = "null"
            
            cmd = [
                self.ffmpeg_path,
                '-i', input_path,
                '-vf', vf_filter,
                '-c:v', 'libx264',
                '-preset', 'ultrafast' if self.speed_priority.get() else 'medium',
                '-crf', '23',
                '-c:a', 'copy',  # 音频直接复制
                '-threads', '0',
                '-y',
                output_path
            ]
            
            if sys.platform == 'win32':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=600, 
                                       startupinfo=startupinfo, encoding='utf-8', errors='ignore')
            else:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=600,
                                       encoding='utf-8', errors='ignore')
            
            if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                file_size_mb = os.path.getsize(output_path) / 1024 / 1024
                self.log(f"    ✓ 成功: {os.path.basename(output_path)} ({file_size_mb:.1f} MB)")
                return True
            else:
                self.log(f"    ✗ 失败: {result.stderr[:200] if result.stderr else '未知错误'}")
                return False
            
        except Exception as e:
            self.log(f"    ✗ 异常: {str(e)}")
            return False
    
    def batch_watermark_operation(self):
        """批量添加水印"""
        self.current_operation = "watermark"
        self.set_controls_state(True)
        self.progress_var.set(0)
        
        try:
            video_folder = self.watermark_video_folder.get()
            watermark_image = self.watermark_image_path.get()
            output_folder = self.watermark_output.get()
            position = self.watermark_position.get()
            opacity = float(self.watermark_opacity.get())
            scale = float(self.watermark_scale.get())
            
            if not all([video_folder, watermark_image, output_folder]):
                messagebox.showerror("错误", "请选择视频文件夹、水印图片和输出文件夹！")
                return
            
            if not os.path.exists(watermark_image):
                messagebox.showerror("错误", "水印图片不存在！")
                return
            
            os.makedirs(output_folder, exist_ok=True)
            
            video_files = self.get_video_files(video_folder)
            
            if not video_files:
                messagebox.showerror("错误", "文件夹中没有找到视频文件！")
                return
            
            self.log(f"\n{'='*60}")
            self.log(f"开始批量添加水印")
            self.log(f"视频数: {len(video_files)} 个")
            self.log(f"水印位置: {position}, 透明度: {opacity}, 缩放: {scale}")
            self.log(f"{'='*60}\n")
            
            success_count = 0
            
            for idx, video_file in enumerate(video_files, 1):
                if self.check_pause_stop():
                    break
                
                video_path = os.path.join(video_folder, video_file)
                output_name = f"watermark_{idx:03d}_{Path(video_file).stem}.mp4"
                output_path = os.path.join(output_folder, output_name)
                
                self.log(f"\n[{idx}/{len(video_files)}] 处理: {video_file}")
                
                if self._watermark_video_ffmpeg(video_path, watermark_image, output_path, position, opacity, scale):
                    success_count += 1
                    self.log(f"✓ 成功: {output_name}")
                else:
                    self.log(f"✗ 失败: {video_file}")
                
                self.progress_var.set((idx / len(video_files)) * 100)
                self.update_status(f"添加水印中... {idx}/{len(video_files)}")
            
            self.log(f"\n{'='*60}")
            self.log(f"完成！成功处理 {success_count}/{len(video_files)} 个视频")
            self.log(f"{'='*60}")
            
            if success_count > 0:
                messagebox.showinfo("完成", f"成功添加 {success_count} 个水印！")
            
        except Exception as e:
            messagebox.showerror("错误", f"水印添加失败: {str(e)}")
            self.log(f"✗ 错误: {str(e)}")
        finally:
            self.set_controls_state(False)
    
    def _watermark_video_ffmpeg(self, input_path, watermark_path, output_path, position, opacity, scale):
        """FFmpeg添加水印"""
        try:
            # 获取视频分辨率
            video_w, video_h = self.get_video_resolution(input_path)
            
            # 获取水印图片分辨率
            with Image.open(watermark_path) as img:
                watermark_w, watermark_h = img.size
            
            # 计算水印缩放后的尺寸
            target_watermark_w = int(video_w * scale)
            target_watermark_h = int(watermark_h * (target_watermark_w / watermark_w))
            
            # 计算位置
            if position == "top_left":
                x = 0
                y = 0
            elif position == "top_right":
                x = video_w - target_watermark_w
                y = 0
            elif position == "bottom_left":
                x = 0
                y = video_h - target_watermark_h
            elif position == "bottom_right":
                x = video_w - target_watermark_w
                y = video_h - target_watermark_h
            else:  # center
                x = (video_w - target_watermark_w) // 2
                y = (video_h - target_watermark_h) // 2
            
            # 构建滤镜
            watermark_filter = (
                f"[1:v]scale={target_watermark_w}:{target_watermark_h}[wm];"
                f"[wm]format=rgba,colorchannelmixer=aa={opacity}[wm_alpha];"
                f"[0:v][wm_alpha]overlay=x={x}:y={y}[v]"
            )
            
            cmd = [
                self.ffmpeg_path,
                '-i', input_path,
                '-i', watermark_path,
                '-filter_complex', watermark_filter,
                '-map', '[v]',
                '-map', '0:a',
                '-c:v', 'libx264',
                '-preset', 'ultrafast' if self.speed_priority.get() else 'medium',
                '-crf', '23',
                '-c:a', 'copy',  # 音频直接复制
                '-threads', '0',
                '-y',
                output_path
            ]
            
            if sys.platform == 'win32':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=600, 
                                       startupinfo=startupinfo, encoding='utf-8', errors='ignore')
            else:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=600,
                                       encoding='utf-8', errors='ignore')
            
            if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                file_size_mb = os.path.getsize(output_path) / 1024 / 1024
                self.log(f"    ✓ 成功: {os.path.basename(output_path)} ({file_size_mb:.1f} MB)")
                return True
            else:
                self.log(f"    ✗ 失败: {result.stderr[:200] if result.stderr else '未知错误'}")
                return False
            
        except Exception as e:
            self.log(f"    ✗ 异常: {str(e)}")
            return False
    
    def batch_volume_operation(self):
        """批量调整音量"""
        self.current_operation = "volume"
        self.set_controls_state(True)
        self.progress_var.set(0)
        
        try:
            folder = self.volume_folder.get()
            output_folder = self.volume_output.get()
            factor = float(self.volume_factor.get())
            
            if not folder or not output_folder:
                messagebox.showerror("错误", "请选择视频文件夹和输出文件夹！")
                return
            
            os.makedirs(output_folder, exist_ok=True)
            
            video_files = self.get_video_files(folder)
            
            if not video_files:
                messagebox.showerror("错误", "文件夹中没有找到视频文件！")
                return
            
            self.log(f"\n{'='*60}")
            self.log(f"开始批量调整音量")
            self.log(f"视频数: {len(video_files)} 个")
            self.log(f"音量倍数: {factor}")
            self.log(f"{'='*60}\n")
            
            success_count = 0
            
            for idx, video_file in enumerate(video_files, 1):
                if self.check_pause_stop():
                    break
                
                video_path = os.path.join(folder, video_file)
                output_name = f"volume_{idx:03d}_{factor}x_{Path(video_file).stem}.mp4"
                output_path = os.path.join(output_folder, output_name)
                
                self.log(f"\n[{idx}/{len(video_files)}] 处理: {video_file}")
                
                if self._volume_change_ffmpeg(video_path, output_path, factor):
                    success_count += 1
                    self.log(f"✓ 成功: {output_name}")
                else:
                    self.log(f"✗ 失败: {video_file}")
                
                self.progress_var.set((idx / len(video_files)) * 100)
                self.update_status(f"音量调整中... {idx}/{len(video_files)}")
            
            self.log(f"\n{'='*60}")
            self.log(f"完成！成功处理 {success_count}/{len(video_files)} 个视频")
            self.log(f"{'='*60}")
            
            if success_count > 0:
                messagebox.showinfo("完成", f"成功调整 {success_count} 个视频的音量！")
            
        except Exception as e:
            messagebox.showerror("错误", f"音量调整失败: {str(e)}")
            self.log(f"✗ 错误: {str(e)}")
        finally:
            self.set_controls_state(False)
    
    def _volume_change_ffmpeg(self, input_path, output_path, factor):
        """FFmpeg调整音量"""
        try:
            # 使用volume滤镜调整音量
            cmd = [
                self.ffmpeg_path,
                '-i', input_path,
                '-c:v', 'copy',  # 视频直接复制
                '-af', f'volume={factor}',
                '-c:a', 'aac',  # 重新编码音频
                '-threads', '0',
                '-y',
                output_path
            ]
            
            if sys.platform == 'win32':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, 
                                       startupinfo=startupinfo, encoding='utf-8', errors='ignore')
            else:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300,
                                       encoding='utf-8', errors='ignore')
            
            if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                file_size_mb = os.path.getsize(output_path) / 1024 / 1024
                self.log(f"    ✓ 成功: {os.path.basename(output_path)} ({file_size_mb:.1f} MB)")
                return True
            else:
                self.log(f"    ✗ 失败: {result.stderr[:200] if result.stderr else '未知错误'}")
                return False
            
        except Exception as e:
            self.log(f"    ✗ 异常: {str(e)}")
            return False
    
    def batch_convert_operation(self):
        """批量格式转换"""
        self.current_operation = "convert"
        self.set_controls_state(True)
        self.progress_var.set(0)
        
        try:
            folder = self.convert_folder.get()
            output_folder = self.convert_output.get()
            target_format = self.convert_format.get()
            
            if not folder or not output_folder:
                messagebox.showerror("错误", "请选择视频文件夹和输出文件夹！")
                return
            
            os.makedirs(output_folder, exist_ok=True)
            
            video_files = self.get_video_files(folder)
            
            if not video_files:
                messagebox.showerror("错误", "文件夹中没有找到视频文件！")
                return
            
            self.log(f"\n{'='*60}")
            self.log(f"开始批量格式转换")
            self.log(f"视频数: {len(video_files)} 个")
            self.log(f"目标格式: {target_format}")
            self.log(f"{'='*60}\n")
            
            success_count = 0
            
            for idx, video_file in enumerate(video_files, 1):
                if self.check_pause_stop():
                    break
                
                video_path = os.path.join(folder, video_file)
                output_name = f"convert_{idx:03d}_{Path(video_file).stem}.{target_format}"
                output_path = os.path.join(output_folder, output_name)
                
                self.log(f"\n[{idx}/{len(video_files)}] 处理: {video_file}")
                
                if self._convert_format_ffmpeg(video_path, output_path, target_format):
                    success_count += 1
                    self.log(f"✓ 成功: {output_name}")
                else:
                    self.log(f"✗ 失败: {video_file}")
                
                self.progress_var.set((idx / len(video_files)) * 100)
                self.update_status(f"格式转换中... {idx}/{len(video_files)}")
            
            self.log(f"\n{'='*60}")
            self.log(f"完成！成功转换 {success_count}/{len(video_files)} 个视频")
            self.log(f"{'='*60}")
            
            if success_count > 0:
                messagebox.showinfo("完成", f"成功转换 {success_count} 个视频！")
            
        except Exception as e:
            messagebox.showerror("错误", f"格式转换失败: {str(e)}")
            self.log(f"✗ 错误: {str(e)}")
        finally:
            self.set_controls_state(False)
    
    def _convert_format_ffmpeg(self, input_path, output_path, target_format):
        """FFmpeg格式转换"""
        try:
            # 根据目标格式选择编码器
            if target_format == "mp4":
                video_codec = "libx264"
                audio_codec = "aac"
            elif target_format == "avi":
                video_codec = "libx264"
                audio_codec = "mp3"
            elif target_format == "mov":
                video_codec = "libx264"
                audio_codec = "aac"
            elif target_format == "mkv":
                video_codec = "libx264"
                audio_codec = "aac"
            else:
                video_codec = "libx264"
                audio_codec = "aac"
            
            cmd = [
                self.ffmpeg_path,
                '-i', input_path,
                '-c:v', video_codec,
                '-preset', 'ultrafast' if self.speed_priority.get() else 'medium',
                '-crf', '23',
                '-c:a', audio_codec,
                '-threads', '0',
                '-y',
                output_path
            ]
            
            if sys.platform == 'win32':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=600, 
                                       startupinfo=startupinfo, encoding='utf-8', errors='ignore')
            else:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=600,
                                       encoding='utf-8', errors='ignore')
            
            if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                file_size_mb = os.path.getsize(output_path) / 1024 / 1024
                self.log(f"    ✓ 成功: {os.path.basename(output_path)} ({file_size_mb:.1f} MB)")
                return True
            else:
                self.log(f"    ✗ 失败: {result.stderr[:200] if result.stderr else '未知错误'}")
                return False
            
        except Exception as e:
            self.log(f"    ✗ 异常: {str(e)}")
            return False
    
    def batch_extract_operation(self):
        """批量提取视频帧"""
        self.current_operation = "extract"
        self.set_controls_state(True)
        self.progress_var.set(0)
        
        try:
            folder = self.extract_folder.get()
            output_folder = self.extract_output.get()
            interval = float(self.extract_interval.get())
            
            if not folder or not output_folder:
                messagebox.showerror("错误", "请选择视频文件夹和输出文件夹！")
                return
            
            os.makedirs(output_folder, exist_ok=True)
            
            video_files = self.get_video_files(folder)
            
            if not video_files:
                messagebox.showerror("错误", "文件夹中没有找到视频文件！")
                return
            
            self.log(f"\n{'='*60}")
            self.log(f"开始批量提取视频帧")
            self.log(f"视频数: {len(video_files)} 个")
            self.log(f"提取间隔: {interval} 秒/帧")
            self.log(f"{'='*60}\n")
            
            total_frames = 0
            
            for idx, video_file in enumerate(video_files, 1):
                if self.check_pause_stop():
                    break
                
                video_path = os.path.join(folder, video_file)
                
                self.log(f"\n[{idx}/{len(video_files)}] 处理: {video_file}")
                
                # 为每个视频创建子文件夹
                video_name = Path(video_file).stem
                video_output_folder = os.path.join(output_folder, f"frames_{video_name}")
                os.makedirs(video_output_folder, exist_ok=True)
                
                frame_count = self._extract_frames_ffmpeg(video_path, video_output_folder, interval, video_name)
                
                if frame_count > 0:
                    total_frames += frame_count
                    self.log(f"✓ 提取 {frame_count} 帧到: {video_output_folder}")
                else:
                    self.log(f"✗ 失败: {video_file}")
                
                self.progress_var.set((idx / len(video_files)) * 100)
                self.update_status(f"提取帧中... {idx}/{len(video_files)}")
            
            self.log(f"\n{'='*60}")
            self.log(f"完成！总计提取 {total_frames} 帧")
            self.log(f"{'='*60}")
            
            if total_frames > 0:
                messagebox.showinfo("完成", f"成功提取 {total_frames} 帧！")
            
        except Exception as e:
            messagebox.showerror("错误", f"提取帧失败: {str(e)}")
            self.log(f"✗ 错误: {str(e)}")
        finally:
            self.set_controls_state(False)
    
    def _extract_frames_ffmpeg(self, input_path, output_folder, interval, video_name):
        """FFmpeg提取视频帧"""
        try:
            # 输出文件名格式: 视频名_帧序号.jpg
            output_pattern = os.path.join(output_folder, f"{video_name}_%04d.jpg")
            
            cmd = [
                self.ffmpeg_path,
                '-i', input_path,
                '-vf', f'fps=1/{interval}',
                '-q:v', '2',  # 高质量JPEG
                '-y',
                output_pattern
            ]
            
            if sys.platform == 'win32':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=600, 
                                       startupinfo=startupinfo, encoding='utf-8', errors='ignore')
            else:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=600,
                                       encoding='utf-8', errors='ignore')
            
            # 计算提取的帧数
            if result.returncode == 0:
                # 统计输出文件夹中的图片数量
                frames = [f for f in os.listdir(output_folder) if f.endswith('.jpg')]
                return len(frames)
            else:
                self.log(f"    ✗ 提取失败: {result.stderr[:200] if result.stderr else '未知错误'}")
                return 0
            
        except Exception as e:
            self.log(f"    ✗ 异常: {str(e)}")
            return 0

    # ===== 原有功能实现（包含修复）=====

    def start_merge(self):
        thread = threading.Thread(target=self.batch_merge_operation)
        thread.daemon = True
        thread.start()
        
    def start_split(self):
        thread = threading.Thread(target=self.batch_split_operation)
        thread.daemon = True
        thread.start()
        
    def start_concat(self):
        thread = threading.Thread(target=self.batch_concat_operation)
        thread.daemon = True
        thread.start()
        
    def start_pip(self):
        thread = threading.Thread(target=self.batch_pip_operation)
        thread.daemon = True
        thread.start()
        
    def start_speed(self):
        thread = threading.Thread(target=self.batch_speed_operation)
        thread.daemon = True
        thread.start()
    
    def batch_merge_operation(self):
        """批量分屏合并"""
        self.current_operation = "merge"
        self.set_controls_state(True)
        self.progress_var.set(0)
        
        try:
            folder1 = self.folder1_path.get()
            folder2 = self.folder2_path.get()
            output = self.output_path.get()
            
            if not all([folder1, folder2, output]):
                messagebox.showerror("错误", "请填写所有必填路径！")
                return
                
            os.makedirs(output, exist_ok=True)
            
            files1 = self.get_media_files(folder1)
            files2 = self.get_media_files(folder2)
            
            if not files1 or not files2:
                messagebox.showerror("错误", "至少有一个文件夹中没有找到媒体文件！")
                return
                
            self.log(f"开始分屏合并：文件夹1有 {len(files1)} 个文件，文件夹2有 {len(files2)} 个文件")
            
            image_duration = float(self.image_duration.get())
            success_count = 0
            total_pairs = min(len(files1), len(files2))
            
            for idx, (file1, file2) in enumerate(zip(files1, files2), 1):
                if self.check_pause_stop():
                    break
                    
                try:
                    self.update_status(f"处理 {idx}/{total_pairs}")
                    self.log(f"\n[{idx}/{total_pairs}] 处理: {file1} + {file2}")
                    
                    file1_path = os.path.join(folder1, file1)
                    file2_path = os.path.join(folder2, file2)
                    
                    output_name = f"merge_{idx:03d}_{Path(file1).stem}_{Path(file2).stem}.mp4"
                    output_path = os.path.join(output, output_name)
                    
                    success = self._merge_with_ffmpeg(file1_path, file2_path, output_path, image_duration)
                    
                    if success:
                        success_count += 1
                        self.log(f"✓ 成功生成: {output_name}")
                    
                    self.progress_var.set((idx / total_pairs) * 100)
                    
                except Exception as e:
                    self.log(f"✗ 处理失败: {str(e)}")
                    continue
                    
            self.log(f"\n=== 全部完成！成功生成 {success_count}/{total_pairs} 个视频，保存在: {output} ===")
            messagebox.showinfo("完成", f"成功生成 {success_count} 个视频！")
            
        except Exception as e:
            messagebox.showerror("错误", f"处理过程出错: {str(e)}")
        finally:
            self.set_controls_state(False)
    
    def batch_split_operation(self):
        """批量分割视频"""
        self.current_operation = "split"
        self.set_controls_state(True)
        self.progress_var.set(0)
        
        try:
            folder = self.split_folder.get()
            output = self.split_output.get()
            audio_output = self.audio_output_path.get()
            
            if not folder or not output:
                messagebox.showerror("错误", "请选择视频文件夹和输出文件夹！")
                return
                
            if self.extract_audio.get() and not audio_output:
                messagebox.showerror("错误", "请设置音频输出文件夹！")
                return
                
            os.makedirs(output, exist_ok=True)
            if self.extract_audio.get():
                os.makedirs(audio_output, exist_ok=True)
            
            video_files = self.get_video_files(folder)
            
            if not video_files:
                messagebox.showerror("错误", "文件夹中没有找到视频文件！")
                return
            
            duration = float(self.split_duration.get())
            
            self.log(f"\n{'='*60}")
            self.log(f"开始批量分割")
            self.log(f"视频数: {len(video_files)} 个")
            self.log(f"分割时长: {duration} 秒")
            self.log(f"{'='*60}\n")
            
            total_segments = 0
            completed = 0
            
            for video_file in video_files:
                if self.check_pause_stop():
                    break
                    
                video_path = os.path.join(folder, video_file)
                results = self.process_split_task(video_path, output, audio_output, duration)
                
                for video_name, count, details in results:
                    if count > 0:
                        total_segments += count
                        success_count = sum(1 for d in details if d[1] == "成功")
                        self.log(f"\n{video_name}: {success_count}/{len(details)} 成功")
                    elif count == 0:
                        self.log(f"\n{video_name}: 跳过")
                    else:
                        self.log(f"\n{video_name}: {details}")
                
                completed += 1
                self.progress_var.set((completed / len(video_files)) * 100)
                self.update_status(f"处理中... {completed}/{len(video_files)}")
            
            self.log(f"\n{'='*60}")
            self.log(f"完成！总计: {len(video_files)} 视频, {total_segments} 片段")
            self.log(f"{'='*60}")
            
            if total_segments > 0:
                messagebox.showinfo("完成", f"成功分割 {total_segments} 个片段")
            else:
                messagebox.showwarning("警告", "没有生成任何片段")
            
        except Exception as e:
            messagebox.showerror("错误", str(e))
        finally:
            self.set_controls_state(False)
    
    def process_split_task(self, video_path, output_folder, audio_folder, segment_duration):
        """处理单个视频的分割任务"""
        try:
            video_name = Path(video_path).stem
            results = []
            
            self.log(f"\n=== 处理: {video_name} ===")
            
            # 检查文件
            if not os.path.exists(video_path):
                self.log(f"✗ 文件不存在: {video_path}")
                return [(video_name, -1, "文件不存在")]
            
            # 获取时长
            duration = self.get_video_info_safe(video_path)
            if duration == 0:
                return [(video_name, 0, "无法读取时长")]
            
            # 计算分割
            if duration < segment_duration:
                if self.keep_remainder.get():
                    num_segments = 1
                else:
                    return [(video_name, 0, "时长不足")]
            else:
                num_segments = int(duration // segment_duration)
                remainder = duration % segment_duration
                if self.keep_remainder.get() and remainder > 0.5:
                    num_segments += 1
            
            self.log(f"将分割为 {num_segments} 个片段")
            
            # 分割
            for i in range(num_segments):
                if self.check_pause_stop():
                    break
                    
                start = i * segment_duration
                end = min(start + segment_duration, duration)
                seg_duration = end - start
                
                output_name = f"{video_name}_part{i+1:03d}.mp4"
                output_path = os.path.join(output_folder, output_name)
                
                self.log(f"  片段 {i+1}/{num_segments}: {start:.1f}-{end:.1f}s ({seg_duration:.1f}s)")
                
                success = self.split_video_ffmpeg(video_path, output_path, start, seg_duration)
                
                if success:
                    results.append((output_name, "成功"))
                    
                    if self.extract_audio.get():
                        audio_name = f"{video_name}_part{i+1:03d}.mp3"
                        audio_path = os.path.join(audio_folder, audio_name)
                        self.extract_audio_ffmpeg(video_path, audio_path, start, seg_duration)
                else:
                    results.append((output_name, "失败"))
            
            return [(video_name, len(results), results)]
            
        except Exception as e:
            self.log(f"✗ 异常: {str(e)}")
            return [(video_name, -1, str(e))]
    
    def split_video_ffmpeg(self, input_path, output_path, start_time, duration):
        """视频分割"""
        try:
            # 确保输出目录存在
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            cmd = [
                self.ffmpeg_path,
                '-ss', str(start_time),
                '-i', input_path,
                '-t', str(duration),
                '-c:v', 'libx264',
                '-preset', 'ultrafast' if self.speed_priority.get() else 'medium',
                '-crf', '23',
                '-c:a', 'aac',
                '-threads', '0',
                '-y',
                output_path
            ]
            
            self.log(f"    执行: ffmpeg -ss {start_time} -i ... -t {duration}")
            
            if sys.platform == 'win32':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, 
                                       startupinfo=startupinfo, encoding='utf-8', errors='ignore')
            else:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300,
                                       encoding='utf-8', errors='ignore')
            
            if result.returncode != 0:
                error_msg = result.stderr[:200] if result.stderr else "未知错误"
                self.log(f"    ✗ FFmpeg错误: {error_msg}")
                return False
                
            # 验证输出文件
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                file_size_mb = os.path.getsize(output_path) / 1024 / 1024
                self.log(f"    ✓ 成功: {os.path.basename(output_path)} ({file_size_mb:.1f} MB)")
                return True
            else:
                self.log(f"    ✗ 输出文件不存在")
                return False
            
        except Exception as e:
            self.log(f"    ✗ 异常: {str(e)}")
            return False
    
    def extract_audio_ffmpeg(self, input_path, output_path, start_time, duration):
        """提取音频"""
        try:
            cmd = [
                self.ffmpeg_path,
                '-ss', str(start_time),
                '-i', input_path,
                '-t', str(duration),
                '-vn',
                '-c:a', 'libmp3lame',
                '-q:a', '4',
                '-y',
                output_path
            ]
            
            if sys.platform == 'win32':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, 
                                       startupinfo=startupinfo, encoding='utf-8', errors='ignore')
            else:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300,
                                       encoding='utf-8', errors='ignore')
            
            return result.returncode == 0 and os.path.exists(output_path)
            
        except:
            return False

    def _merge_with_ffmpeg(self, file1_path, file2_path, output_path, image_duration):
        """FFmpeg合并核心实现（已修复音频处理逻辑）"""
        try:
            # 检查文件
            if not os.path.exists(file1_path):
                self.log(f"✗ 文件不存在: {file1_path}")
                return False
            if not os.path.exists(file2_path):
                self.log(f"✗ 文件不存在: {file2_path}")
                return False
            
            # 判断文件类型
            ext1 = Path(file1_path).suffix.lower()
            ext2 = Path(file2_path).suffix.lower()
            
            # 如果都是视频，使用滤镜
            if ext1 in self.video_extensions and ext2 in self.video_extensions:
                self.log(f"  视频+视频模式，使用FFmpeg滤镜")
                
                # 构建视频滤镜
                filter_complex = (
                    '[0:v]scale=540:1080:force_original_aspect_ratio=decrease,pad=540:1080:(ow-iw)/2:(oh-ih)/2[v0];'
                    '[1:v]scale=540:1080:force_original_aspect_ratio=decrease,pad=540:1080:(ow-iw)/2:(oh-ih)/2[v1];'
                    '[v0][v1]hstack=inputs=2[v];'
                )
                
                # 音频处理 - 根据用户选择决定使用哪个音频源（修复部分）
                audio_source = self.audio_source.get()
                filter_complex_audio = ''
                map_audio = []
                
                if audio_source == "folder1":
                    # 只使用第一个输入的音频 [0:a]
                    filter_complex_audio = '[0:a]anull[a]'
                    map_audio = ['-map', '[a]', '-c:a', 'aac']
                elif audio_source == "folder2":
                    # 只使用第二个输入的音频 [1:a]
                    filter_complex_audio = '[1:a]anull[a]'
                    map_audio = ['-map', '[a]', '-c:a', 'aac']
                else:  # "none"
                    map_audio = ['-an']  # 禁用音频输出
                
                # 完整的滤镜
                filter_complex += filter_complex_audio
                
                # 输出时长
                duration1 = self.get_video_info_safe(file1_path)
                duration2 = self.get_video_info_safe(file2_path)
                min_duration = min(duration1, duration2) if duration1 > 0 and duration2 > 0 else 0
                
                # 构建最终命令
                cmd = [
                    self.ffmpeg_path,
                    '-i', file1_path,
                    '-i', file2_path,
                    '-filter_complex', filter_complex,
                    '-map', '[v]'] + map_audio + [
                    '-c:v', 'libx264',
                    '-preset', 'ultrafast' if self.speed_priority.get() else 'medium',
                    '-crf', '23',
                    '-threads', '0',
                    '-y',
                    output_path
                ]
                
                if min_duration > 0:
                    cmd += ['-t', str(min_duration)]
                
                self.log(f"    执行FFmpeg复杂滤镜...")
                
            else:
                # 包含图片，使用MoviePy备用方案
                self.log(f"  包含图片，使用MoviePy方案")
                return self._merge_with_moviepy_safe(file1_path, file2_path, output_path, image_duration)
            
            # 执行FFmpeg
            if sys.platform == 'win32':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=600, 
                                       startupinfo=startupinfo, encoding='utf-8', errors='ignore')
            else:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=600,
                                       encoding='utf-8', errors='ignore')
            
            if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                file_size_mb = os.path.getsize(output_path) / 1024 / 1024
                self.log(f"    ✓ 成功: {os.path.basename(output_path)} ({file_size_mb:.1f} MB)")
                return True
            else:
                self.log(f"    ✗ 失败: {result.stderr[:200] if result.stderr else '未知错误'}")
                return False
            
        except Exception as e:
            self.log(f"    ✗ 异常: {str(e)}")
            return False
    
    def _merge_with_moviepy_safe(self, file1_path, file2_path, output_path, image_duration):
        """MoviePy备用方案"""
        try:
            from moviepy.editor import VideoFileClip, ImageClip, clips_array
            
            ext1 = Path(file1_path).suffix.lower()
            ext2 = Path(file2_path).suffix.lower()
            
            # 加载文件
            if ext1 in self.image_extensions:
                img = Image.open(file1_path)
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                clip1 = ImageClip(np.array(img), duration=image_duration)
            else:
                clip1 = VideoFileClip(file1_path)
            
            if ext2 in self.image_extensions:
                img = Image.open(file2_path)
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                clip2 = ImageClip(np.array(img), duration=image_duration)
            else:
                clip2 = VideoFileClip(file2_path)
            
            # 统一时长
            min_dur = min(clip1.duration, clip2.duration)
            clip1 = clip1.subclip(0, min_dur)
            clip2 = clip2.subclip(0, min_dur)
            
            # 调整大小和合并
            clip1 = clip1.resize(height=1080, width=540)
            clip2 = clip2.resize(height=1080, width=540)
            final = clips_array([[clip1, clip2]])
            
            # 处理音频（MoviePy方案已正确处理）
            if self.audio_source.get() != "none":
                if self.audio_source.get() == "folder1" and ext1 not in self.image_extensions:
                    final = final.set_audio(clip1.audio)
                elif ext2 not in self.image_extensions:
                    final = final.set_audio(clip2.audio)
            
            # 导出
            final.write_videofile(output_path, codec='libx264', preset='ultrafast', logger=None)
            
            # 清理
            clip1.close()
            clip2.close()
            final.close()
            
            self.log(f"    ✓ 成功: {os.path.basename(output_path)}")
            return True
            
        except Exception as e:
            self.log(f"    ✗ 失败: {str(e)}")
            return False
    
    def batch_concat_operation(self):
        """批量转场拼接"""
        self.current_operation = "concat"
        self.set_controls_state(True)
        self.progress_var.set(0)
        
        try:
            # 获取所有非空文件夹
            folders = [f.get() for f in self.concat_folders if f.get().strip()]
            output = self.concat_output.get()
            
            if not folders or not output:
                messagebox.showerror("错误", "请选择至少1个文件夹和输出文件夹！")
                return
                
            os.makedirs(output, exist_ok=True)
            
            # 获取所有视频文件
            all_videos = []
            for i, folder in enumerate(folders):
                videos = self.get_video_files(folder)
                all_videos.append(videos)
            
            min_count = min(len(videos) for videos in all_videos) if all_videos else 0
            
            if min_count == 0:
                messagebox.showerror("错误", "有文件夹中没有找到视频文件！")
                return
                
            self.log(f"\n{'='*60}")
            self.log(f"开始批量转场拼接")
            self.log(f"文件夹数: {len(folders)} 个")
            self.log(f"每组视频数: {min_count} 个")
            self.log(f"{'='*60}\n")
            
            success_count = 0
            
            for i in range(min_count):
                if self.check_pause_stop():
                    break
                    
                # 收集当前组的视频
                group_videos = []
                for j, videos in enumerate(all_videos):
                    group_videos.append(os.path.join(folders[j], videos[i]))
                
                output_name = f"concat_{i+1:03d}.mp4"
                output_path = os.path.join(output, output_name)
                
                self.log(f"\n[{i+1}/{min_count}] 拼接 {len(group_videos)} 个视频")
                
                if self._concat_with_transition(group_videos, output_path):
                    success_count += 1
                    self.log(f"✓ 成功: {output_name}")
                else:
                    self.log(f"✗ 失败")
                
                self.progress_var.set((i + 1) / min_count * 100)
                self.update_status(f"转场拼接中... {i+1}/{min_count}")
            
            self.log(f"\n{'='*60}")
            self.log(f"完成！成功生成 {success_count}/{min_count} 个视频")
            self.log(f"{'='*60}")
            
            if success_count > 0:
                messagebox.showinfo("完成", f"成功生成 {success_count} 个拼接视频！")
            
        except Exception as e:
            messagebox.showerror("错误", f"转场拼接失败: {str(e)}")
            self.log(f"✗ 错误: {str(e)}")
        finally:
            self.set_controls_state(False)
    
    def _concat_with_transition(self, video_paths, output_path):
        """转场拼接实现（简化版）"""
        try:
            if len(video_paths) == 1:
                # 只有一个视频，直接复制
                shutil.copy2(video_paths[0], output_path)
                return True
            
            # 创建临时文件列表
            temp_list = os.path.join(os.path.dirname(output_path), f"temp_list_{os.getpid()}.txt")
            with open(temp_list, 'w', encoding='utf-8') as f:
                for video in video_paths:
                    f.write(f"file '{os.path.abspath(video)}'\n")
            
            # 使用concat滤镜
            cmd = [
                self.ffmpeg_path,
                '-f', 'concat',
                '-safe', '0',
                '-i', temp_list,
                '-c:v', 'libx264',
                '-preset', 'ultrafast' if self.speed_priority.get() else 'medium',
                '-crf', '23',
                '-c:a', 'aac',
                '-threads', '0',
                '-y',
                output_path
            ]
            
            if sys.platform == 'win32':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=900, 
                                       startupinfo=startupinfo, encoding='utf-8', errors='ignore')
            else:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=900,
                                       encoding='utf-8', errors='ignore')
            
            # 清理临时文件
            if os.path.exists(temp_list):
                os.remove(temp_list)
            
            if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                file_size_mb = os.path.getsize(output_path) / 1024 / 1024
                self.log(f"    ✓ 拼接成功: {os.path.basename(output_path)} ({file_size_mb:.1f} MB)")
                return True
            else:
                self.log(f"    ✗ 拼接失败: {result.stderr[:200] if result.stderr else '未知错误'}")
                return False
            
        except Exception as e:
            self.log(f"    ✗ 拼接异常: {str(e)}")
            return False
    
    def batch_pip_operation(self):
        """批量画中画合成"""
        self.current_operation = "pip"
        self.set_controls_state(True)
        self.progress_var.set(0)
        
        try:
            bg_folder = self.pip_bg_folder.get()
            fg_folder = self.pip_fg_folder.get()
            output = self.pip_output.get()
            position = self.pip_position.get()
            scale = float(self.pip_scale.get())
            
            if not all([bg_folder, fg_folder, output]):
                messagebox.showerror("错误", "请选择所有必填文件夹！")
                return
                
            os.makedirs(output, exist_ok=True)
            
            bg_files = self.get_media_files(bg_folder)
            fg_files = self.get_media_files(fg_folder)
            
            if not bg_files or not fg_files:
                messagebox.showerror("错误", "有文件夹中没有找到媒体文件！")
                return
                
            min_count = min(len(bg_files), len(fg_files))
            
            self.log(f"\n{'='*60}")
            self.log(f"开始批量画中画合成")
            self.log(f"视频对数: {min_count} 对")
            self.log(f"{'='*60}\n")
            
            success_count = 0
            
            for i in range(min_count):
                if self.check_pause_stop():
                    break
                    
                bg_path = os.path.join(bg_folder, bg_files[i])
                fg_path = os.path.join(fg_folder, fg_files[i])
                
                output_name = f"pip_{i+1:03d}_{Path(bg_files[i]).stem}.mp4"
                output_path = os.path.join(output, output_name)
                
                self.log(f"\n[{i+1}/{min_count}] 处理: {bg_files[i]} + {fg_files[i]}")
                
                if self._pip_ffmpeg(bg_path, fg_path, output_path, position, scale):
                    success_count += 1
                    self.log(f"✓ 成功: {output_name}")
                else:
                    self.log(f"✗ 失败")
                
                self.progress_var.set((i + 1) / min_count * 100)
                self.update_status(f"画中画合成中... {i+1}/{min_count}")
            
            self.log(f"\n{'='*60}")
            self.log(f"完成！成功生成 {success_count}/{min_count} 个视频")
            self.log(f"{'='*60}")
            
            if success_count > 0:
                messagebox.showinfo("完成", f"成功生成 {success_count} 个画中画视频！")
            
        except Exception as e:
            messagebox.showerror("错误", f"画中画合成失败: {str(e)}")
            self.log(f"✗ 错误: {str(e)}")
        finally:
            self.set_controls_state(False)
    
    def _pip_ffmpeg(self, bg_path, fg_path, output_path, position, scale):
        """画中画实现"""
        try:
            # 获取背景视频分辨率
            bg_w, bg_h = self.get_video_resolution(bg_path)
            
            # 计算前景尺寸
            fg_w = int(bg_w * scale)
            fg_h = int(bg_h * scale)
            
            # 计算位置
            margin = int(bg_w * 0.02)  # 2%边距
            if position == "top_left":
                x = margin
                y = margin
            elif position == "top_right":
                x = bg_w - fg_w - margin
                y = margin
            elif position == "bottom_left":
                x = margin
                y = bg_h - fg_h - margin
            else:  # bottom_right
                x = bg_w - fg_w - margin
                y = bg_h - fg_h - margin
            
            # 构建滤镜
            filter_complex = (
                f"[1:v]scale={fg_w}:{fg_h}[fg];"
                f"[0:v][fg]overlay=x={x}:y={y}[v]"
            )
            
            cmd = [
                self.ffmpeg_path,
                '-i', bg_path,
                '-i', fg_path,
                '-filter_complex', filter_complex,
                '-map', '[v]',
                '-map', '0:a',  # 使用背景音频
                '-c:v', 'libx264',
                '-preset', 'ultrafast' if self.speed_priority.get() else 'medium',
                '-crf', '23',
                '-c:a', 'copy',
                '-threads', '0',
                '-y',
                output_path
            ]
            
            if sys.platform == 'win32':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=600, 
                                       startupinfo=startupinfo, encoding='utf-8', errors='ignore')
            else:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=600,
                                       encoding='utf-8', errors='ignore')
            
            if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                file_size_mb = os.path.getsize(output_path) / 1024 / 1024
                self.log(f"    ✓ 画中画成功: {os.path.basename(output_path)} ({file_size_mb:.1f} MB)")
                return True
            else:
                self.log(f"    ✗ 画中画失败: {result.stderr[:200] if result.stderr else '未知错误'}")
                return False
            
        except Exception as e:
            self.log(f"    ✗ 画中画异常: {str(e)}")
            return False
    
    def batch_speed_operation(self):
        """批量变速/倒放"""
        self.current_operation = "speed"
        self.set_controls_state(True)
        self.progress_var.set(0)
        
        try:
            folder = self.speed_folder.get()
            output = self.speed_output.get()
            speed_factor = float(self.speed_factor.get())
            reverse = self.speed_reverse.get()
            
            if not folder or not output:
                messagebox.showerror("错误", "请选择视频文件夹和输出文件夹！")
                return
                
            os.makedirs(output, exist_ok=True)
            
            video_files = self.get_video_files(folder)
            
            if not video_files:
                messagebox.showerror("错误", "文件夹中没有找到视频文件！")
                return
            
            self.log(f"\n{'='*60}")
            self.log(f"开始批量变速/倒放")
            self.log(f"视频数: {len(video_files)} 个")
            self.log(f"速度倍数: {speed_factor}x, 倒放: {'是' if reverse else '否'}")
            self.log(f"{'='*60}\n")
            
            success_count = 0
            
            for idx, video_file in enumerate(video_files, 1):
                if self.check_pause_stop():
                    break
                
                video_path = os.path.join(folder, video_file)
                suffix = "reverse" if reverse else f"{speed_factor}x"
                output_name = f"speed_{idx:03d}_{suffix}_{Path(video_file).stem}.mp4"
                output_path = os.path.join(output, output_name)
                
                self.log(f"\n[{idx}/{len(video_files)}] 处理: {video_file}")
                
                if self._speed_change_ffmpeg(video_path, output_path, speed_factor, reverse):
                    success_count += 1
                    self.log(f"✓ 成功: {output_name}")
                else:
                    self.log(f"✗ 失败")
                
                self.progress_var.set((idx / len(video_files)) * 100)
                self.update_status(f"变速中... {idx}/{len(video_files)}")
            
            self.log(f"\n{'='*60}")
            self.log(f"完成！成功处理 {success_count}/{len(video_files)} 个视频")
            self.log(f"{'='*60}")
            
            if success_count > 0:
                messagebox.showinfo("完成", f"成功处理 {success_count} 个视频！")
            
        except Exception as e:
            messagebox.showerror("错误", f"变速处理失败: {str(e)}")
            self.log(f"✗ 错误: {str(e)}")
        finally:
            self.set_controls_state(False)
    
    def _speed_change_ffmpeg(self, input_path, output_path, speed_factor, reverse):
        """变速/倒放实现"""
        try:
            # 构建视频滤镜
            vf_filters = []
            
            # 变速滤镜
            if speed_factor != 1.0:
                vf_filters.append(f"setpts=PTS/{speed_factor}")
            
            # 倒放滤镜
            if reverse:
                vf_filters.append("reverse")
            
            # 音频滤镜
            af_filters = []
            if speed_factor != 1.0:
                # 音频变速（保持音调）
                af_filters.append(f"atempo={speed_factor}")
            
            vf_str = ','.join(vf_filters) if vf_filters else 'null'
            af_str = ','.join(af_filters) if af_filters else 'null'
            
            cmd = [
                self.ffmpeg_path,
                '-i', input_path,
                '-vf', vf_str,
                '-af', af_str,
                '-c:v', 'libx264',
                '-preset', 'ultrafast' if self.speed_priority.get() else 'medium',
                '-crf', '23',
                '-c:a', 'aac',
                '-threads', '0',
                '-y',
                output_path
            ]
            
            if sys.platform == 'win32':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=600, 
                                       startupinfo=startupinfo, encoding='utf-8', errors='ignore')
            else:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=600,
                                       encoding='utf-8', errors='ignore')
            
            if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                file_size_mb = os.path.getsize(output_path) / 1024 / 1024
                self.log(f"    ✓ 变速成功: {os.path.basename(output_path)} ({file_size_mb:.1f} MB)")
                return True
            else:
                self.log(f"    ✗ 变速失败: {result.stderr[:200] if result.stderr else '未知错误'}")
                return False
            
        except Exception as e:
            self.log(f"    ✗ 变速异常: {str(e)}")
            return False


def main():
    root = tk.Tk()
    style = ttk.Style()
    style.configure('Accent.TButton', font=('Arial', 10, 'bold'))
    
    app = FFmpegVideoEditorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()