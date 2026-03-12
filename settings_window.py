import json
import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox
from PIL import Image, ImageTk


def _resource_path(relative_path: str) -> str:
    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative_path)


def _settings_path() -> Path:
    """settings.json 与 kk.py / kk.exe 同级目录"""
    if getattr(sys, 'frozen', False):
        base = Path(sys.executable).parent
    else:
        base = Path(sys.argv[0]).parent
    return base / "settings.json"


def load_settings(app):
    """读取 settings.json，填充 app 的 tk.StringVar。若文件不存在则保持默认值。"""
    path = _settings_path()
    if not path.exists():
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        app.mcp_url.set(data.get("mcp_url", "http://localhost:8400/mcp"))
        app.llm_api_base.set(data.get("llm_api_base", "https://api.openai.com/v1"))
        app.llm_api_key.set(data.get("llm_api_key", ""))
        app.llm_model.set(data.get("llm_model", "gpt-4o"))
        app.verbose_log.set(data.get("verbose_log", False))
        app.thread_count.set(str(data.get("thread_count", "1")))
        app.speed_priority.set(data.get("speed_priority", True))
    except Exception:
        pass


def _save_settings(app):
    """将所有设置项写入 settings.json。"""
    path = _settings_path()
    data = {
        "mcp_url": app.mcp_url.get(),
        "llm_api_base": app.llm_api_base.get(),
        "llm_api_key": app.llm_api_key.get(),
        "llm_model": app.llm_model.get(),
        "verbose_log": app.verbose_log.get(),
        "thread_count": app.thread_count.get(),
        "speed_priority": app.speed_priority.get(),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def open_settings(app):
    """打开全局设置窗口"""
    win = tk.Toplevel(app.root)
    win.title("全局设置")
    win.geometry("480x570")
    win.resizable(False, False)
    win.grab_set()  # 模态

    # 使窗口居中于主窗口
    app.root.update_idletasks()
    rx = app.root.winfo_x() + (app.root.winfo_width() - 480) // 2
    ry = app.root.winfo_y() + (app.root.winfo_height() - 540) // 2
    win.geometry(f"+{rx}+{ry}")

    icon_path = _resource_path(os.path.join('assets', 'logo.ico'))
    if os.path.exists(icon_path):
        win.iconbitmap(icon_path)

    header_frame = ttk.Frame(win)
    header_frame.pack(pady=(12, 0))
    logo_path = _resource_path(os.path.join('assets', 'logo.png'))
    if os.path.exists(logo_path):
        img = Image.open(logo_path).resize((28, 28), Image.LANCZOS)
        win._logo = ImageTk.PhotoImage(img)
        ttk.Label(header_frame, image=win._logo).pack(side='left', padx=(0, 6))
    ttk.Label(header_frame, text="全局设置", font=("Microsoft YaHei", 13, "bold")).pack(side='left')

    pad = {"padx": 12, "pady": 6}

    # ── MCP 地址 ──────────────────────────────────
    mcp_section = ttk.LabelFrame(win, text="MCP 服务配置", padding=10)
    mcp_section.pack(fill="x", padx=15, pady=(15, 8))

    ttk.Label(mcp_section, text="MCP 地址:").grid(row=0, column=0, sticky="w", **pad)
    ttk.Entry(mcp_section, textvariable=app.mcp_url, width=42).grid(
        row=0, column=1, padx=5, pady=6, sticky="ew"
    )
    mcp_section.columnconfigure(1, weight=1)

    ttk.Label(
        mcp_section,
        text="该地址由视频配音等功能共享使用",
        foreground="gray",
        font=("", 9),
    ).grid(row=1, column=0, columnspan=2, sticky="w", padx=12)

    # ── LLM 翻译配置 ──────────────────────────────
    llm_section = ttk.LabelFrame(win, text="LLM 翻译配置", padding=10)
    llm_section.pack(fill="x", padx=15, pady=(0, 8))

    ttk.Label(llm_section, text="API Base:").grid(row=0, column=0, sticky="w", **pad)
    ttk.Entry(llm_section, textvariable=app.llm_api_base, width=42).grid(
        row=0, column=1, padx=5, pady=6, sticky="ew"
    )

    ttk.Label(llm_section, text="API Key:").grid(row=1, column=0, sticky="w", **pad)
    ttk.Entry(llm_section, textvariable=app.llm_api_key, width=42, show="*").grid(
        row=1, column=1, padx=5, pady=6, sticky="ew"
    )

    ttk.Label(llm_section, text="模型:").grid(row=2, column=0, sticky="w", **pad)
    ttk.Entry(llm_section, textvariable=app.llm_model, width=42).grid(
        row=2, column=1, padx=5, pady=6, sticky="ew"
    )
    llm_section.columnconfigure(1, weight=1)

    # ── 调试选项 ──────────────────────────────────
    debug_section = ttk.LabelFrame(win, text="调试选项", padding=10)
    debug_section.pack(fill="x", padx=15, pady=(0, 8))

    ttk.Checkbutton(
        debug_section,
        text="打印详细日志",
        variable=app.verbose_log,
    ).grid(row=0, column=0, sticky="w", padx=12, pady=4)

    # ── 性能与稳定性 ──────────────────────────────
    perf_section = ttk.LabelFrame(win, text="性能与稳定性", padding=10)
    perf_section.pack(fill="x", padx=15, pady=(0, 8))

    ttk.Label(perf_section, text="并行线程数:").grid(row=0, column=0, sticky="w", padx=12, pady=4)
    thread_spin = ttk.Spinbox(
        perf_section, textvariable=app.thread_count,
        from_=1, to=16, width=5,
    )
    thread_spin.grid(row=0, column=1, sticky="w", padx=5, pady=4)
    ttk.Label(
        perf_section,
        text="同时处理的文件数量（建议 1-4）",
        foreground="gray",
        font=("", 9),
    ).grid(row=0, column=2, sticky="w", padx=8)

    ttk.Checkbutton(
        perf_section,
        text="极速模式（ultrafast，编码速度更快，文件稍大）",
        variable=app.speed_priority,
    ).grid(row=1, column=0, columnspan=3, sticky="w", padx=12, pady=4)

    # ── 按钮区 ────────────────────────────────────
    btn_frame = ttk.Frame(win)
    btn_frame.pack(pady=12)

    def on_save():
        url = app.mcp_url.get().strip()
        if not url:
            messagebox.showwarning("提示", "MCP 地址不能为空", parent=win)
            return
        app.mcp_url.set(url)
        try:
            _save_settings(app)
            app.log(f"[设置] 已保存到 settings.json")
        except Exception as e:
            messagebox.showerror("保存失败", f"写入 settings.json 失败：{e}", parent=win)
            return
        win.destroy()

    ttk.Button(btn_frame, text="保存", width=10, command=on_save).pack(side="left", padx=8)
    ttk.Button(btn_frame, text="取消", width=10, command=win.destroy).pack(side="left", padx=8)
