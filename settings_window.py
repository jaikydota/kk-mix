import tkinter as tk
from tkinter import ttk, messagebox


def open_settings(app):
    """打开全局设置窗口"""
    win = tk.Toplevel(app.root)
    win.title("全局设置")
    win.geometry("480x200")
    win.resizable(False, False)
    win.grab_set()  # 模态

    # 使窗口居中于主窗口
    app.root.update_idletasks()
    rx = app.root.winfo_x() + (app.root.winfo_width() - 480) // 2
    ry = app.root.winfo_y() + (app.root.winfo_height() - 200) // 2
    win.geometry(f"+{rx}+{ry}")

    pad = {"padx": 12, "pady": 8}

    # ── MCP 地址 ──────────────────────────────────
    section = ttk.LabelFrame(win, text="MCP 服务配置", padding=10)
    section.pack(fill="x", padx=15, pady=(15, 8))

    ttk.Label(section, text="MCP 地址:").grid(row=0, column=0, sticky="w", **pad)
    entry = ttk.Entry(section, textvariable=app.mcp_url, width=42)
    entry.grid(row=0, column=1, padx=5, pady=8, sticky="ew")
    section.columnconfigure(1, weight=1)

    ttk.Label(
        section,
        text="该地址由视频配音等功能共享使用",
        foreground="gray",
        font=("", 9),
    ).grid(row=1, column=0, columnspan=2, sticky="w", padx=12)

    # ── 按钮区 ────────────────────────────────────
    btn_frame = ttk.Frame(win)
    btn_frame.pack(pady=12)

    def on_save():
        url = app.mcp_url.get().strip()
        if not url:
            messagebox.showwarning("提示", "MCP 地址不能为空", parent=win)
            return
        app.mcp_url.set(url)
        app.log(f"[设置] MCP 地址已保存: {url}")
        win.destroy()

    ttk.Button(btn_frame, text="保存", width=10, command=on_save).pack(side="left", padx=8)
    ttk.Button(btn_frame, text="取消", width=10, command=win.destroy).pack(side="left", padx=8)
