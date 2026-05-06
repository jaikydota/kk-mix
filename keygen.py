"""
授权码生成器 - 独立 GUI 工具
需要输入管理员密码才能使用
核心加解密逻辑由 _license_core.pyd 提供（Cython 编译，防反编译）
"""

import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, timedelta

import _license_core


def _resource_path(relative_path: str) -> str:
    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative_path)


class KeygenApp:
    """授权码生成器 GUI"""

    def __init__(self, root):
        self.root = root
        self.root.title("出海帮-超大杯混剪系统-授权码生成器")
        self.root.geometry("620x460")
        self.root.resizable(False, False)

        icon_path = _resource_path(os.path.join('assets', 'logo.ico'))
        if os.path.exists(icon_path):
            self.root.iconbitmap(icon_path)

        self.authenticated = False
        self._show_password_screen()

    def _show_password_screen(self):
        """密码验证界面"""
        self.pw_frame = ttk.Frame(self.root, padding=40)
        self.pw_frame.pack(fill='both', expand=True)

        ttk.Label(self.pw_frame, text="管理员验证",
                  font=('Microsoft YaHei', 16, 'bold')).pack(pady=(20, 5))
        ttk.Label(self.pw_frame, text="请输入管理员密码以继续",
                  foreground='gray').pack(pady=(0, 20))

        self.pw_var = tk.StringVar()
        pw_entry = ttk.Entry(self.pw_frame, textvariable=self.pw_var,
                             show='*', width=30, font=('Consolas', 12))
        pw_entry.pack(pady=(0, 10))

        self.pw_status = ttk.Label(self.pw_frame, text="", foreground='red')
        self.pw_status.pack(pady=(0, 15))

        ttk.Button(self.pw_frame, text="确认",
                   command=self._verify_password,
                   style='Accent.TButton').pack()

        pw_entry.focus_set()
        pw_entry.bind('<Return>', lambda e: self._verify_password())

    def _verify_password(self):
        if _license_core.verify_admin_password(self.pw_var.get()):
            self.authenticated = True
            self.pw_frame.destroy()
            self._show_generator_screen()
        else:
            self.pw_status.config(text="密码错误，请重试")

    def _show_generator_screen(self):
        """授权码生成界面"""
        frame = ttk.Frame(self.root, padding=20)
        frame.pack(fill='both', expand=True)

        ttk.Label(frame, text="授权码生成器",
                  font=('Microsoft YaHei', 14, 'bold')).pack(pady=(0, 15))

        mid_frame = ttk.Frame(frame)
        mid_frame.pack(fill='x', pady=(0, 8))
        ttk.Label(mid_frame, text="机器码：",
                  font=('Microsoft YaHei', 10)).pack(side='left')
        self.mid_var = tk.StringVar()
        mid_entry = ttk.Entry(mid_frame, textvariable=self.mid_var,
                              width=24, font=('Consolas', 11))
        mid_entry.pack(side='left', padx=(5, 8))
        ttk.Label(mid_frame, text="(粘贴用户提供的机器码，留空则不绑机器)",
                  foreground='gray', font=('Microsoft YaHei', 8)).pack(side='left')

        days_frame = ttk.Frame(frame)
        days_frame.pack(fill='x', pady=(0, 10))
        ttk.Label(days_frame, text="授权天数：",
                  font=('Microsoft YaHei', 10)).pack(side='left')
        self.days_var = tk.StringVar(value="30")
        days_entry = ttk.Entry(days_frame, textvariable=self.days_var,
                               width=10, font=('Consolas', 11))
        days_entry.pack(side='left', padx=(5, 10))

        presets = [("30天", "30"), ("90天", "90"), ("180天", "180"), ("365天", "365")]
        for text, val in presets:
            ttk.Button(days_frame, text=text,
                       command=lambda v=val: self.days_var.set(v)).pack(side='left', padx=2)

        ttk.Button(frame, text="生成授权码", command=self._generate,
                   style='Accent.TButton').pack(pady=(5, 10))

        self.result_text = tk.Text(frame, height=5, width=60,
                                   font=('Consolas', 9), wrap='char')
        self.result_text.pack(fill='x', pady=(0, 5))

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill='x')
        ttk.Button(btn_frame, text="复制授权码",
                   command=self._copy_code).pack(side='left', padx=2)

        self.info_label = ttk.Label(frame, text="", foreground='green')
        self.info_label.pack(pady=(10, 0))

        mid_entry.focus_set()
        days_entry.bind('<Return>', lambda e: self._generate())

    def _generate(self):
        try:
            days = int(self.days_var.get())
            if days <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("错误", "请输入有效的天数（正整数）")
            return

        machine_id = self.mid_var.get().strip()
        auth_code = _license_core.generate_auth_code(days, machine_id=machine_id)
        if auth_code:
            self.result_text.delete('1.0', 'end')
            self.result_text.insert('1.0', auth_code)
            expire = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
            bind_info = f"，绑定机器码：{machine_id}" if machine_id else "，未绑定机器（通用码）"
            self.info_label.config(
                text=f"生成成功！有效期 {days} 天，到期时间：{expire}{bind_info}",
                foreground='green')
        else:
            self.info_label.config(text="生成失败，请重试", foreground='red')

    def _copy_code(self):
        code = self.result_text.get('1.0', 'end').strip()
        if code:
            self.root.clipboard_clear()
            self.root.clipboard_append(code)
            self.info_label.config(text="已复制到剪贴板！", foreground='blue')
        else:
            self.info_label.config(text="没有可复制的授权码", foreground='red')


def main():
    root = tk.Tk()
    style = ttk.Style()
    style.configure('Accent.TButton', font=('Microsoft YaHei', 10, 'bold'))
    app = KeygenApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
