import asyncio
import base64
import os
import sys
import json
import time
import gc
import subprocess
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import numpy as np
from PIL import Image, ImageTk
import shutil
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding as crypto_padding
from cryptography.hazmat.backends import default_backend
import speech_tab
import settings_window

VERSION = "v9.0.0"
APP_TITLE = f"中巨量KK智能剪辑工具 {VERSION}"

def _resource_path(relative_path: str) -> str:
    """获取资源文件的绝对路径，兼容开发环境和 PyInstaller 打包后环境。"""
    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative_path)

VERSION_INFO = f"""\
版本：{VERSION}
平台：Windows

更新日志（只记录大功能迭代）：
• v9.2  增加视频压缩功能
• v9.1  增加批量裁剪图片功能
• v9.0  增加授权码登录
• v8.4  视频添加标题支持自定义字体颜色
• v8.3  增加批量视频裁剪尺寸功能
• v8.2  增加视频添加标题功能
• v8.1  增加批量填充音乐功能优化
• v1-8  基础合并/分割功能等
"""


# ─────────────────────────────────────────────────────────────
# 授权管理器
# ─────────────────────────────────────────────────────────────

class LicenseManager:
    """授权管理器 - 授权码验证"""

    def __init__(self, app_name="REDACTED-SEED"):
        self.app_name = app_name
        self.secret_key = self._generate_key()
        app_data = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "vek")
        os.makedirs(app_data, exist_ok=True)
        self.license_file = os.path.join(app_data, ".vek_li")

    def _generate_key(self):
        key_base = hashlib.sha256(self.app_name.encode()).digest()
        return key_base[:32]

    def _encrypt_data(self, data):
        try:
            iv = os.urandom(16)
            cipher = Cipher(algorithms.AES(self.secret_key), modes.CBC(iv), backend=default_backend())
            encryptor = cipher.encryptor()
            padder = crypto_padding.PKCS7(128).padder()
            padded_data = padder.update(data.encode()) + padder.finalize()
            encrypted = encryptor.update(padded_data) + encryptor.finalize()
            return base64.b64encode(iv + encrypted).decode()
        except Exception:
            return None

    def _decrypt_data(self, encrypted_data):
        try:
            decoded = base64.b64decode(encrypted_data.encode())
            iv = decoded[:16]
            encrypted = decoded[16:]
            cipher = Cipher(algorithms.AES(self.secret_key), modes.CBC(iv), backend=default_backend())
            decryptor = cipher.decryptor()
            padded_data = decryptor.update(encrypted) + decryptor.finalize()
            unpadder = crypto_padding.PKCS7(128).unpadder()
            data = unpadder.update(padded_data) + unpadder.finalize()
            return data.decode()
        except Exception:
            return None

    def verify_auth_code(self, auth_code):
        try:
            decrypted_data = self._decrypt_data(auth_code)
            if not decrypted_data:
                return False, "授权码无效或损坏，请联系管理员"
            license_info = json.loads(decrypted_data)
            expire_date_str = license_info.get("expire_date")
            expire_date = datetime.strptime(expire_date_str, "%Y-%m-%d %H:%M:%S")
            now = datetime.now()
            create_date_str = license_info.get("create_date")
            if create_date_str:
                create_date = datetime.strptime(create_date_str, "%Y-%m-%d %H:%M:%S")
                if now < create_date:
                    return False, "系统时间异常，请检查系统时间设置"
            if now > expire_date:
                return False, f"授权码已过期（过期时间：{expire_date_str}）"
            days_left = (expire_date - now).days
            return True, f"授权验证成功，剩余 {days_left} 天"
        except Exception as e:
            return False, f"授权码验证失败: {str(e)}"

    def save_license(self, auth_code):
        try:
            encrypted = self._encrypt_data(auth_code)
            with open(self.license_file, 'w') as f:
                f.write(encrypted)
            return True
        except Exception:
            return False

    def load_license(self):
        if not os.path.exists(self.license_file):
            return None
        try:
            with open(self.license_file, 'r') as f:
                encrypted = f.read()
            return self._decrypt_data(encrypted)
        except Exception:
            return None


def show_license_dialog(root):
    """显示授权验证对话框，返回 True 表示授权通过"""
    lm = LicenseManager()

    saved_code = lm.load_license()
    if saved_code:
        ok, msg = lm.verify_auth_code(saved_code)
        if ok:
            return True

    result = {"authorized": False}

    dialog = tk.Toplevel(root)
    dialog.title("软件授权验证")
    dialog.geometry("480x260")
    dialog.resizable(False, False)
    dialog.transient(root)
    dialog.grab_set()

    icon_path = _resource_path(os.path.join('assets', 'logo.ico'))
    if os.path.exists(icon_path):
        dialog.iconbitmap(icon_path)

    dialog.protocol("WM_DELETE_WINDOW", lambda: (result.update(authorized=False), dialog.destroy()))

    frame = ttk.Frame(dialog, padding=20)
    frame.pack(fill='both', expand=True)

    ttk.Label(frame, text="请输入授权码", font=('Microsoft YaHei', 14, 'bold')).pack(pady=(0, 5))
    ttk.Label(frame, text="首次使用需要输入授权码，请联系管理员获取", foreground='gray').pack(pady=(0, 15))

    code_var = tk.StringVar()
    code_entry = ttk.Entry(frame, textvariable=code_var, width=50, font=('Consolas', 10))
    code_entry.pack(pady=(0, 5))

    status_label = ttk.Label(frame, text="", foreground='red')
    status_label.pack(pady=(0, 10))

    def do_verify():
        code = code_var.get().strip()
        if not code:
            status_label.config(text="请输入授权码", foreground='red')
            return
        ok, msg = lm.verify_auth_code(code)
        if ok:
            lm.save_license(code)
            result["authorized"] = True
            status_label.config(text=msg, foreground='green')
            dialog.after(600, dialog.destroy)
        else:
            status_label.config(text=msg, foreground='red')

    btn_frame = ttk.Frame(frame)
    btn_frame.pack(pady=(5, 0))
    ttk.Button(btn_frame, text="验证授权", command=do_verify, style='Accent.TButton').pack(side='left', padx=5)
    ttk.Button(btn_frame, text="退出", command=lambda: (result.update(authorized=False), dialog.destroy())).pack(side='left', padx=5)

    code_entry.focus_set()
    code_entry.bind('<Return>', lambda e: do_verify())

    root.wait_window(dialog)
    return result["authorized"]


# ─────────────────────────────────────────────────────────────
# MCP 异步调用（模块级，通过 asyncio.run() 在 daemon thread 中使用）
# ─────────────────────────────────────────────────────────────

async def _mcp_separate(audio_path: str, mcp_url: str):
    """Demucs 人声分离。返回 (vocals_bytes, no_vocals_bytes)。"""
    from fastmcp import Client
    audio_b64 = base64.b64encode(open(audio_path, "rb").read()).decode()
    async with Client(mcp_url) as client:
        task_id = (await client.call_tool(
            "demucs_service_separate_audio",
            {"audio_bytes": audio_b64, "model": "htdemucs", "two_stems": True},
        )).data

        elapsed = 0.0
        while elapsed < 600:
            info = (await client.call_tool(
                "demucs_service_query_task", {"task_id": task_id}
            )).data
            if info.get("status") == "completed":
                break
            if info.get("status") == "failed":
                raise RuntimeError(f"Demucs 失败: {info.get('error')}")
            await asyncio.sleep(5)
            elapsed += 5
        else:
            raise TimeoutError("Demucs 超时（600s）")

        vocals_raw = (await client.call_tool(
            "demucs_service_get_result", {"task_id": task_id, "stem": "vocals"}
        )).data
        no_vocals_raw = (await client.call_tool(
            "demucs_service_get_result", {"task_id": task_id, "stem": "no_vocals"}
        )).data

    def _to_bytes(v):
        if isinstance(v, bytes):
            return v
        return base64.b64decode(v)

    return _to_bytes(vocals_raw), _to_bytes(no_vocals_raw)


async def _mcp_transcribe(audio_path: str, mcp_url: str) -> list:
    """Whisper 转录。返回 segments 列表 [{"start", "end", "text"}, ...]。"""
    from fastmcp import Client
    audio_b64 = base64.b64encode(open(audio_path, "rb").read()).decode()
    async with Client(mcp_url) as client:
        task_id = (await client.call_tool(
            "whisper_transcribe_audio",
            {"audio_bytes": audio_b64, "language": None},
        )).data

        elapsed = 0.0
        while elapsed < 600:
            info = (await client.call_tool(
                "whisper_query_task", {"task_id": task_id}
            )).data
            if info.get("status") == "completed":
                break
            if info.get("status") == "failed":
                raise RuntimeError(f"Whisper 失败: {info.get('error')}")
            await asyncio.sleep(3)
            elapsed += 3
        else:
            raise TimeoutError("Whisper 超时（600s）")

        result = (await client.call_tool(
            "whisper_get_result", {"task_id": task_id}
        )).data

    return result.get("segments", [])


async def _mcp_tts_batch(texts: list, ref_voice_path: str, mcp_url: str) -> list:
    """TTS 批量合成。返回 wav_bytes 列表，顺序与 texts 一致。"""
    from fastmcp import Client
    prompt_b64 = base64.b64encode(open(ref_voice_path, "rb").read()).decode()
    async with Client(mcp_url) as client:
        task_id = (await client.call_tool(
            "tts_generate_voice_batch",
            {"texts": texts, "prompt_voice_bytes_list": prompt_b64},
        )).data

        elapsed = 0.0
        info = {}
        while elapsed < 600:
            info = (await client.call_tool(
                "tts_query_task", {"task_id": task_id}
            )).data
            if info.get("status") == "completed":
                break
            if info.get("status") == "failed":
                raise RuntimeError(f"TTS 失败: {info.get('error')}")
            await asyncio.sleep(5)
            elapsed += 5
        else:
            raise TimeoutError("TTS 超时（600s）")

        count = info.get("result", {}).get("count", len(texts))
        wav_list = []
        for i in range(count):
            wav_b64 = (await client.call_tool(
                "tts_get_result_batch_item",
                {"task_id": task_id, "index": i},
            )).data
            wav_list.append(base64.b64decode(wav_b64) if isinstance(wav_b64, str) else wav_b64)

    return wav_list

class FFmpegVideoEditorApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("900x850")
        icon_path = _resource_path(os.path.join('assets', 'logo.ico'))
        if os.path.exists(icon_path):
            self.root.iconbitmap(icon_path)
        
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
        self.concat_folder_widgets = []  # track dynamic UI rows
        self.concat_output = tk.StringVar()
        self.concat_transition = tk.DoubleVar(value=0.5)
        self.concat_transition_type = tk.StringVar(value='淡入淡出-fade')
        
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
        
        # 填充音乐
        self.music_video_folder = tk.StringVar()
        self.music_audio_folder = tk.StringVar()
        self.music_output_folder = tk.StringVar()
        self.music_keep_original_audio = tk.BooleanVar(value=False)

        # 视频添加标题
        self.title_video_folder = tk.StringVar()
        self.title_output_folder = tk.StringVar()
        self.title_font = tk.StringVar()
        self.title_fontsize = tk.StringVar(value="5")
        self.title_fontsize_unit = tk.StringVar(value="percent")  # "percent" 或 "px"
        self.title_y_percent = tk.StringVar(value="8")
        self.title_fontcolor = tk.StringVar(value="#ffffff")
        self.title_text = tk.StringVar()
        self.title_text_mode = tk.StringVar(value="fixed")  # "fixed" 或 "txt"
        self.title_txt_file = tk.StringVar()

        # 批量裁剪比例
        self.crop_video_folder = tk.StringVar()
        self.crop_output_folder = tk.StringVar()
        self.crop_ratio = tk.StringVar(value="9:16")
        self.crop_mode = tk.StringVar(value="video")  # "video" 或 "image"

        # 视频配音变量
        self.speech_video_folder = tk.StringVar()
        self.speech_text_folder = tk.StringVar()
        self.speech_ref_voice_folder = tk.StringVar()
        self.speech_output_folder = tk.StringVar()
        self.mcp_url = tk.StringVar(value="http://localhost:8400/mcp")
        self.speech_keep_audio = tk.BooleanVar(value=False)

        # 视频翻译变量
        self.translate_folder = tk.StringVar()
        self.translate_output = tk.StringVar()
        self.translate_target_lang = tk.StringVar(value="zh")

        # LLM 翻译配置
        self.llm_api_base = tk.StringVar(value="https://api.openai.com/v1")
        self.llm_api_key = tk.StringVar()
        self.llm_model = tk.StringVar(value="gpt-4o")

        # 调试
        self.verbose_log = tk.BooleanVar(value=False)

        # 性能与稳定性
        self.thread_count = tk.StringVar(value="1")
        self.speed_priority = tk.BooleanVar(value=True)
        self.compress_video = tk.BooleanVar(value=False)
        self.bitrate = tk.StringVar(value="2M")

        # 支持的文件类型
        self.video_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm'}
        self.image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff'}
        self.audio_extensions = {'.mp3', '.wav', '.aac', '.flac', '.ogg', '.wma', '.m4a'}
        self.all_extensions = self.video_extensions | self.image_extensions
        
        settings_window.load_settings(self)
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
        # ttk.Label(status_frame, text=f"FFmpeg路径: {self.ffmpeg_path}", foreground='green').pack(side='left')
        ttk.Button(status_frame, text="设置", command=lambda: settings_window.open_settings(self)).pack(side='right', padx=5)
        ttk.Button(status_frame, text="版本说明", command=self._show_version_info).pack(side='right', padx=5)
        # ttk.Button(status_frame, text="测试FFmpeg", command=self.test_ffmpeg).pack(side='right', padx=5)
        
        # 标题（logo + 文字）
        title_frame = ttk.Frame(self.root)
        title_frame.pack(pady=10)
        logo_path = _resource_path(os.path.join('assets', 'logo.png'))
        if os.path.exists(logo_path):
            img = Image.open(logo_path).resize((36, 36), Image.LANCZOS)
            self._title_logo = ImageTk.PhotoImage(img)
            ttk.Label(title_frame, image=self._title_logo).pack(side='left', padx=(0, 8))
        ttk.Label(title_frame, text=APP_TITLE, font=("Microsoft YaHei", 16, "bold")).pack(side='left')
        
        # 两行 Tab 按钮栏
        tab_bar = tk.Frame(self.root, bg='#f0f0f0')
        tab_bar.pack(fill='x', padx=10, pady=(5, 0))

        # 内容区（单一共享区域）
        content_area = tk.Frame(self.root, relief='groove', bd=2, bg='#f0f0f0')
        content_area.pack(fill='both', expand=True, padx=10, pady=(0, 5))

        self._tab_frames = {}
        self._tab_btns = {}
        self._active_tab = None

        ROW1 = [
            ("左右分屏合并", "merge"),
            ("批量分割视频", "split"),
            ("视频转场拼接", "concat"),
            ("画中画合成",   "pip"),
            ("批量变速/倒放", "speed"),
            ("批量旋转/翻转", "rotate"),
            ("批量添加水印", "watermark"),
            ("批量调整音量", "volume"),
            ("批量格式转换", "convert"),
            ("批量提取帧",   "extract"),
        ]
        # 从"填充音乐"开始放第二层，后续新增功能也加在这里
        ROW2 = [
            ("填充音乐",    "music"),
            ("视频添加标题", "title"),
            ("批量裁剪比例", "crop"),
            ("视频配音(后续开放)",    "speech"),
            ("视频翻译(后续开放)",    "translate"),
        ]
        CREATE_MAP = {
            "merge":     self.create_merge_tab,
            "split":     self.create_split_tab,
            "concat":    self.create_concat_tab,
            "pip":       self.create_pip_tab,
            "speed":     self.create_speed_tab,
            "rotate":    self.create_rotate_tab,
            "watermark": self.create_watermark_tab,
            "volume":    self.create_volume_tab,
            "convert":   self.create_convert_tab,
            "extract":   self.create_extract_tab,
            "music":     self.create_music_tab,
            "title":     self.create_title_tab,
            "crop":      self.create_crop_tab,
            "speech":    lambda f: speech_tab.create_speech_tab(self, f),
            "translate": self.create_translate_tab,
        }

        for row_tabs in [ROW1, ROW2]:
            row_frame = tk.Frame(tab_bar, bg='#f0f0f0')
            row_frame.pack(fill='x', pady=1)
            for tab_text, tab_key in row_tabs:
                frame = ttk.Frame(content_area)
                self._tab_frames[tab_key] = frame
                CREATE_MAP[tab_key](frame)
                btn = tk.Button(
                    row_frame, text=tab_text,
                    command=lambda k=tab_key: self._switch_tab(k),
                    relief='raised', bg='#e1e1e1', fg='#1a1a1a',
                    bd=1, padx=8, pady=3, cursor='hand2',
                    font=('微软雅黑', 9),
                    activebackground='#cce4f7', activeforeground='#003a6e',
                )
                btn.pack(side='left', padx=2, pady=2)
                self._tab_btns[tab_key] = btn

        self._switch_tab("merge")
        
        # 控制按钮
        control_frame = ttk.Frame(self.root)
        control_frame.pack(fill='x', padx=10, pady=5)
        
        self.pause_btn = ttk.Button(control_frame, text="暂停", command=self.toggle_pause, state='disabled')
        self.pause_btn.pack(side='left', padx=5)
        
        self.stop_btn = ttk.Button(control_frame, text="停止", command=self.stop_operation, state='disabled')
        self.stop_btn.pack(side='left', padx=5)

        ttk.Button(control_frame, text="导出日志", command=self.export_log).pack(side='right', padx=5)
        ttk.Button(control_frame, text="清空日志", command=self.clear_log).pack(side='right', padx=5)
        
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

    def clear_log(self):
        """清空操作日志"""
        self.log_text.delete("1.0", "end")

    def export_log(self):
        """将操作日志导出为 {时间}.log 文件"""
        content = self.log_text.get("1.0", "end").strip()
        if not content:
            messagebox.showinfo("提示", "操作日志为空，无需导出。")
            return
        folder = filedialog.askdirectory(title="选择日志导出文件夹")
        if not folder:
            return
        filename = datetime.now().strftime("%Y%m%d_%H%M%S") + f"_{VERSION}.log"
        filepath = os.path.join(folder, filename)
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            self.log(f"[日志] 已导出到：{filepath}")
        except Exception as e:
            messagebox.showerror("导出失败", f"写入文件失败：{e}")

    def _quality_args(self) -> list:
        """根据压缩视频设置返回码率控制参数列表。"""
        if self.compress_video.get():
            return ['-b:v', self.bitrate.get()]
        return ['-crf', '23']

    def _run_cmd(self, cmd: list, timeout: int = 600):
        """统一执行子进程命令，支持详细日志。返回 CompletedProcess 对象。"""
        if self.verbose_log.get():
            self.log(f"[CMD] {' '.join(str(x) for x in cmd)}")
        if sys.platform == 'win32':
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    timeout=timeout, startupinfo=si,
                                    encoding='utf-8', errors='ignore')
        else:
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    timeout=timeout, encoding='utf-8', errors='ignore')
        if self.verbose_log.get() and result.stderr:
            for line in result.stderr.splitlines():
                if line.strip():
                    self.log(f"[FFmpeg] {line}")
        return result
            
    def update_status(self, message):
        """更新状态栏"""
        self.status_var.set(message)
        self.root.update()
        
    def _show_version_info(self):
        """显示版本说明对话框"""
        win = tk.Toplevel(self.root)
        win.title("版本说明")
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()
        w, h = 420, 400
        rx = self.root.winfo_x() + (self.root.winfo_width() - w) // 2
        ry = self.root.winfo_y() + (self.root.winfo_height() - h) // 2
        win.geometry(f"{w}x{h}+{rx}+{ry}")
        icon_path = _resource_path(os.path.join('assets', 'logo.ico'))
        if os.path.exists(icon_path):
            win.iconbitmap(icon_path)
        title_frame = ttk.Frame(win)
        title_frame.pack(pady=(18, 6))
        logo_path = _resource_path(os.path.join('assets', 'logo.png'))
        if os.path.exists(logo_path):
            img = Image.open(logo_path).resize((28, 28), Image.LANCZOS)
            win._logo = ImageTk.PhotoImage(img)
            ttk.Label(title_frame, image=win._logo).pack(side='left', padx=(0, 6))
        ttk.Label(title_frame, text=APP_TITLE, font=("Microsoft YaHei", 13, "bold")).pack(side='left')
        text = tk.Text(win, wrap='word', font=("Microsoft YaHei", 10), relief='flat',
                       bg=win.cget('bg'), state='normal', height=12)
        text.insert('1.0', VERSION_INFO)
        text.config(state='disabled')
        text.pack(padx=20, fill='both', expand=True)
        ttk.Button(win, text="  关闭  ", command=win.destroy).pack(pady=10)


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
        
    def get_image_files(self, folder):
        """仅获取图片文件"""
        if not os.path.exists(folder):
            self.log(f"错误：文件夹不存在 {folder}")
            return []

        files = [f for f in os.listdir(folder) if Path(f).suffix.lower() in self.image_extensions]
        self.log(f"扫描图片文件夹: 发现 {len(files)} 个图片文件")
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
    
    def get_audio_video_files(self, folder):
        """获取视频和音频文件"""
        if not os.path.exists(folder):
            self.log(f"错误：文件夹不存在 {folder}")
            return []
        
        valid_ext = self.video_extensions | self.audio_extensions
        files = [f for f in os.listdir(folder) if Path(f).suffix.lower() in valid_ext]
        self.log(f"扫描音乐文件夹: 发现 {len(files)} 个文件")
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
                result = self._run_cmd(ffprobe_cmd, timeout=30)
                
                if result.returncode == 0 and result.stdout.strip():
                    duration = float(result.stdout.strip())
                    self.log(f"    ✓ 使用ffprobe读取: {duration:.1f}秒")
                    return duration
            
            # 备用方法: 使用ffmpeg -i
            cmd = [self.ffmpeg_path, '-i', video_path]
            result = self._run_cmd(cmd, timeout=30)
            
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
            
    def _get_video_duration_fast(self, video_path):
        """通过 ffprobe 快速获取视频时长（秒），失败时用 ffmpeg 解析，仍失败返回 0.0"""
        ffprobe_path = self.ffmpeg_path.replace('ffmpeg', 'ffprobe')
        if os.path.exists(ffprobe_path) or shutil.which(ffprobe_path):
            try:
                cmd = [
                    ffprobe_path, '-v', 'error',
                    '-show_entries', 'format=duration',
                    '-of', 'default=noprint_wrappers=1:nokey=1',
                    video_path,
                ]
                r = self._run_cmd(cmd, timeout=30)
                if r.returncode == 0 and r.stdout.strip():
                    return float(r.stdout.strip())
            except Exception:
                pass

        # ffprobe 不可用时，用 ffmpeg -i 解析 stderr
        try:
            cmd = [self.ffmpeg_path, '-i', video_path]
            r = self._run_cmd(cmd, timeout=30)
            import re
            m = re.search(r'Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)', r.stderr)
            if m:
                h, mi, s = m.group(1), m.group(2), m.group(3)
                return float(h) * 3600 + float(mi) * 60 + float(s)
        except Exception:
            pass
        return 0.0

    def get_video_resolution_fps_bak(self, video_path):
        """通过 ffmpeg stderr 解析视频分辨率和帧率（备用方案，会解码整个视频，优先使用 get_video_resolution_fps）"""
        import re
        try:
            cmd = [self.ffmpeg_path, '-i', video_path, '-f', 'null', '-']
            result = self._run_cmd(cmd, timeout=30)

            w, h, fps = 1920, 1080, 25.0
            for line in result.stderr.split('\n'):
                if 'Stream #0:0' in line and 'Video:' in line:
                    # 解析分辨率
                    res_match = re.search(r'(\d{2,5})x(\d{2,5})', line)
                    if res_match:
                        w, h = int(res_match.group(1)), int(res_match.group(2))
                    # 解析帧率（取 tbr/fps 数值）
                    fps_match = re.search(r'([\d.]+)\s*(?:fps|tbr)', line)
                    if fps_match:
                        fps = float(fps_match.group(1))
                    break
            return w, h, fps
        except:
            return 1920, 1080, 25.0

    def get_video_resolution_fps(self, video_path):
        """单次 ffprobe 同时获取视频分辨率和帧率，返回 (w, h, fps)"""
        try:
            ffprobe_path = self.ffmpeg_path.replace('ffmpeg.exe', 'ffprobe.exe').replace('ffmpeg', 'ffprobe')
            if os.path.exists(ffprobe_path) or shutil.which(ffprobe_path):
                cmd = [
                    ffprobe_path, '-v', 'error', '-select_streams', 'v:0',
                    '-show_entries', 'stream=width,height,avg_frame_rate',
                    '-of', 'default=noprint_wrappers=1:nokey=1', video_path,
                ]
                result = self._run_cmd(cmd, timeout=30)
                if result.returncode == 0:
                    lines = [l.strip() for l in result.stdout.strip().splitlines() if l.strip()]
                    if len(lines) >= 3:
                        w, h = int(lines[0]), int(lines[1])
                        fps_str = lines[2]
                        if '/' in fps_str:
                            num, den = fps_str.split('/')
                            den = int(den)
                            fps = round(int(num) / den, 6) if den else 25.0
                        else:
                            fps = float(fps_str) if fps_str else 25.0
                        return w, h, fps
        except Exception:
            pass
        # ffprobe 不可用时回退到 get_video_resolution_fps_bak
        return self.get_video_resolution_fps_bak(video_path)

    def _get_video_info(self, video_path):
        """单次 ffprobe 获取分辨率、帧率及是否有音频流，返回 (w, h, fps, has_audio)"""
        try:
            ffprobe_path = self.ffmpeg_path.replace('ffmpeg.exe', 'ffprobe.exe').replace('ffmpeg', 'ffprobe')
            cmd = [
                ffprobe_path, '-v', 'error', '-show_streams',
                '-show_entries', 'stream=codec_type,width,height,avg_frame_rate',
                '-of', 'json', video_path,
            ]
            r = self._run_cmd(cmd, timeout=30)
            if r.returncode == 0 and r.stdout.strip():
                streams = json.loads(r.stdout).get('streams', [])
                w, h, fps, has_audio = 1920, 1080, 25.0, False
                got_video = False
                for s in streams:
                    ctype = s.get('codec_type', '')
                    if ctype == 'video' and not got_video:
                        w = s.get('width', 1920)
                        h = s.get('height', 1080)
                        fps_str = s.get('avg_frame_rate', '25/1')
                        if '/' in fps_str:
                            num, den = fps_str.split('/')
                            den = int(den)
                            fps = round(int(num) / den, 6) if den else 25.0
                        else:
                            fps = float(fps_str) if fps_str else 25.0
                        got_video = True
                    elif ctype == 'audio':
                        has_audio = True
                return w, h, fps, has_audio
        except Exception:
            pass
        w, h, fps = self.get_video_resolution_fps_bak(video_path)
        return w, h, fps, True  # 解析失败时保守假设有音频

    def _switch_tab(self, key):
        """切换到指定 Tab，隐藏其余内容区"""
        for k, frame in self._tab_frames.items():
            frame.pack_forget()
        for k, btn in self._tab_btns.items():
            btn.config(bg='#e1e1e1', fg='#1a1a1a', relief='raised', font=('微软雅黑', 9))
        self._tab_frames[key].pack(fill='both', expand=True)
        self._tab_btns[key].config(bg='#0078d4', fg='#ffffff', relief='flat', font=('微软雅黑', 9, 'bold'))
        self._active_tab = key

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
        folders_lf = ttk.LabelFrame(parent, text="视频文件夹（按顺序拼接，可动态添加）", padding=5)
        folders_lf.grid(row=0, column=0, columnspan=3, sticky='ew', padx=10, pady=5)

        # 可滚动区域：Canvas + Scrollbar
        canvas = tk.Canvas(folders_lf, height=180, highlightthickness=0)
        scrollbar = ttk.Scrollbar(folders_lf, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        canvas.pack(side='top', fill='both', expand=True)

        self.concat_folders_container = ttk.Frame(canvas)
        win_id = canvas.create_window((0, 0), window=self.concat_folders_container, anchor='nw')

        def _on_inner_configure(event):
            canvas.configure(scrollregion=canvas.bbox('all'))

        def _on_canvas_resize(event):
            canvas.itemconfig(win_id, width=event.width)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')

        self.concat_folders_container.bind('<Configure>', _on_inner_configure)
        canvas.bind('<Configure>', _on_canvas_resize)
        canvas.bind('<MouseWheel>', _on_mousewheel)
        self.concat_folders_container.bind('<MouseWheel>', _on_mousewheel)

        # 初始化行（使用已有的 StringVar）
        self.concat_folder_widgets = []
        for var in self.concat_folders:
            self._add_concat_folder_row(var)

        # 添加按钮
        add_btn_frame = ttk.Frame(folders_lf)
        add_btn_frame.pack(fill='x', padx=5, pady=(4, 2))
        ttk.Button(add_btn_frame, text="＋ 添加文件夹", command=self.add_concat_folder).pack(side='left')
        ttk.Label(add_btn_frame, text="（可无限添加，至少保留1个）", foreground='gray').pack(side='left', padx=8)

        ttk.Label(parent, text="输出文件夹:").grid(row=1, column=0, sticky='w', padx=10, pady=5)
        ttk.Entry(parent, textvariable=self.concat_output, width=45).grid(row=1, column=1, padx=5)
        ttk.Button(parent, text="浏览", command=lambda: self.browse_folder(self.concat_output, True)).grid(row=1, column=2, padx=5)

        transition_frame = ttk.LabelFrame(parent, text="转场设置", padding=10)
        transition_frame.grid(row=2, column=0, columnspan=3, sticky='ew', padx=10, pady=5)

        ttk.Label(transition_frame, text="转场时长(秒):").pack(side='left', padx=5)
        ttk.Entry(transition_frame, textvariable=self.concat_transition, width=8).pack(side='left', padx=5)
        ttk.Label(transition_frame, text="(0=无转场)", foreground='gray').pack(side='left', padx=(0, 15))

        ttk.Label(transition_frame, text="转场类型:").pack(side='left', padx=5)
        transition_types = [
            '淡入淡出-fade', '淡入黑场-fadeblack', '淡入白场-fadewhite',
            '向左擦除-wipeleft', '向右擦除-wiperight', '向上擦除-wipeup', '向下擦除-wipedown',
            '向左滑动-slideleft', '向右滑动-slideright', '向上滑动-slideup', '向下滑动-slidedown',
            '向左平滑-smoothleft', '向右平滑-smoothright', '向上平滑-smoothup', '向下平滑-smoothdown',
            '圆形展开-circleopen', '圆形收缩-circleclose', '径向扫描-radial', '溶解-dissolve', '像素化-pixelize',
        ]
        ttk.Combobox(
            transition_frame, textvariable=self.concat_transition_type,
            values=transition_types, width=20, state='readonly'
        ).pack(side='left', padx=5)

        ttk.Button(parent, text="开始转场拼接", command=self.start_concat, style='Accent.TButton').grid(row=3, column=0, columnspan=3, pady=15)
        parent.columnconfigure(1, weight=1)

    def _add_concat_folder_row(self, var):
        """在转场拼接列表末尾追加一行"""
        idx = len(self.concat_folder_widgets)
        frame = ttk.Frame(self.concat_folders_container)
        frame.pack(fill='x', padx=5, pady=2)

        label = ttk.Label(frame, text=f"文件夹{idx + 1}:", width=8)
        label.pack(side='left')
        ttk.Entry(frame, textvariable=var, width=35).pack(side='left', padx=5)
        ttk.Button(frame, text="浏览", command=lambda v=var: self.browse_folder(v)).pack(side='left')
        if idx >= 5:
            ttk.Button(frame, text="✕", width=3,
                       command=lambda v=var, f=frame: self.remove_concat_folder(v, f)).pack(side='left', padx=3)
        else:
            ttk.Label(frame, width=4).pack(side='left', padx=3)

        self.concat_folder_widgets.append({'var': var, 'frame': frame, 'label': label})

    def add_concat_folder(self):
        """动态添加一个文件夹行"""
        var = tk.StringVar()
        self.concat_folders.append(var)
        self._add_concat_folder_row(var)

    def remove_concat_folder(self, var, frame):
        """删除指定的文件夹行（前5个固定，不可删除）"""
        idx = self.concat_folders.index(var)
        if idx < 5:
            messagebox.showwarning("提示", "前5个文件夹不能移除！")
            return
        self.concat_folders.pop(idx)
        self.concat_folder_widgets.pop(idx)
        frame.destroy()
        self._update_concat_folder_labels()

    def _update_concat_folder_labels(self):
        """删除行后重新编号所有标签"""
        for i, widget in enumerate(self.concat_folder_widgets):
            widget['label'].config(text=f"文件夹{i + 1}:")

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
    
    def create_music_tab(self, parent):
        """创建填充音乐标签页"""
        ttk.Label(parent, text="视频文件夹(视频原片):").grid(row=0, column=0, sticky='w', padx=10, pady=5)
        ttk.Entry(parent, textvariable=self.music_video_folder, width=45).grid(row=0, column=1, padx=5)
        ttk.Button(parent, text="浏览", command=lambda: self.browse_folder(self.music_video_folder)).grid(row=0, column=2, padx=5)
        
        ttk.Label(parent, text="音乐文件夹（视频/音乐）:").grid(row=1, column=0, sticky='w', padx=10, pady=5)
        ttk.Entry(parent, textvariable=self.music_audio_folder, width=45).grid(row=1, column=1, padx=5)
        ttk.Button(parent, text="浏览", command=lambda: self.browse_folder(self.music_audio_folder)).grid(row=1, column=2, padx=5)
        
        ttk.Label(parent, text="输出文件夹:").grid(row=2, column=0, sticky='w', padx=10, pady=5)
        ttk.Entry(parent, textvariable=self.music_output_folder, width=45).grid(row=2, column=1, padx=5)
        ttk.Button(parent, text="浏览", command=lambda: self.browse_folder(self.music_output_folder, True)).grid(row=2, column=2, padx=5)
        
        ttk.Checkbutton(parent, text="保留原生视频声音（与音乐混合）",
                        variable=self.music_keep_original_audio).grid(
            row=3, column=0, columnspan=3, sticky='w', padx=10, pady=2)
        
        ttk.Button(parent, text="开始填充音乐", command=self.start_music, style='Accent.TButton').grid(row=4, column=0, columnspan=3, pady=15)
        parent.columnconfigure(1, weight=1)

    def create_title_tab(self, parent):
        """创建视频添加标题标签页"""
        ttk.Label(parent, text="视频文件夹:").grid(row=0, column=0, sticky='w', padx=10, pady=5)
        ttk.Entry(parent, textvariable=self.title_video_folder).grid(row=0, column=1, padx=5, sticky='ew')
        ttk.Button(parent, text="浏览", command=lambda: self.browse_folder(self.title_video_folder)).grid(row=0, column=2, padx=5)

        ttk.Label(parent, text="输出文件夹:").grid(row=1, column=0, sticky='w', padx=10, pady=5)
        ttk.Entry(parent, textvariable=self.title_output_folder).grid(row=1, column=1, padx=5, sticky='ew')
        ttk.Button(parent, text="浏览", command=lambda: self.browse_folder(self.title_output_folder, True)).grid(row=1, column=2, padx=5)

        ttk.Label(parent, text="选择字体:").grid(row=2, column=0, sticky='w', padx=10, pady=5)
        font_cb = ttk.Combobox(parent, textvariable=self.title_font, state='readonly')
        font_cb.grid(row=2, column=1, padx=5, sticky='ew')
        font_cb['values'] = self._get_system_fonts()
        if font_cb['values']:
            names = font_cb['values']
            # 优先选微软雅黑，其次任意含中文名的字体，最后取第一个
            msyh = next((n for n in names if '微软雅黑' in n), None)
            chinese = next((n for n in names if self._label_has_chinese(n)), None)
            self.title_font.set(msyh or chinese or names[0])
        ttk.Button(parent, text="刷新", command=lambda: self._refresh_title_fonts(font_cb)).grid(row=2, column=2, padx=5)
        ttk.Label(parent, text="💡 如果标题文字是中文，请尽量选择含中文的系统字体，防止显示乱码（您可自己下载安装字体到系统中，安装后重启应用读取）。",
                  foreground='gray').grid(row=3, column=0, columnspan=3, sticky='w', padx=12, pady=(0, 4))

        ttk.Label(parent, text="字体大小:").grid(row=4, column=0, sticky='w', padx=10, pady=5)
        size_frame = ttk.Frame(parent)
        size_frame.grid(row=4, column=1, padx=5, sticky='w')
        ttk.Entry(size_frame, textvariable=self.title_fontsize, width=8).pack(side='left')
        _unit_px_defaults = {"percent": "5", "px": "30"}
        def _on_fontsize_unit_change(*_):
            unit = self.title_fontsize_unit.get()
            size_unit_label.config(text="% 视频高度" if unit == "percent" else "px像素")
            try:
                float(self.title_fontsize.get())
            except ValueError:
                self.title_fontsize.set(_unit_px_defaults[unit])
        ttk.Radiobutton(size_frame, text="%", variable=self.title_fontsize_unit,
                        value="percent", command=lambda: (self.title_fontsize.set("5"), _on_fontsize_unit_change())).pack(side='left', padx=(6, 2))
        ttk.Radiobutton(size_frame, text="px", variable=self.title_fontsize_unit,
                        value="px", command=lambda: (self.title_fontsize.set("30"), _on_fontsize_unit_change())).pack(side='left', padx=(0, 4))
        size_unit_label = ttk.Label(size_frame, text="% 视频高度", foreground='gray')
        size_unit_label.pack(side='left')

        ttk.Label(parent, text="文字高度位置:").grid(row=5, column=0, sticky='w', padx=10, pady=5)
        ypos_frame = ttk.Frame(parent)
        ypos_frame.grid(row=5, column=1, padx=5, sticky='w')
        ttk.Entry(ypos_frame, textvariable=self.title_y_percent, width=8).pack(side='left')
        ttk.Label(ypos_frame, text="% 距顶部（默认 8%）", foreground='gray').pack(side='left', padx=5)

        ttk.Label(parent, text="字体颜色:").grid(row=6, column=0, sticky='w', padx=10, pady=5)
        color_frame = ttk.Frame(parent)
        color_frame.grid(row=6, column=1, padx=5, sticky='w')
        color_preview_btn = tk.Button(color_frame, width=3, bg=self.title_fontcolor.get(),
                                      relief='solid', bd=1, cursor='hand2')
        color_preview_btn.pack(side='left', padx=(0, 8))

        def _pick_color():
            from tkinter import colorchooser
            result = colorchooser.askcolor(color=self.title_fontcolor.get(), title="选择字体颜色")
            if result[1]:
                self.title_fontcolor.set(result[1])
                color_preview_btn.config(bg=result[1])

        color_preview_btn.config(command=_pick_color)

        def _set_preset_color(hex_color):
            self.title_fontcolor.set(hex_color)
            color_preview_btn.config(bg=hex_color)

        for _name, _hex in [("白色", "#ffffff"), ("黄色", "#ffff00"), ("红色", "#ff3333"), ("黑色", "#000000")]:
            _hex_captured = _hex
            ttk.Button(color_frame, text=_name,
                       command=lambda h=_hex_captured: _set_preset_color(h)).pack(side='left', padx=2)

        ttk.Label(parent, text="标题来源:").grid(row=7, column=0, sticky='w', padx=10, pady=5)
        mode_frame = ttk.Frame(parent)
        mode_frame.grid(row=7, column=1, padx=5, sticky='w')

        # 固定文字行（与视频文件夹行对齐：col0=标签, col1=输入框, col2=空）
        fixed_label = ttk.Label(parent, text="标题文字:")
        fixed_label.grid(row=8, column=0, sticky='w', padx=10, pady=5)
        fixed_entry = ttk.Entry(parent, textvariable=self.title_text)
        fixed_entry.grid(row=8, column=1, columnspan=2, padx=5, sticky='ew')

        # TXT文件行（与视频文件夹行对齐：col0=标签, col1=输入框, col2=浏览按钮）
        txt_label = ttk.Label(parent, text="TXT文件:")
        txt_label.grid(row=8, column=0, sticky='w', padx=10, pady=5)
        txt_entry = ttk.Entry(parent, textvariable=self.title_txt_file)
        txt_entry.grid(row=8, column=1, padx=5, sticky='ew')
        txt_btn = ttk.Button(parent, text="浏览", command=self._browse_title_txt)
        txt_btn.grid(row=8, column=2, padx=5)
        txt_hint = ttk.Label(parent, text="💡 每行一条标题，视频数量超出时从第一行循环读取。", foreground='gray')
        txt_hint.grid(row=9, column=0, columnspan=3, sticky='w', padx=12, pady=(0, 4))

        def _toggle_title_mode():
            if self.title_text_mode.get() == "fixed":
                txt_label.grid_remove()
                txt_entry.grid_remove()
                txt_btn.grid_remove()
                txt_hint.grid_remove()
                fixed_label.grid()
                fixed_entry.grid()
            else:
                fixed_label.grid_remove()
                fixed_entry.grid_remove()
                txt_label.grid()
                txt_entry.grid()
                txt_btn.grid()
                txt_hint.grid()

        ttk.Radiobutton(mode_frame, text="固定文字", variable=self.title_text_mode,
                        value="fixed", command=_toggle_title_mode).pack(side='left', padx=(0, 15))
        ttk.Radiobutton(mode_frame, text="从TXT读取", variable=self.title_text_mode,
                        value="txt", command=_toggle_title_mode).pack(side='left')
        _toggle_title_mode()

        ttk.Button(parent, text="批量添加标题", command=self.start_title, style='Accent.TButton').grid(row=10, column=0, columnspan=3, pady=15)
        parent.columnconfigure(1, weight=1)

    def create_crop_tab(self, parent):
        """创建批量裁剪比例标签页"""
        ttk.Label(parent, text="裁剪类型:").grid(row=0, column=0, sticky='w', padx=10, pady=5)
        mode_frame = ttk.Frame(parent)
        mode_frame.grid(row=0, column=1, padx=5, sticky='w')
        ttk.Radiobutton(mode_frame, text="批量裁剪视频", variable=self.crop_mode, value="video").pack(side='left', padx=6)
        ttk.Radiobutton(mode_frame, text="批量裁剪图片", variable=self.crop_mode, value="image").pack(side='left', padx=6)

        ttk.Label(parent, text="源文件夹:").grid(row=1, column=0, sticky='w', padx=10, pady=5)
        ttk.Entry(parent, textvariable=self.crop_video_folder).grid(row=1, column=1, padx=5, sticky='ew')
        ttk.Button(parent, text="浏览", command=lambda: self.browse_folder(self.crop_video_folder)).grid(row=1, column=2, padx=5)

        ttk.Label(parent, text="输出文件夹:").grid(row=2, column=0, sticky='w', padx=10, pady=5)
        ttk.Entry(parent, textvariable=self.crop_output_folder).grid(row=2, column=1, padx=5, sticky='ew')
        ttk.Button(parent, text="浏览", command=lambda: self.browse_folder(self.crop_output_folder, True)).grid(row=2, column=2, padx=5)

        ttk.Label(parent, text="目标比例:").grid(row=3, column=0, sticky='w', padx=10, pady=5)
        ratio_frame = ttk.Frame(parent)
        ratio_frame.grid(row=3, column=1, padx=5, sticky='w')
        for ratio in ("9:16", "16:9", "18:9", "1:1", "4:3", "3:4", "21:9"):
            ttk.Radiobutton(ratio_frame, text=ratio, variable=self.crop_ratio, value=ratio).pack(side='left', padx=6)

        ttk.Label(parent, text="💡 以居中方式裁剪，超出目标比例的四边内容将被裁掉，不会拉伸画面。",
                  foreground='gray').grid(row=4, column=0, columnspan=3, sticky='w', padx=12, pady=(0, 4))

        ttk.Button(parent, text="批量裁剪", command=self.start_crop, style='Accent.TButton').grid(row=5, column=0, columnspan=3, pady=15)
        parent.columnconfigure(1, weight=1)

    # 常见中文字体：注册表英文名 → 中文名（用于下拉框显示）
    _KNOWN_CHINESE_FONTS = {
        "Microsoft YaHei":            "微软雅黑",
        "Microsoft YaHei UI":         "微软雅黑 UI",
        "Microsoft YaHei Light":      "微软雅黑 细体",
        "Microsoft YaHei UI Light":   "微软雅黑 UI 细体",
        "SimSun":                     "宋体",
        "NSimSun":                    "新宋体",
        "SimSun-ExtB":                "宋体-ExtB",
        "SimSun-ExtG":                "宋体-ExtG",
        "SimHei":                     "黑体",
        "FangSong":                   "仿宋",
        "KaiTi":                      "楷体",
        "FangSong_GB2312":            "仿宋_GB2312",
        "KaiTi_GB2312":               "楷体_GB2312",
        "DengXian":                   "等线",
        "DengXian Light":             "等线 Light",
        "LiSu":                       "隶书",
        "YouYuan":                    "幼圆",
        "STSong":                     "华文宋体",
        "STZhongsong":                "华文中宋",
        "STFangsong":                 "华文仿宋",
        "STKaiti":                    "华文楷体",
        "STHupo":                     "华文琥珀",
        "STXihei":                    "华文细黑",
        "STCaiyun":                   "华文彩云",
        "STLiti":                     "华文隶书",
        "STXingkai":                  "华文行楷",
        "STXinwei":                   "华文新魏",
        "FZShuTi":                    "方正舒体",
        "FZYaoTi":                    "方正姚体",
        "Adobe Heiti Std R":          "Adobe 黑体 Std R",
        "Adobe Kaiti Std R":          "Adobe 楷体 Std R",
        "Adobe Song Std L":           "Adobe 宋体 Std L",
        "Adobe Fangsong Std R":       "Adobe 仿宋 Std R",
    }

    @staticmethod
    def _label_has_chinese(s):
        """判断字符串是否含有中文字符。"""
        return any('\u4e00' <= c <= '\u9fff' or '\u3400' <= c <= '\u4dbf' for c in s)

    def _get_system_fonts(self):
        """从 Windows 注册表读取字体，映射显示标签→字体文件路径。
        对已知中文字体生成 "中文名 (English Name)" 格式标签，使其排在前面且易于辨认。
        返回列表顺序：含中文名的字体在前（按名称排序），其余在后（按名称排序）。
        """
        import winreg
        fonts_dir = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "Fonts")
        font_map = {}
        try:
            reg_key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"
            )
            i = 0
            while True:
                try:
                    display_name, filename, _ = winreg.EnumValue(reg_key, i)
                    i += 1
                    font_path = filename if os.path.isabs(filename) else os.path.join(fonts_dir, filename)
                    if os.path.exists(font_path) and Path(font_path).suffix.lower() in ('.ttf', '.otf', '.ttc'):
                        eng = display_name.replace(" (TrueType)", "").replace(" (OpenType)", "").strip()
                        # 包含匹配：按英文名长度从长到短，收集所有命中的中文名（避免短串误匹配长串）
                        matched_cn = [cn for ek, cn in sorted(
                            self._KNOWN_CHINESE_FONTS.items(), key=lambda x: -len(x[0])
                        ) if ek in eng]
                        # 去重并保持顺序
                        seen, unique_cn = set(), []
                        for c in matched_cn:
                            if c not in seen:
                                seen.add(c)
                                unique_cn.append(c)
                        cn_part = " & ".join(unique_cn)
                        label = f"{cn_part} ({eng})" if cn_part else eng
                        font_map[label] = font_path
                except OSError:
                    break
            winreg.CloseKey(reg_key)
        except Exception:
            for fname in sorted(os.listdir(fonts_dir)):
                if fname.lower().endswith(('.ttf', '.otf', '.ttc')):
                    font_map[Path(fname).stem] = os.path.join(fonts_dir, fname)
        self._title_font_map = font_map
        chinese_names = sorted(k for k in font_map if self._label_has_chinese(k))
        other_names   = sorted(k for k in font_map if not self._label_has_chinese(k))
        return chinese_names + other_names

    def _refresh_title_fonts(self, combobox):
        """刷新字体列表"""
        values = self._get_system_fonts()
        combobox['values'] = values
        if values and not self.title_font.get():
            self.title_font.set(values[0])

    def _browse_title_txt(self):
        """浏览并选择标题TXT文件"""
        path = filedialog.askopenfilename(
            title="选择标题TXT文件",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        if path:
            self.title_txt_file.set(path)

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
    
    def start_music(self):
        thread = threading.Thread(target=self.batch_music_operation)
        thread.daemon = True
        thread.start()

    def start_title(self):
        thread = threading.Thread(target=self.batch_title_operation)
        thread.daemon = True
        thread.start()

    def start_crop(self):
        thread = threading.Thread(target=self.batch_crop_operation)
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
                *self._quality_args(),
                '-c:a', 'copy',  # 音频直接复制
                '-threads', '0',
                '-y',
                output_path
            ]
            
            result = self._run_cmd(cmd, timeout=600)
            
            if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                file_size_mb = os.path.getsize(output_path) / 1024 / 1024
                self.log(f"    ✓ 成功: {os.path.basename(output_path)} ({file_size_mb:.1f} MB)")
                return True
            else:
                self.log(f"    ✗ 失败: {result.stderr[-500:] if result.stderr else '未知错误'}")
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
            video_w, video_h, _ = self.get_video_resolution_fps(input_path)
            
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
                *self._quality_args(),
                '-c:a', 'copy',  # 音频直接复制
                '-threads', '0',
                '-y',
                output_path
            ]
            
            result = self._run_cmd(cmd, timeout=600)
            
            if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                file_size_mb = os.path.getsize(output_path) / 1024 / 1024
                self.log(f"    ✓ 成功: {os.path.basename(output_path)} ({file_size_mb:.1f} MB)")
                return True
            else:
                self.log(f"    ✗ 失败: {result.stderr[-500:] if result.stderr else '未知错误'}")
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
            
            result = self._run_cmd(cmd, timeout=300)
            
            if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                file_size_mb = os.path.getsize(output_path) / 1024 / 1024
                self.log(f"    ✓ 成功: {os.path.basename(output_path)} ({file_size_mb:.1f} MB)")
                return True
            else:
                self.log(f"    ✗ 失败: {result.stderr[-500:] if result.stderr else '未知错误'}")
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
                *self._quality_args(),
                '-c:a', audio_codec,
                '-threads', '0',
                '-y',
                output_path
            ]
            
            result = self._run_cmd(cmd, timeout=600)
            
            if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                file_size_mb = os.path.getsize(output_path) / 1024 / 1024
                self.log(f"    ✓ 成功: {os.path.basename(output_path)} ({file_size_mb:.1f} MB)")
                return True
            else:
                self.log(f"    ✗ 失败: {result.stderr[-500:] if result.stderr else '未知错误'}")
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
            
            result = self._run_cmd(cmd, timeout=600)
            
            # 计算提取的帧数
            if result.returncode == 0:
                # 统计输出文件夹中的图片数量
                frames = [f for f in os.listdir(output_folder) if f.endswith('.jpg')]
                return len(frames)
            else:
                self.log(f"    ✗ 提取失败: {result.stderr[-500:] if result.stderr else '未知错误'}")
                return 0
            
        except Exception as e:
            self.log(f"    ✗ 异常: {str(e)}")
            return 0

    # ===== 填充音乐功能实现 =====

    def batch_music_operation(self):
        """批量填充音乐"""
        self.current_operation = "music"
        self.set_controls_state(True)
        self.progress_var.set(0)
        
        temp_dir = None
        try:
            video_folder = self.music_video_folder.get()
            audio_folder = self.music_audio_folder.get()
            output_folder = self.music_output_folder.get()
            
            if not video_folder or not audio_folder or not output_folder:
                messagebox.showerror("错误", "请选择视频文件夹、音乐文件夹和输出文件夹！")
                return
            
            os.makedirs(output_folder, exist_ok=True)
            
            video_files = self.get_video_files(video_folder)
            if not video_files:
                messagebox.showerror("错误", "视频文件夹中没有找到视频文件！")
                return
            
            music_source_files = self.get_audio_video_files(audio_folder)
            if not music_source_files:
                messagebox.showerror("错误", "音乐文件夹中没有找到视频或音频文件！")
                return
            
            self.log(f"\n{'='*60}")
            self.log(f"开始填充音乐")
            self.log(f"视频数: {len(video_files)} 个")
            self.log(f"音乐源: {len(music_source_files)} 个")
            self.log(f"{'='*60}\n")
            
            temp_dir = os.path.join(output_folder, '_temp')
            os.makedirs(temp_dir, exist_ok=True)
            
            music_files = []
            for idx, mf in enumerate(music_source_files, 1):
                if self.check_pause_stop():
                    break
                mf_path = os.path.join(audio_folder, mf)
                ext = Path(mf).suffix.lower()
                
                if ext in self.audio_extensions:
                    music_files.append(mf_path)
                    self.log(f"  音频文件直接使用: {mf}")
                elif ext in self.video_extensions:
                    temp_audio = os.path.join(temp_dir, f"extract_{idx:03d}.aac")
                    self.log(f"  从视频提取音频: {mf}")
                    if self._music_extract_audio_ffmpeg(mf_path, temp_audio):
                        music_files.append(temp_audio)
                    else:
                        self.log(f"    ✗ 提取失败，跳过: {mf}")
            
            if not music_files:
                messagebox.showerror("错误", "未能获取任何可用的音乐文件！")
                return
            
            while len(music_files) < len(video_files):
                music_files.append(music_files[-1])
            
            keep_audio = self.music_keep_original_audio.get()
            mode_label = "混合模式（保留原声）" if keep_audio else "替换模式（移除原声）"
            self.log(f"\n可用音乐: {len(music_files)} 个（含补齐）")
            self.log(f"音频模式: {mode_label}")
            self.log(f"开始合并...\n")
            
            success_count = 0
            total = len(video_files)
            
            for idx, (vf, af) in enumerate(zip(video_files, music_files), 1):
                if self.check_pause_stop():
                    break
                
                video_path = os.path.join(video_folder, vf)
                output_name = f"music_{idx:03d}_{Path(vf).stem}.mp4"
                output_path = os.path.join(output_folder, output_name)
                
                self.log(f"[{idx}/{total}] {vf} + {os.path.basename(af)}")
                
                if self._music_replace_ffmpeg(video_path, af, output_path, keep_audio):
                    success_count += 1
                    self.log(f"  ✓ 成功: {output_name}")
                else:
                    self.log(f"  ✗ 失败: {vf}")
                
                self.progress_var.set((idx / total) * 100)
                self.update_status(f"填充音乐中... {idx}/{total}")
            
            self.log(f"\n{'='*60}")
            self.log(f"完成！成功处理 {success_count}/{total} 个视频")
            self.log(f"{'='*60}")
            
            if success_count > 0:
                messagebox.showinfo("完成", f"成功填充音乐 {success_count} 个视频！")
            
        except Exception as e:
            messagebox.showerror("错误", f"填充音乐失败: {str(e)}")
            self.log(f"✗ 错误: {str(e)}")
        finally:
            if temp_dir and os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                    self.log("已清理临时文件")
                except Exception:
                    pass
            self.set_controls_state(False)
    
    def _music_extract_audio_ffmpeg(self, input_path, output_path):
        """从视频中提取音频"""
        try:
            cmd = [
                self.ffmpeg_path,
                '-i', input_path,
                '-vn',
                '-c:a', 'aac',
                '-y',
                output_path
            ]
            
            result = self._run_cmd(cmd, timeout=300)
            
            if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                self.log(f"    ✓ 音频提取成功")
                return True
            else:
                self.log(f"    ✗ 音频提取失败: {result.stderr[-500:] if result.stderr else '未知错误'}")
                return False
            
        except Exception as e:
            self.log(f"    ✗ 音频提取异常: {str(e)}")
            return False
    
    def _music_replace_ffmpeg(self, video_path, audio_path, output_path, keep_original_audio=False):
        """合入新音频；keep_original_audio=True 时保留原声与新音频混合"""
        try:
            if keep_original_audio:
                cmd = [
                    self.ffmpeg_path,
                    '-i', video_path,
                    '-i', audio_path,
                    '-filter_complex', '[0:a][1:a]amix=inputs=2:duration=shortest[aout]',
                    '-map', '0:v',
                    '-map', '[aout]',
                    '-c:v', 'copy',
                    '-c:a', 'aac',
                    '-shortest',
                    '-y',
                    output_path
                ]
            else:
                cmd = [
                    self.ffmpeg_path,
                    '-i', video_path,
                    '-i', audio_path,
                    '-map', '0:v',
                    '-map', '1:a',
                    '-c:v', 'copy',
                    '-c:a', 'aac',
                    '-shortest',
                    '-y',
                    output_path
                ]
            
            result = self._run_cmd(cmd, timeout=600)
            
            if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                file_size_mb = os.path.getsize(output_path) / 1024 / 1024
                self.log(f"    ✓ 合并成功: {os.path.basename(output_path)} ({file_size_mb:.1f} MB)")
                return True
            else:
                self.log(f"    ✗ 合并失败: {result.stderr[-500:] if result.stderr else '未知错误'}")
                return False
            
        except Exception as e:
            self.log(f"    ✗ 合并异常: {str(e)}")
            return False

    def batch_title_operation(self):
        """批量为视频添加标题文字"""
        self.current_operation = "title"
        self.set_controls_state(True)
        self.progress_var.set(0)

        try:
            video_folder = self.title_video_folder.get()
            output_folder = self.title_output_folder.get().strip()
            font_name = self.title_font.get()
            text_mode = self.title_text_mode.get()
            fontsize_unit = self.title_fontsize_unit.get()
            try:
                fontsize_val = max(1, float(self.title_fontsize.get()))
                if fontsize_unit == "percent":
                    fontsize_val = max(0.5, min(50.0, fontsize_val))
                else:
                    fontsize_val = max(10, int(fontsize_val))
            except ValueError:
                fontsize_val = 5 if fontsize_unit == "percent" else 30
            try:
                y_percent = max(0, min(90, float(self.title_y_percent.get()))) / 100
            except ValueError:
                y_percent = 0.08

            if not video_folder:
                messagebox.showerror("错误", "请选择视频文件夹！")
                return
            if not font_name:
                messagebox.showerror("错误", "请选择字体！")
                return

            if text_mode == "fixed":
                fixed_title = ''.join(ch for ch in self.title_text.get() if ch.isprintable()).strip()
                if not fixed_title:
                    messagebox.showerror("错误", "请输入标题文字！")
                    return
                title_lines = None
            else:
                txt_file = self.title_txt_file.get().strip()
                if not txt_file:
                    messagebox.showerror("错误", "请选择TXT文件！")
                    return
                if not os.path.exists(txt_file):
                    messagebox.showerror("错误", f"TXT文件不存在：{txt_file}")
                    return
                with open(txt_file, 'r', encoding='utf-8') as f:
                    title_lines = [line.strip() for line in f if line.strip()]
                if not title_lines:
                    messagebox.showerror("错误", "TXT文件中没有有效内容！")
                    return
                fixed_title = None

            font_color = self.title_fontcolor.get() or "#ffffff"

            font_path = getattr(self, '_title_font_map', {}).get(font_name)
            if not font_path or not os.path.exists(font_path):
                messagebox.showerror("错误", f"找不到字体文件：{font_name}")
                return

            video_files = self.get_video_files(video_folder)
            if not video_files:
                messagebox.showerror("错误", "文件夹中没有找到视频文件！")
                return

            if not output_folder:
                output_folder = os.path.join(video_folder, "title_output")
            os.makedirs(output_folder, exist_ok=True)

            self.log(f"\n{'='*60}")
            self.log(f"开始批量添加标题")
            self.log(f"视频数: {len(video_files)} 个")
            if title_lines:
                self.log(f"标题来源: TXT文件，共 {len(title_lines)} 行（不够则循环）")
            else:
                self.log(f"标题: {fixed_title}")
            self.log(f"字体: {font_name}")
            self.log(f"{'='*60}\n")

            success_count = 0

            for idx, video_file in enumerate(video_files, 1):
                if self.check_pause_stop():
                    break

                video_path = os.path.join(video_folder, video_file)
                output_name = f"title_{idx:03d}_{Path(video_file).stem}.mp4"
                output_path = os.path.join(output_folder, output_name)

                current_title = (title_lines[(idx - 1) % len(title_lines)] if title_lines else fixed_title).replace('%', '')

                self.log(f"\n[{idx}/{len(video_files)}] 处理: {video_file}")
                self.log(f"  标题: {current_title}")

                try:
                    ok = self._title_ffmpeg(video_path, output_path, font_path, current_title, fontsize_val, y_percent, fontsize_unit, font_color)
                except RuntimeError as e:
                    if "__font_error__" in str(e):
                        self.log(f"✗ 字体加载失败，终止批处理")
                        messagebox.showerror(
                            "字体失效",
                            f"当前系统字体「{Path(font_path).stem}」无法正常加载。\n\n请更换字体后重试。"
                        )
                        break
                    raise
                else:
                    if ok:
                        success_count += 1
                        self.log(f"✓ 成功: {output_name}")
                    else:
                        self.log(f"✗ 失败: {video_file}")

                self.progress_var.set((idx / len(video_files)) * 100)
                self.update_status(f"添加标题中... {idx}/{len(video_files)}")

            self.log(f"\n{'='*60}")
            self.log(f"完成！成功处理 {success_count}/{len(video_files)} 个视频")
            self.log(f"输出目录: {output_folder}")
            self.log(f"{'='*60}")

            if success_count > 0:
                done = threading.Event()
                def _show_done_dialog():
                    dlg = tk.Toplevel(self.root)
                    dlg.withdraw()
                    dlg.title("完成")
                    dlg.resizable(False, False)
                    dlg.transient(self.root)
                    icon_path = _resource_path(os.path.join('assets', 'logo.ico'))
                    if os.path.exists(icon_path):
                        dlg.iconbitmap(icon_path)
                    tk.Label(dlg, text=f"成功处理 {success_count} 个视频！\n输出目录: {output_folder}",
                             padx=20, pady=15, justify="left").pack()
                    btn_frame = tk.Frame(dlg, pady=8)
                    btn_frame.pack()
                    tk.Button(btn_frame, text="打开文件夹", width=12,
                              command=lambda: [os.startfile(output_folder), dlg.destroy(), done.set()]).pack(side="left", padx=6)
                    tk.Button(btn_frame, text="确定", width=8,
                              command=lambda: [dlg.destroy(), done.set()]).pack(side="left", padx=6)
                    dlg.protocol("WM_DELETE_WINDOW", lambda: [dlg.destroy(), done.set()])
                    dlg.update_idletasks()
                    w, h = dlg.winfo_reqwidth(), dlg.winfo_reqheight()
                    rx = self.root.winfo_x() + (self.root.winfo_width() - w) // 2
                    ry = self.root.winfo_y() + (self.root.winfo_height() - h) // 2
                    dlg.geometry(f"+{rx}+{ry}")
                    dlg.deiconify()
                    dlg.grab_set()
                self.root.after(0, _show_done_dialog)
                done.wait()

        except Exception as e:
            messagebox.showerror("错误", f"添加标题失败: {str(e)}")
            self.log(f"✗ 错误: {str(e)}")
        finally:
            self.set_controls_state(False)

    def batch_crop_operation(self):
        """批量居中裁剪视频/图片为指定比例"""
        self.current_operation = "crop"
        self.set_controls_state(True)
        self.progress_var.set(0)

        try:
            source_folder = self.crop_video_folder.get().strip()
            output_folder = self.crop_output_folder.get().strip()
            ratio_str = self.crop_ratio.get().strip()
            mode = self.crop_mode.get()
            is_image = (mode == "image")
            type_label = "图片" if is_image else "视频"

            if not source_folder:
                messagebox.showerror("错误", f"请选择{type_label}文件夹！")
                return

            if not ratio_str or ':' not in ratio_str:
                messagebox.showerror("错误", "请选择目标比例！")
                return

            try:
                rw, rh = [int(x) for x in ratio_str.split(':')]
            except ValueError:
                messagebox.showerror("错误", f"比例格式不正确：{ratio_str}")
                return

            if is_image:
                files = self.get_image_files(source_folder)
            else:
                files = self.get_video_files(source_folder)
            if not files:
                messagebox.showerror("错误", f"文件夹中没有找到{type_label}文件！")
                return

            if not output_folder:
                output_folder = os.path.join(source_folder, "crop_output")
            os.makedirs(output_folder, exist_ok=True)

            self.log(f"\n{'='*60}")
            self.log(f"开始批量裁剪{type_label}比例")
            self.log(f"{type_label}数: {len(files)} 个")
            self.log(f"目标比例: {ratio_str}")
            self.log(f"{'='*60}\n")

            success_count = 0

            for idx, file_name in enumerate(files, 1):
                if self.check_pause_stop():
                    break

                file_path = os.path.join(source_folder, file_name)

                if is_image:
                    ext = Path(file_name).suffix.lower()
                    output_name = f"crop_{ratio_str.replace(':', 'x')}_{idx:03d}_{Path(file_name).stem}{ext}"
                    output_path = os.path.join(output_folder, output_name)
                    self.log(f"\n[{idx}/{len(files)}] 处理: {file_name}")
                    ok = self._crop_image(file_path, output_path, rw, rh)
                else:
                    output_name = f"crop_{ratio_str.replace(':', 'x')}_{idx:03d}_{Path(file_name).stem}.mp4"
                    output_path = os.path.join(output_folder, output_name)
                    self.log(f"\n[{idx}/{len(files)}] 处理: {file_name}")
                    ok = self._crop_ffmpeg(file_path, output_path, rw, rh)

                if ok:
                    success_count += 1
                    self.log(f"✓ 成功: {output_name}")
                else:
                    self.log(f"✗ 失败: {file_name}")

                self.progress_var.set((idx / len(files)) * 100)
                self.update_status(f"裁剪{type_label}中... {idx}/{len(files)}")

            self.log(f"\n{'='*60}")
            self.log(f"完成！成功处理 {success_count}/{len(files)} 个{type_label}")
            self.log(f"输出目录: {output_folder}")
            self.log(f"{'='*60}")

            if success_count > 0:
                done = threading.Event()
                def _show_done_dialog():
                    dlg = tk.Toplevel(self.root)
                    dlg.withdraw()
                    dlg.title("完成")
                    dlg.resizable(False, False)
                    dlg.transient(self.root)
                    icon_path = _resource_path(os.path.join('assets', 'logo.ico'))
                    if os.path.exists(icon_path):
                        dlg.iconbitmap(icon_path)
                    tk.Label(dlg, text=f"成功处理 {success_count} 个{type_label}！\n输出目录: {output_folder}",
                             padx=20, pady=15, justify="left").pack()
                    btn_frame = tk.Frame(dlg, pady=8)
                    btn_frame.pack()
                    tk.Button(btn_frame, text="打开文件夹", width=12,
                              command=lambda: [os.startfile(output_folder), dlg.destroy(), done.set()]).pack(side="left", padx=6)
                    tk.Button(btn_frame, text="确定", width=8,
                              command=lambda: [dlg.destroy(), done.set()]).pack(side="left", padx=6)
                    dlg.protocol("WM_DELETE_WINDOW", lambda: [dlg.destroy(), done.set()])
                    dlg.update_idletasks()
                    w, h = dlg.winfo_reqwidth(), dlg.winfo_reqheight()
                    rx = self.root.winfo_x() + (self.root.winfo_width() - w) // 2
                    ry = self.root.winfo_y() + (self.root.winfo_height() - h) // 2
                    dlg.geometry(f"+{rx}+{ry}")
                    dlg.deiconify()
                    dlg.grab_set()
                self.root.after(0, _show_done_dialog)
                done.wait()

        except Exception as e:
            messagebox.showerror("错误", f"裁剪失败: {str(e)}")
            self.log(f"✗ 错误: {str(e)}")
        finally:
            self.set_controls_state(False)

    def _crop_ffmpeg(self, input_path, output_path, ratio_w, ratio_h):
        """居中裁剪视频到指定宽高比，不拉伸画面"""
        try:
            src_w, src_h, _ = self.get_video_resolution_fps(input_path)
            src_ratio = src_w / src_h
            target_ratio = ratio_w / ratio_h

            if abs(src_ratio - target_ratio) < 0.001:
                # 比例已相同，直接复制流
                crop_filter = f"crop={src_w}:{src_h}:0:0"
            elif src_ratio > target_ratio:
                # 原视频更宽，裁剪左右
                new_w = int(src_h * ratio_w / ratio_h)
                new_w -= new_w % 2  # 保证偶数
                x = (src_w - new_w) // 2
                crop_filter = f"crop={new_w}:{src_h}:{x}:0"
            else:
                # 原视频更高，裁剪上下
                new_h = int(src_w * ratio_h / ratio_w)
                new_h -= new_h % 2
                y = (src_h - new_h) // 2
                crop_filter = f"crop={src_w}:{new_h}:0:{y}"

            cmd = [
                self.ffmpeg_path,
                '-i', input_path,
                '-vf', crop_filter,
                '-c:v', 'libx264',
                '-preset', 'ultrafast' if self.speed_priority.get() else 'medium',
                *self._quality_args(),
                '-c:a', 'copy',
                '-y',
                output_path
            ]
            result = self._run_cmd(cmd, timeout=600)
            return result.returncode == 0
        except Exception as e:
            self.log(f"  ffmpeg 错误: {e}")
            return False

    def _crop_image(self, input_path, output_path, ratio_w, ratio_h):
        """居中裁剪图片到指定宽高比，不拉伸画面"""
        try:
            with Image.open(input_path) as img:
                src_w, src_h = img.size
                src_ratio = src_w / src_h
                target_ratio = ratio_w / ratio_h

                if abs(src_ratio - target_ratio) < 0.001:
                    crop_box = (0, 0, src_w, src_h)
                elif src_ratio > target_ratio:
                    new_w = int(src_h * ratio_w / ratio_h)
                    x = (src_w - new_w) // 2
                    crop_box = (x, 0, x + new_w, src_h)
                else:
                    new_h = int(src_w * ratio_h / ratio_w)
                    y = (src_h - new_h) // 2
                    crop_box = (0, y, src_w, y + new_h)

                cropped = img.crop(crop_box)
                if img.mode == 'RGBA' and Path(output_path).suffix.lower() in ('.jpg', '.jpeg', '.bmp'):
                    cropped = cropped.convert('RGB')
                cropped.save(output_path, quality=95)
            return True
        except Exception as e:
            self.log(f"  图片裁剪错误: {e}")
            return False

    def _wrap_title_text(self, text, fontsize, video_width, margin_ratio=0.08):
        """
        按视频宽度和字体大小动态换行。
        中文/全角按 fontsize*1.15 估算宽度（含字间距），ASCII/半角按 fontsize*0.65。
        两侧各留 margin_ratio (默认8%) 留白。
        """
        import unicodedata

        usable_px = video_width * (1.0 - 2 * margin_ratio)

        def char_px(ch):
            if unicodedata.east_asian_width(ch) in ('W', 'F'):
                return fontsize * 1.15
            return fontsize * 0.65

        lines = []
        current = ""
        current_w = 0.0

        for ch in text:
            w = char_px(ch)
            if current_w + w <= usable_px:
                current += ch
                current_w += w
            else:
                if current:
                    lines.append(current)
                current = ch
                current_w = w

        if current:
            lines.append(current)

        return lines if lines else [text]

    def _title_ffmpeg(self, input_path, output_path, font_path, title_text, fontsize=5, y_percent=0.08, fontsize_unit="percent", font_color="#ffffff"):
        """使用 FFmpeg drawtext 在视频指定高度居中位置烧录标题文字，支持自动换行"""
        try:
            safe_font = font_path.replace("\\", "/").replace(":", "\\:")

            # 将 #rrggbb 转换为 ffmpeg 接受的 0xrrggbb 格式
            if font_color.startswith("#"):
                ffmpeg_color = "0x" + font_color[1:]
            else:
                ffmpeg_color = font_color

            video_width, video_height, _ = self.get_video_resolution_fps(input_path)
            if fontsize_unit == "percent":
                fontsize = max(10, int(video_height * fontsize / 100))
            else:
                fontsize = max(10, int(fontsize))
            lines = self._wrap_title_text(title_text, fontsize, video_width)

            line_spacing = fontsize * 1.35  # 行间距
            drawtext_filters = []

            for i, line in enumerate(lines):
                safe_text = line.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")
                # 多行时整体垂直居中于 y_percent 位置
                y_expr = f"h*{y_percent}+{i * line_spacing:.1f}"
                drawtext_filters.append(
                    f"drawtext=fontfile='{safe_font}'"
                    f":text='{safe_text}'"
                    f":x=(w-text_w)/2"
                    f":y={y_expr}"
                    f":fontsize={fontsize}"
                    f":fontcolor={ffmpeg_color}"
                    f":borderw=3"
                    f":bordercolor=black@0.7"
                    f":shadowx=2:shadowy=2:shadowcolor=black@0.5"
                )

            drawtext = ",".join(drawtext_filters)

            cmd = [
                self.ffmpeg_path,
                '-i', input_path,
                '-vf', drawtext,
                '-c:v', 'libx264',
                '-preset', 'ultrafast' if self.speed_priority.get() else 'medium',
                *self._quality_args(),
                '-c:a', 'copy',
                '-y',
                output_path
            ]

            result = self._run_cmd(cmd, timeout=600)

            if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                size_mb = os.path.getsize(output_path) / 1024 / 1024
                self.log(f"    ✓ 完成: {os.path.basename(output_path)} ({size_mb:.1f} MB)")
                return True
            else:
                stderr_text = result.stderr or ""
                if "Fontconfig error" in stderr_text or "Cannot load default config file" in stderr_text:
                    raise RuntimeError("__font_error__")
                self.log(f"    ✗ 失败: {stderr_text[-500:] if stderr_text else '未知错误'}")
                return False

        except RuntimeError:
            raise
        except Exception as e:
            self.log(f"    ✗ 异常: {str(e)}")
            return False

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
                '-i', input_path,
                '-ss', str(start_time),
                '-t', str(duration),
                '-c:v', 'libx264',
                '-preset', 'ultrafast' if self.speed_priority.get() else 'medium',
                *self._quality_args(),
                '-c:a', 'aac',
                '-threads', '0',
                '-avoid_negative_ts', 'make_zero',
                '-y',
                output_path
            ]
            
            self.log(f"    执行: ffmpeg -i ... -ss {start_time} -t {duration}")
            
            result = self._run_cmd(cmd, timeout=300)
            
            if result.returncode != 0:
                error_msg = result.stderr[-500:] if result.stderr else "未知错误"
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
                '-i', input_path,
                '-ss', str(start_time),
                '-t', str(duration),
                '-vn',
                '-c:a', 'libmp3lame',
                '-q:a', '4',
                '-y',
                output_path
            ]
            
            result = self._run_cmd(cmd, timeout=300)
            
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
                    *self._quality_args(),
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
            result = self._run_cmd(cmd, timeout=600)
            
            if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                file_size_mb = os.path.getsize(output_path) / 1024 / 1024
                self.log(f"    ✓ 成功: {os.path.basename(output_path)} ({file_size_mb:.1f} MB)")
                return True
            else:
                self.log(f"    ✗ 失败: {result.stderr[-500:] if result.stderr else '未知错误'}")
                return False
            
        except Exception as e:
            self.log(f"    ✗ 异常: {str(e)}")
            return False
    
    def _merge_with_moviepy_safe(self, file1_path, file2_path, output_path, image_duration):
        """MoviePy备用方案"""
        try:
            import PIL.Image
            if not hasattr(PIL.Image, 'ANTIALIAS'):
                PIL.Image.ANTIALIAS = PIL.Image.LANCZOS
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
            
            # 导出（ImageClip 无 fps，显式指定兜底）
            output_fps = getattr(clip1, 'fps', None) or getattr(clip2, 'fps', None) or 24
            preset = 'ultrafast' if self.speed_priority.get() else 'medium'
            final.write_videofile(output_path, fps=output_fps, codec='libx264', preset=preset, logger=None)
            
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

            # 创建临时文件夹，用于存放分辨率归一化后的视频
            temp_dir = os.path.join(output, "_concat_temp_resize")
            os.makedirs(temp_dir, exist_ok=True)

            try:
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

                    # 分辨率/帧率归一化：以第一个视频为基准，居中裁剪并统一帧率
                    td = self.concat_transition.get()
                    ref_w, ref_h, ref_fps = self.get_video_resolution_fps(group_videos[0])
                    self.log(f"    基准分辨率: {ref_w}x{ref_h}，帧率: {ref_fps}fps（取自第1个视频）")
                    # 预扫描：判断是否有任何视频需要归一化
                    any_needs_norm = False
                    for k in range(1, len(group_videos)):
                        _w, _h, _fps = self.get_video_resolution_fps(group_videos[k])
                        if (_w != ref_w or _h != ref_h) or (round(_fps, 3) != round(ref_fps, 3)):
                            any_needs_norm = True
                            break
                    # xfade 要求所有输入 timebase 一致；只要有视频被重编码，
                    # 第一个视频也必须同样重编码，否则原始 tbn 与重编码后 tbn 不同
                    normalized_videos = []
                    preset = 'ultrafast' if self.speed_priority.get() else 'medium'
                    for k in range(len(group_videos)):
                        src = group_videos[k]
                        if k == 0:
                            # 分辨率/帧率已知，仅需一次 ffprobe 查音频
                            _, _, _, src_has_audio = self._get_video_info(src)
                            w, h, src_fps = ref_w, ref_h, ref_fps
                        else:
                            # 一次 ffprobe 同时获取分辨率、帧率、音频
                            w, h, src_fps, src_has_audio = self._get_video_info(src)
                        need_resize = (w != ref_w or h != ref_h)
                        need_fps = (round(src_fps, 3) != round(ref_fps, 3))
                        # 有转场时：只要有其他视频被重编码，第一个也必须重编码保证 timebase 一致
                        force_reencode = (k == 0 and td > 0 and any_needs_norm)
                        need_audio_fix = not src_has_audio
                        if not need_resize and not need_fps and not force_reencode and not need_audio_fix:
                            normalized_videos.append(src)
                        else:
                            reasons = []
                            if need_resize:
                                reasons.append(f"分辨率 {w}x{h}→{ref_w}x{ref_h}")
                            if need_fps:
                                reasons.append(f"帧率 {src_fps}→{ref_fps}fps")
                            if force_reencode and not need_resize and not need_fps:
                                reasons.append("timebase 对齐（xfade）")
                            if need_audio_fix:
                                reasons.append("补充静音音频轨")
                            self.log(f"    需要归一化 [{k+1}]: {', '.join(reasons)}")
                            tmp_name = f"tmp_{i:03d}_{k:02d}_{os.path.basename(src)}"
                            tmp_path = os.path.join(temp_dir, tmp_name)
                            if need_audio_fix:
                                resize_cmd = [
                                    self.ffmpeg_path, '-i', src,
                                    '-f', 'lavfi', '-i', 'anullsrc=channel_layout=stereo:sample_rate=44100',
                                ]
                                if need_resize:
                                    resize_cmd += ['-vf', f"scale={ref_w}:{ref_h}:force_original_aspect_ratio=increase,crop={ref_w}:{ref_h},setsar=1"]
                                else:
                                    resize_cmd += ['-vf', 'setsar=1']
                                resize_cmd += [
                                    '-r', str(ref_fps),
                                    '-c:v', 'libx264', '-preset', preset, *self._quality_args(),
                                    '-c:a', 'aac', '-shortest',
                                    '-threads', '0', '-y', tmp_path,
                                ]
                            else:
                                resize_cmd = [
                                    self.ffmpeg_path, '-i', src,
                                ]
                                if need_resize:
                                    resize_cmd += ['-vf', f"scale={ref_w}:{ref_h}:force_original_aspect_ratio=increase,crop={ref_w}:{ref_h},setsar=1"]
                                else:
                                    resize_cmd += ['-vf', 'setsar=1']
                                resize_cmd += [
                                    '-r', str(ref_fps),
                                    '-c:v', 'libx264', '-preset', preset, *self._quality_args(),
                                    '-c:a', 'aac', '-threads', '0', '-y', tmp_path,
                                ]
                            res = self._run_cmd(resize_cmd, timeout=600)
                            if res.returncode == 0 and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
                                normalized_videos.append(tmp_path)
                            else:
                                self.log(f"    ✗ 归一化转换失败，使用原始文件: {os.path.basename(src)}")
                                normalized_videos.append(src)

                    if self._concat_with_transition(normalized_videos, output_path):
                        success_count += 1
                        self.log(f"✓ 成功: {output_name}")
                    else:
                        self.log(f"✗ 失败")

                    self.progress_var.set((i + 1) / min_count * 100)
                    self.update_status(f"转场拼接中... {i+1}/{min_count}")

            finally:
                # 清理临时文件夹
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    self.log(f"    临时文件夹已清理")

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
        """转场拼接：td=0 用 concat filter 保证时间戳连续，td>0 用 xfade+acrossfade"""
        try:
            if len(video_paths) == 1:
                shutil.copy2(video_paths[0], output_path)
                return True

            n = len(video_paths)
            td = self.concat_transition.get()
            _tt_raw = self.concat_transition_type.get() or '淡入淡出-fade'
            transition_type = _tt_raw.split('-')[-1] if '-' in _tt_raw else _tt_raw
            preset = 'ultrafast' if self.speed_priority.get() else 'medium'

            def run_cmd(cmd):
                return self._run_cmd(cmd, timeout=900)

            # 构建公共输入参数
            inputs = []
            for v in video_paths:
                inputs += ['-i', v]

            if td <= 0:
                # ── 无转场：用 concat filter 替代 -f concat demuxer ──
                # concat filter 会统一时间基，避免帧率/时间戳不连续导致的卡顿
                # 先对每个输入视频 setsar=1，避免 SAR 不一致导致 concat 失败
                setsar = ';'.join(f'[{i}:v]setsar=1[sv{i}]' for i in range(n))
                streams = ''.join(f'[sv{i}][{i}:a]' for i in range(n))
                filter_complex = f'{setsar};{streams}concat=n={n}:v=1:a=1[vout][aout]'
                cmd = [self.ffmpeg_path] + inputs + [
                    '-filter_complex', filter_complex,
                    '-map', '[vout]', '-map', '[aout]',
                    '-c:v', 'libx264', '-preset', preset, *self._quality_args(),
                    '-c:a', 'aac', '-threads', '0', '-y', output_path,
                ]
            else:
                # ── 有转场：用 xfade + acrossfade 链实现真正的转场动画 ──
                # 第一步：ffprobe 获取每段时长（计算 xfade offset 必需）
                durations = []
                for v in video_paths:
                    d = self._get_video_duration_fast(v)
                    if d <= 0:
                        self.log(f"    ✗ 无法获取时长: {os.path.basename(v)}")
                        return False
                    durations.append(d)
                    self.log(f"    时长: {os.path.basename(v)} = {d:.2f}s")

                # 转场时长不能超过最短片段的一半
                min_dur = min(durations)
                if td >= min_dur:
                    td = round(min_dur * 0.4, 3)
                    self.log(f"    ⚠ 转场时长超过最短片段，自动调整为 {td:.2f}s")

                # 第二步：构建 filter_complex
                # xfade offset = 前所有片段时长之和 - 已叠加的转场时长
                # acrossfade 不需要 offset，直接链式连接即可
                # 先对每个输入视频 setsar=1，避免 SAR 不一致导致 xfade 失败
                filter_parts = [f'[{i}:v]setsar=1[sv{i}]' for i in range(n)]
                prev_v = '[sv0]'
                prev_a = '[0:a]'
                offset = 0.0
                for i in range(1, n):
                    offset += durations[i - 1] - td
                    is_last = (i == n - 1)
                    out_v = '[vout]' if is_last else f'[v{i}]'
                    out_a = '[aout]' if is_last else f'[a{i}]'
                    filter_parts.append(
                        f"{prev_v}[sv{i}]xfade=transition={transition_type}"
                        f":duration={td:.3f}:offset={offset:.3f}{out_v}"
                    )
                    filter_parts.append(
                        f"{prev_a}[{i}:a]acrossfade=d={td:.3f}{out_a}"
                    )
                    prev_v = out_v
                    prev_a = out_a

                filter_complex = ';'.join(filter_parts)
                cmd = [self.ffmpeg_path] + inputs + [
                    '-filter_complex', filter_complex,
                    '-map', '[vout]', '-map', '[aout]',
                    '-c:v', 'libx264', '-preset', preset, *self._quality_args(),
                    '-c:a', 'aac', '-threads', '0', '-y', output_path,
                ]

            result = run_cmd(cmd)
            if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                file_size_mb = os.path.getsize(output_path) / 1024 / 1024
                self.log(f"    ✓ 拼接成功: {os.path.basename(output_path)} ({file_size_mb:.1f} MB)")
                return True
            else:
                if os.path.exists(output_path) and os.path.getsize(output_path) == 0:
                    os.remove(output_path)
                self.log(f"    ✗ 拼接失败: {result.stderr[-500:] if result.stderr else '未知错误'}")
                return False

        except Exception as e:
            if os.path.exists(output_path) and os.path.getsize(output_path) == 0:
                try:
                    os.remove(output_path)
                except Exception:
                    pass
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
            bg_w, bg_h, _ = self.get_video_resolution_fps(bg_path)
            
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
                *self._quality_args(),
                '-c:a', 'copy',
                '-threads', '0',
                '-y',
                output_path
            ]
            
            result = self._run_cmd(cmd, timeout=600)
            
            if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                file_size_mb = os.path.getsize(output_path) / 1024 / 1024
                self.log(f"    ✓ 画中画成功: {os.path.basename(output_path)} ({file_size_mb:.1f} MB)")
                return True
            else:
                self.log(f"    ✗ 画中画失败: {result.stderr[-500:] if result.stderr else '未知错误'}")
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
                *self._quality_args(),
                '-c:a', 'aac',
                '-threads', '0',
                '-y',
                output_path
            ]
            
            result = self._run_cmd(cmd, timeout=600)
            
            if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                file_size_mb = os.path.getsize(output_path) / 1024 / 1024
                self.log(f"    ✓ 变速成功: {os.path.basename(output_path)} ({file_size_mb:.1f} MB)")
                return True
            else:
                self.log(f"    ✗ 变速失败: {result.stderr[-500:] if result.stderr else '未知错误'}")
                return False
            
        except Exception as e:
            self.log(f"    ✗ 变速异常: {str(e)}")
            return False


    # ─────────────────────────────────────────────────────────────
    # 视频翻译 Tab UI
    # ─────────────────────────────────────────────────────────────

    def create_translate_tab(self, parent):
        """创建视频翻译标签页"""
        ttk.Label(parent, text="视频文件夹:").grid(row=0, column=0, sticky='w', padx=10, pady=5)
        ttk.Entry(parent, textvariable=self.translate_folder, width=45).grid(row=0, column=1, padx=5)
        ttk.Button(parent, text="浏览", command=lambda: self.browse_folder(self.translate_folder)).grid(row=0, column=2, padx=5)

        ttk.Label(parent, text="输出文件夹:").grid(row=1, column=0, sticky='w', padx=10, pady=5)
        ttk.Entry(parent, textvariable=self.translate_output, width=45).grid(row=1, column=1, padx=5)
        ttk.Button(parent, text="浏览", command=lambda: self.browse_folder(self.translate_output, True)).grid(row=1, column=2, padx=5)

        lang_frame = ttk.LabelFrame(parent, text="翻译设置", padding=10)
        lang_frame.grid(row=2, column=0, columnspan=3, sticky='ew', padx=10, pady=5)

        ttk.Label(lang_frame, text="目标语言:").pack(side='left', padx=5)
        lang_combo = ttk.Combobox(
            lang_frame,
            textvariable=self.translate_target_lang,
            values=["zh", "en"],
            width=8,
            state="readonly",
        )
        lang_combo.pack(side='left', padx=5)
        ttk.Label(lang_frame, text="zh=中文  en=英文", foreground='gray').pack(side='left', padx=10)

        ttk.Button(
            parent, text="开始批量翻译配音",
            command=self.start_translate,
            style='Accent.TButton',
        ).grid(row=3, column=0, columnspan=3, pady=15)

        parent.columnconfigure(1, weight=1)

    def start_translate(self):
        thread = threading.Thread(target=self.batch_translate_operation)
        thread.daemon = True
        thread.start()

    def batch_translate_operation(self):
        """批量视频翻译配音入口"""
        self.current_operation = "translate"
        self.set_controls_state(True)
        self.progress_var.set(0)

        try:
            folder = self.translate_folder.get().strip()
            output_folder = self.translate_output.get().strip()
            target_lang = self.translate_target_lang.get().strip() or "zh"

            if not folder or not output_folder:
                messagebox.showerror("错误", "请选择视频文件夹和输出文件夹！")
                return
            if not self.mcp_url.get().strip():
                messagebox.showerror("错误", "请在设置中配置 MCP 地址！")
                return
            if not self.llm_api_key.get().strip():
                messagebox.showerror("错误", "请在设置中配置 LLM API Key！")
                return

            os.makedirs(output_folder, exist_ok=True)

            video_files = self.get_video_files(folder)
            if not video_files:
                messagebox.showerror("错误", "文件夹中没有找到视频文件！")
                return

            task_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            if getattr(sys, 'frozen', False):
                base_dir = Path(sys.executable).parent
            else:
                base_dir = Path(sys.argv[0]).parent
            task_temp_root = base_dir / "temp" / task_ts

            self.log(f"\n{'='*60}")
            self.log(f"开始批量翻译配音")
            self.log(f"视频数: {len(video_files)} 个  目标语言: {target_lang}")
            self.log(f"临时目录: {task_temp_root}")
            self.log(f"{'='*60}\n")

            success_count = 0
            for idx, video_file in enumerate(video_files, 1):
                if self.check_pause_stop():
                    break

                video_path = os.path.join(folder, video_file)
                video_temp_dir = task_temp_root / Path(video_file).stem
                os.makedirs(video_temp_dir, exist_ok=True)

                self.log(f"\n[{idx}/{len(video_files)}] 处理: {video_file}")
                ok = self._translate_video(video_path, output_folder, str(video_temp_dir), target_lang)
                if ok:
                    success_count += 1
                    self.log(f"✓ 完成: {video_file}")
                else:
                    self.log(f"✗ 失败: {video_file}")

                self.progress_var.set((idx / len(video_files)) * 100)
                self.update_status(f"翻译配音中... {idx}/{len(video_files)}")

            self.log(f"\n{'='*60}")
            self.log(f"完成！成功处理 {success_count}/{len(video_files)} 个视频")
            self.log(f"{'='*60}")

            if success_count > 0:
                messagebox.showinfo("完成", f"成功翻译配音 {success_count} 个视频！")

        except Exception as e:
            messagebox.showerror("错误", f"翻译配音失败: {str(e)}")
            self.log(f"✗ 错误: {str(e)}")
        finally:
            self.set_controls_state(False)

    # ─────────────────────────────────────────────────────────────
    # 视频翻译核心逻辑
    # ─────────────────────────────────────────────────────────────

    def _translate_video(self, input_path: str, output_folder: str, temp_dir: str, target_lang: str) -> bool:
        """对单个视频执行完整 11 步翻译配音流程。"""
        stem = Path(input_path).stem
        mcp_url = self.mcp_url.get().strip()

        def p(n, msg):
            self.log(f"  [{n}/11] {msg}")

        try:
            # Step 1 — 提取音频
            p(1, "提取音频...")
            origin_audio = os.path.join(temp_dir, "origin_audio.mp3")
            cmd = [
                self.ffmpeg_path, "-i", input_path,
                "-vn", "-ar", "44100", "-ac", "2", "-ab", "192k", "-f", "mp3",
                "-y", origin_audio,
            ]
            r = self._run_ffmpeg(cmd, timeout=300)
            if not r:
                return False

            # Step 2 — Demucs 人声分离
            p(2, "人声分离（Demucs）...")
            try:
                vocals_bytes, no_vocals_bytes = asyncio.run(
                    _mcp_separate(origin_audio, mcp_url)
                )
            except Exception as e:
                self.log(f"    ✗ Demucs 失败: {e}")
                return False
            vocals_path = os.path.join(temp_dir, "vocals.wav")
            no_vocals_path = os.path.join(temp_dir, "no_vocals.wav")
            open(vocals_path, "wb").write(vocals_bytes)
            open(no_vocals_path, "wb").write(no_vocals_bytes)

            # Step 3 — 截取参考音色（前 8 秒）
            p(3, "截取参考音色（8 秒）...")
            ref_voice_path = os.path.join(temp_dir, "ref_voice.wav")
            cmd = [
                self.ffmpeg_path, "-i", vocals_path,
                "-t", "8", "-c", "copy", "-y", ref_voice_path,
            ]
            if not self._run_ffmpeg(cmd, timeout=60):
                return False

            # Step 4 — Whisper 转录
            p(4, "语音转录（Whisper）...")
            try:
                segments = asyncio.run(_mcp_transcribe(vocals_path, mcp_url))
            except Exception as e:
                self.log(f"    ✗ Whisper 失败: {e}")
                return False
            if not segments:
                self.log("    ✗ 转录结果为空")
                return False
            self.log(f"    转录段数: {len(segments)}")

            # Step 5 — LLM 翻译
            p(5, f"LLM 翻译 → {target_lang}...")
            texts = [seg.get("text", "").strip() for seg in segments]
            translated = self._llm_translate(texts, target_lang)

            # Step 6 — 生成 SRT
            p(6, "生成 SRT 字幕...")
            srt_name = f"{stem}_translated_{target_lang}.srt"
            srt_temp = os.path.join(temp_dir, srt_name)
            srt_output = os.path.join(output_folder, srt_name)
            self._write_srt(segments, translated, srt_temp)
            import shutil as _shutil
            _shutil.copy2(srt_temp, srt_output)

            # Step 7 — TTS 批量合成
            p(7, "TTS 批量合成...")
            try:
                wav_list = asyncio.run(_mcp_tts_batch(translated, ref_voice_path, mcp_url))
            except Exception as e:
                self.log(f"    ✗ TTS 失败: {e}")
                return False
            if len(wav_list) != len(segments):
                self.log(f"    ✗ TTS 返回数量不匹配 ({len(wav_list)} vs {len(segments)})")
                return False
            for i, wav_bytes in enumerate(wav_list):
                open(os.path.join(temp_dir, f"tts_seg_{i}.wav"), "wb").write(wav_bytes)

            # Step 8 — 时长对齐
            p(8, "时长对齐...")
            for i, seg in enumerate(segments):
                seg_path = os.path.join(temp_dir, f"tts_seg_{i}.wav")
                aligned_path = os.path.join(temp_dir, f"tts_aligned_{i}.wav")
                target_dur = seg["end"] - seg["start"]
                if not self._align_audio_duration(seg_path, aligned_path, target_dur):
                    return False

            # Step 9 — 音轨拼接（含段间静音填充）
            p(9, "音轨拼接...")
            tts_final = os.path.join(temp_dir, "tts_final.wav")
            if not self._concat_tts_segments(segments, temp_dir, tts_final):
                return False

            # Step 10 — 音频混合
            p(10, "混合背景音乐...")
            mixed_audio = os.path.join(temp_dir, "mixed_audio.wav")
            cmd = [
                self.ffmpeg_path,
                "-i", tts_final, "-i", no_vocals_path,
                "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=first:weights=1.5 1",
                "-y", mixed_audio,
            ]
            if not self._run_ffmpeg(cmd, timeout=300):
                return False

            # Step 11 — 合成输出（SRT→ASS + 替换音轨 + 字幕烧录）
            p(11, "合成最终视频...")
            ass_path = os.path.join(temp_dir, "subtitles.ass")
            self._srt_to_ass(srt_temp, ass_path)
            out_mp4 = os.path.join(output_folder, f"{stem}_translated_{target_lang}.mp4")
            # ASS 路径在 Windows 下需转义反斜杠
            ass_escaped = ass_path.replace("\\", "/").replace(":", "\\:")
            cmd = [
                self.ffmpeg_path,
                "-i", input_path,
                "-i", mixed_audio,
                "-map", "0:v:0", "-map", "1:a:0",
                "-vf", f"ass={ass_escaped}",
                "-c:v", "libx264",
                "-preset", "ultrafast" if self.speed_priority.get() else "medium",
                *self._quality_args(),
                "-c:a", "aac", "-b:a", "192k",
                "-threads", "0",
                "-y", out_mp4,
            ]
            if not self._run_ffmpeg(cmd, timeout=600):
                return False

            size_mb = os.path.getsize(out_mp4) / 1024 / 1024
            self.log(f"    ✓ 输出: {os.path.basename(out_mp4)} ({size_mb:.1f} MB)")
            return True

        except Exception as e:
            self.log(f"    ✗ 异常: {e}")
            return False

    # ── 辅助方法 ──────────────────────────────────────────────

    def _run_ffmpeg(self, cmd: list, timeout: int = 300) -> bool:
        """执行 ffmpeg 命令并记录错误，成功返回 True。"""
        try:
            r = self._run_cmd(cmd, timeout=timeout)
            if r.returncode == 0:
                return True
            self.log(f"    ✗ ffmpeg 错误: {r.stderr[-500:] if r.stderr else '未知'}")
            return False
        except Exception as e:
            self.log(f"    ✗ ffmpeg 异常: {e}")
            return False

    def _get_audio_duration(self, wav_path: str) -> float:
        """用 ffprobe 获取音频时长（秒）。失败返回 0.0。"""
        try:
            cmd = [
                self.ffmpeg_path.replace("ffmpeg", "ffprobe").replace("ffmpeg.exe", "ffprobe.exe"),
                "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", wav_path,
            ]
            r = self._run_cmd(cmd, timeout=30)
            if r.returncode == 0 and r.stdout.strip():
                return float(r.stdout.strip())
        except Exception:
            pass
        return 0.0

    def _align_audio_duration(self, src: str, dst: str, target_dur: float) -> bool:
        """将音频对齐到 target_dur 秒（追加静音或加速）。"""
        actual = self._get_audio_duration(src)
        if actual <= 0 or target_dur <= 0:
            import shutil as _sh
            _sh.copy2(src, dst)
            return True

        ratio = actual / target_dur
        if abs(ratio - 1.0) < 0.02:
            import shutil as _sh
            _sh.copy2(src, dst)
            return True

        if ratio < 1.0:
            # TTS 时长不足：追加静音
            pad = target_dur - actual
            cmd = [
                self.ffmpeg_path,
                "-i", src,
                "-f", "lavfi", "-t", str(pad), "-i", "anullsrc=r=44100:cl=stereo",
                "-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1",
                "-y", dst,
            ]
        else:
            # TTS 时长超出：加速（链式 atempo 处理超范围情况）
            atempo_chain = self._build_atempo_chain(ratio)
            cmd = [
                self.ffmpeg_path,
                "-i", src,
                "-filter:a", atempo_chain,
                "-y", dst,
            ]
        return self._run_ffmpeg(cmd, timeout=120)

    def _build_atempo_chain(self, ratio: float) -> str:
        """构建 atempo 滤镜链（每级范围 [0.5, 2.0]）。"""
        filters = []
        remaining = ratio
        while remaining > 2.0:
            filters.append("atempo=2.0")
            remaining /= 2.0
        while remaining < 0.5:
            filters.append("atempo=0.5")
            remaining /= 0.5
        filters.append(f"atempo={remaining:.6f}")
        return ",".join(filters)

    def _concat_tts_segments(self, segments: list, temp_dir: str, output: str) -> bool:
        """拼接所有对齐后的 TTS 片段，段间插入静音填充。"""
        parts = []
        for i, seg in enumerate(segments):
            aligned = os.path.join(temp_dir, f"tts_aligned_{i}.wav")
            parts.append(aligned)
            # 段间静音
            if i < len(segments) - 1:
                gap = segments[i + 1]["start"] - segments[i]["end"]
                if gap > 0.01:
                    silence_path = os.path.join(temp_dir, f"silence_{i}.wav")
                    cmd = [
                        self.ffmpeg_path,
                        "-f", "lavfi",
                        "-t", f"{gap:.6f}",
                        "-i", "anullsrc=r=44100:cl=stereo",
                        "-y", silence_path,
                    ]
                    if not self._run_ffmpeg(cmd, timeout=30):
                        return False
                    parts.append(silence_path)

        # 写 concat list 文件（使用绝对路径，避免 ffmpeg concat 相对路径二次拼接）
        list_file = os.path.join(temp_dir, "concat_list.txt")
        with open(list_file, "w", encoding="utf-8") as f:
            for p in parts:
                abs_p = os.path.abspath(p)
                f.write(f"file '{abs_p.replace(chr(39), chr(39)+'\\'+chr(39)+chr(39))}'\n")

        cmd = [
            self.ffmpeg_path,
            "-f", "concat", "-safe", "0",
            "-i", list_file,
            "-c", "copy",
            "-y", output,
        ]
        return self._run_ffmpeg(cmd, timeout=300)

    def _write_srt(self, segments: list, translations: list, path: str):
        """将时间戳和译文写入 SRT 文件。"""
        def _ts(sec: float) -> str:
            h = int(sec // 3600)
            m = int((sec % 3600) // 60)
            s = int(sec % 60)
            ms = int(round((sec - int(sec)) * 1000))
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

        with open(path, "w", encoding="utf-8") as f:
            for i, (seg, txt) in enumerate(zip(segments, translations), 1):
                f.write(f"{i}\n")
                f.write(f"{_ts(seg['start'])} --> {_ts(seg['end'])}\n")
                f.write(f"{txt}\n\n")

    def _srt_to_ass(self, srt_path: str, ass_path: str):
        """将 SRT 转为 ASS，使用默认字幕样式（白色、底部居中、黑色描边）。"""
        header = (
            "[Script Info]\n"
            "ScriptType: v4.00+\n"
            "PlayResX: 1920\n"
            "PlayResY: 1080\n\n"
            "[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Default,Arial,24,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,"
            "0,0,0,0,100,100,0,0,1,2,0,2,10,10,20,1\n\n"
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        )

        def _srt_ts_to_ass(ts: str) -> str:
            # "00:00:01,234" → "0:00:01.23"
            ts = ts.strip().replace(",", ".")
            parts = ts.split(":")
            h, m, rest = int(parts[0]), int(parts[1]), parts[2]
            s, ms_str = rest.split(".")
            ms = int(ms_str[:2]) if len(ms_str) >= 2 else int(ms_str) * 10
            return f"{h}:{m:02d}:{int(s):02d}.{ms:02d}"

        with open(srt_path, "r", encoding="utf-8") as f:
            content = f.read()

        import re
        blocks = re.split(r"\n\n+", content.strip())
        events = []
        for block in blocks:
            lines = block.strip().splitlines()
            if len(lines) < 3:
                continue
            times = lines[1].split(" --> ")
            if len(times) != 2:
                continue
            start = _srt_ts_to_ass(times[0])
            end = _srt_ts_to_ass(times[1])
            text = "\\N".join(lines[2:])
            events.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")

        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(header)
            f.write("\n".join(events))
            f.write("\n")

    def _llm_translate(self, texts: list, target_lang: str) -> list:
        """使用 OpenAI 兼容 API 并发翻译，每句最多重试 3 次，最终失败保留原文。"""
        try:
            import openai
        except ImportError:
            self.log("    ✗ 未安装 openai 库，请执行 pip install openai")
            return texts

        lang_map = {"zh": "中文", "en": "英文"}
        lang_name = lang_map.get(target_lang, target_lang)
        client = openai.AsyncOpenAI(
            base_url=self.llm_api_base.get().strip(),
            api_key=self.llm_api_key.get().strip(),
        )
        model = self.llm_model.get().strip()
        log_fn = self.log

        async def _translate_all():
            sem = asyncio.Semaphore(8)

            async def one(i: int, text: str):
                if not text:
                    return i, text
                async with sem:
                    for attempt in range(3):
                        try:
                            resp = await client.chat.completions.create(
                                model=model,
                                messages=[{
                                    "role": "user",
                                    "content": (
                                        f"将以下文本翻译为{lang_name}，保持原文含义，"
                                        f"只输出译文，不要解释。\n{text}"
                                    ),
                                }],
                                temperature=0.3,
                            )
                            return i, resp.choices[0].message.content.strip()
                        except Exception as e:
                            if attempt == 2:
                                log_fn(f"    ⚠ 第 {i+1} 句翻译失败，保留原文: {e}")
                    return i, text

            results = await asyncio.gather(*[one(i, t) for i, t in enumerate(texts)])
            return [r for _, r in sorted(results)]

        return asyncio.run(_translate_all())


def main():
    root = tk.Tk()
    style = ttk.Style()
    style.configure('Accent.TButton', font=('Microsoft YaHei', 10, 'bold'))

    root.withdraw()
    if not show_license_dialog(root):
        root.destroy()
        return

    root.deiconify()
    app = FFmpegVideoEditorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()