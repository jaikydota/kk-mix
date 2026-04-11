"""
授权码生成器 - 独立 GUI 工具
需要输入管理员密码才能使用
"""

import os
import sys
import json
import base64
import hashlib
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, timedelta
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend

ADMIN_PASSWORD = "REDACTED"


def _resource_path(relative_path: str) -> str:
    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative_path)


class LicenseGenerator:
    """授权码生成器"""

    def __init__(self, app_name="REDACTED-SEED"):
        self.app_name = app_name
        self.secret_key = self._generate_key()

    def _generate_key(self):
        key_base = hashlib.sha256(self.app_name.encode()).digest()
        return key_base[:32]

    def _encrypt_data(self, data):
        try:
            iv = os.urandom(16)
            cipher = Cipher(algorithms.AES(self.secret_key), modes.CBC(iv), backend=default_backend())
            encryptor = cipher.encryptor()
            padder = padding.PKCS7(128).padder()
            padded_data = padder.update(data.encode()) + padder.finalize()
            encrypted = encryptor.update(padded_data) + encryptor.finalize()
            return base64.b64encode(iv + encrypted).decode()
        except Exception:
            return None

    def generate_auth_code(self, days=30):
        try:
            license_info = {
                "expire_date": (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S"),
                "create_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "days": days,
                "version": "7.0"
            }
            return self._encrypt_data(json.dumps(license_info))
        except Exception:
            return None


class KeygenApp:
    """授权码生成器 GUI"""

    def __init__(self, root):
        self.root = root
        self.root.title("出海帮-巨量剪辑工具-授权码生成器")
        self.root.geometry("560x420")
        self.root.resizable(False, False)

        icon_path = _resource_path(os.path.join('assets', 'logo.ico'))
        if os.path.exists(icon_path):
            self.root.iconbitmap(icon_path)

        self.generator = LicenseGenerator()
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
        if self.pw_var.get() == ADMIN_PASSWORD:
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

        days_entry.focus_set()
        days_entry.bind('<Return>', lambda e: self._generate())

    def _generate(self):
        try:
            days = int(self.days_var.get())
            if days <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("错误", "请输入有效的天数（正整数）")
            return

        auth_code = self.generator.generate_auth_code(days)
        if auth_code:
            self.result_text.delete('1.0', 'end')
            self.result_text.insert('1.0', auth_code)
            expire = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
            self.info_label.config(
                text=f"生成成功！有效期 {days} 天，到期时间：{expire}",
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
