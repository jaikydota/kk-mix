"""
Cython 编译脚本：把 _license_core.pyx 编译为 _license_core.cp3xx-win_amd64.pyd

用法: uv run python setup_cython.py build_ext --inplace

密钥注入（避免把真实密钥提交进仓库）：
  - KK_LICENSE_SEED     授权码加密种子（任意随机字符串）
  - KK_ADMIN_PASSWORD   keygen 管理员密码（只把 SHA256 写进 .pyd）
  来源优先级：环境变量 > 项目根目录 build_secrets.env（KEY=VALUE，已 gitignore）> 开发默认值
  开发默认值：seed="kk-mix-dev"，密码="admin"，仅供本地调试，不要用于正式发布。
"""
from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

from Cython.Build import cythonize
from setuptools import Extension, setup

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "_license_core.pyx"
BUILD_SRC = ROOT / "build" / "cython_src" / "_license_core.pyx"

DEV_SEED = "kk-mix-dev"
DEV_PASSWORD = "admin"


def _load_secrets() -> tuple[str, str]:
    values: dict[str, str] = {}
    env_file = ROOT / "build_secrets.env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            values[k.strip()] = v.strip()
    seed = os.environ.get("KK_LICENSE_SEED") or values.get("KK_LICENSE_SEED") or ""
    pw = os.environ.get("KK_ADMIN_PASSWORD") or values.get("KK_ADMIN_PASSWORD") or ""

    if not seed or not pw:
        print("[setup_cython] 未提供 KK_LICENSE_SEED / KK_ADMIN_PASSWORD，"
              "使用开发默认值（seed=kk-mix-dev, 密码=admin）。正式发布请务必设置！",
              file=sys.stderr)
    return seed or DEV_SEED, pw or DEV_PASSWORD


def _escape_bytes(data: bytes) -> str:
    """把任意字节渲染成可放进 b"..." 字面量的 \\xNN 转义串。"""
    return "".join("\\x%02x" % b for b in data)


def _render_source() -> Path:
    seed, pw = _load_secrets()
    digest = hashlib.sha256(pw.encode("utf-8")).digest()
    hash_lines = "\n".join(
        "    b'" + _escape_bytes(digest[i:i + 8]) + "'"
        for i in range(0, len(digest), 8)
    )
    seed_literal = _escape_bytes(seed.encode("utf-8"))

    text = SRC.read_text(encoding="utf-8")
    for placeholder in ("@@KK_LICENSE_SEED@@", "@@KK_ADMIN_PW_HASH@@"):
        if placeholder not in text:
            raise SystemExit(f"_license_core.pyx 缺少占位符 {placeholder}")
    text = text.replace("@@KK_LICENSE_SEED@@", seed_literal)
    text = text.replace("@@KK_ADMIN_PW_HASH@@", hash_lines)

    BUILD_SRC.parent.mkdir(parents=True, exist_ok=True)
    BUILD_SRC.write_text(text, encoding="utf-8")
    return BUILD_SRC


extensions = [
    Extension("_license_core", [str(_render_source().relative_to(ROOT)).replace("\\", "/")]),
]

setup(
    ext_modules=cythonize(
        extensions,
        compiler_directives={
            "language_level": "3",
            "boundscheck": False,
            "wraparound": False,
        },
    ),
    packages=[],
    py_modules=[],
)
