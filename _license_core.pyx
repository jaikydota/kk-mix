# cython: language_level=3
"""
授权核心模块 — Cython 编译为 .pyd，提高逆向门槛。
编译后只分发 _license_core.pyd，不分发 .pyx 源码。
"""

import os
import sys
import json
import base64
import hashlib
import subprocess
from datetime import datetime, timedelta
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend

# ── Cython typed 内部常量（不进 Python 符号表） ──
cdef bytes _APP_SEED = b"REDACTED-SEED"
cdef bytes _KEY_CACHE = b""

cdef bytes _derive_key():
    global _KEY_CACHE
    if _KEY_CACHE:
        return _KEY_CACHE
    _KEY_CACHE = hashlib.sha256(_APP_SEED).digest()[:32]
    return _KEY_CACHE


# ─────────────────────────────────────────────────────────────
# 机器码
# ─────────────────────────────────────────────────────────────

def get_machine_id() -> str:
    """采集本机唯一标识（主板UUID + CPU ID → MD5），格式 XXXX-XXXX-XXXX-XXXX。"""
    raw = ""
    try:
        r = subprocess.run(
            ["wmic", "csproduct", "get", "UUID"],
            capture_output=True, text=True, timeout=5,
        )
        raw += r.stdout.strip()
    except Exception:
        pass
    try:
        r = subprocess.run(
            ["wmic", "cpu", "get", "ProcessorId"],
            capture_output=True, text=True, timeout=5,
        )
        raw += r.stdout.strip()
    except Exception:
        pass
    h = hashlib.md5(raw.encode()).hexdigest()[:16].upper()
    return f"{h[:4]}-{h[4:8]}-{h[8:12]}-{h[12:16]}"


# ─────────────────────────────────────────────────────────────
# 加解密
# ─────────────────────────────────────────────────────────────

def _encrypt_data(data: str) -> str | None:
    cdef bytes key = _derive_key()
    try:
        iv = os.urandom(16)
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        encryptor = cipher.encryptor()
        padder = padding.PKCS7(128).padder()
        padded_data = padder.update(data.encode()) + padder.finalize()
        encrypted = encryptor.update(padded_data) + encryptor.finalize()
        return base64.b64encode(iv + encrypted).decode()
    except Exception:
        return None


def _decrypt_data(encrypted_data: str) -> str | None:
    cdef bytes key = _derive_key()
    try:
        decoded = base64.b64decode(encrypted_data.encode())
        iv = decoded[:16]
        encrypted = decoded[16:]
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        padded_data = decryptor.update(encrypted) + decryptor.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        data = unpadder.update(padded_data) + unpadder.finalize()
        return data.decode()
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────
# 授权码生成（仅 keygen 调用）
# ─────────────────────────────────────────────────────────────

def generate_auth_code(int days = 30, str machine_id = "") -> str | None:
    try:
        license_info = {
            "expire_date": (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S"),
            "create_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "days": days,
            "version": "9.5",
        }
        if machine_id:
            license_info["machine_id"] = machine_id
        return _encrypt_data(json.dumps(license_info))
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────
# 授权码验证
# ─────────────────────────────────────────────────────────────

def verify_auth_code(str auth_code) -> tuple:
    try:
        decrypted_data = _decrypt_data(auth_code)
        if not decrypted_data:
            return False, "授权码无效或损坏，请联系管理员"
        license_info = json.loads(decrypted_data)
        bound_machine = license_info.get("machine_id")
        if bound_machine and bound_machine != get_machine_id():
            return False, "授权码与本机不匹配，请联系管理员重新生成"
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


# ─────────────────────────────────────────────────────────────
# 本地授权文件读写
# ─────────────────────────────────────────────────────────────

cdef str _license_dir():
    d = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "vek")
    os.makedirs(d, exist_ok=True)
    return d


def save_license(str auth_code) -> bool:
    try:
        encrypted = _encrypt_data(auth_code)
        path = os.path.join(_license_dir(), ".vek_li")
        with open(path, 'w') as f:
            f.write(encrypted)
        return True
    except Exception:
        return False


def load_license() -> str | None:
    path = os.path.join(_license_dir(), ".vek_li")
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r') as f:
            encrypted = f.read()
        return _decrypt_data(encrypted)
    except Exception:
        return None


def get_license_info() -> dict | None:
    """加载并完整解密授权信息，返回 dict（含 expire_date / days 等字段），失败返回 None。"""
    auth_code = load_license()
    if not auth_code:
        return None
    try:
        raw = _decrypt_data(auth_code)
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return None


# ─────────────────────────────────────────────────────────────
# keygen 管理员密码验证（哈希比对，不存明文）
# ─────────────────────────────────────────────────────────────

cdef bytes _ADMIN_PW_HASH = (
    b'REDACTED'
    b'REDACTED'
    b'REDACTED'
    b'REDACTED'
)

def verify_admin_password(str pw) -> bool:
    return hashlib.sha256(pw.encode()).digest() == _ADMIN_PW_HASH
