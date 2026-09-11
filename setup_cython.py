"""
Cython 编译脚本：把 _license_core.pyx 编译为 _license_core.cp3xx-win_amd64.pyd

用法: uv run python setup_cython.py build_ext --inplace

编译时注入（避免把真实密钥提交进仓库）：
  - KK_LICENSE_SEED     授权码加密种子（任意随机字符串），默认 "kk-mix-dev"
  - KK_LICENSE_ENABLED  是否启用授权校验，1/true/yes/on 为启用，默认关闭
  来源优先级：环境变量 > 项目根目录 build_secrets.env（KEY=VALUE，已 gitignore）> 默认值

开关之所以放在编译期而不是 settings.json / 环境变量：运行期可改的位置
终端用户自己就能关掉授权校验，等于没有校验。烧进 .pyd 后与其余授权逻辑同等强度。
默认关闭是为了让开源用户 clone 后直接跑通；正式发布前务必设 KK_LICENSE_ENABLED=1。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from Cython.Build import cythonize
from setuptools import Extension, setup

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "_license_core.pyx"
BUILD_SRC = ROOT / "build" / "cython_src" / "_license_core.pyx"

DEV_SEED = "kk-mix-dev"


TRUTHY = {"1", "true", "yes", "on"}


def _load_secrets() -> tuple[str, bool]:
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
    raw_enabled = os.environ.get("KK_LICENSE_ENABLED") or values.get("KK_LICENSE_ENABLED") or ""
    enabled = raw_enabled.strip().lower() in TRUTHY

    if enabled and not seed:
        print("[setup_cython] 警告：已启用授权校验，但未提供 KK_LICENSE_SEED，"
              "正在使用公开的默认种子 kk-mix-dev —— 任何人都能伪造授权码！",
              file=sys.stderr)
    print(f"[setup_cython] 授权校验：{'启用' if enabled else '关闭'}"
          f"（KK_LICENSE_ENABLED={raw_enabled or '未设置'}）"
          f"，种子：{'自定义' if seed else '默认 kk-mix-dev'}", file=sys.stderr)
    return seed or DEV_SEED, enabled


def _escape_bytes(data: bytes) -> str:
    """把任意字节渲染成可放进 b"..." 字面量的 \\xNN 转义串。"""
    return "".join("\\x%02x" % b for b in data)


def _render_source() -> Path:
    seed, enabled = _load_secrets()
    seed_literal = _escape_bytes(seed.encode("utf-8"))

    text = SRC.read_text(encoding="utf-8")
    for placeholder in ("@@KK_LICENSE_SEED@@", "@@KK_LICENSE_ENABLED@@"):
        if placeholder not in text:
            raise SystemExit(f"_license_core.pyx 缺少占位符 {placeholder}")
    text = text.replace("@@KK_LICENSE_SEED@@", seed_literal)
    text = text.replace("@@KK_LICENSE_ENABLED@@", "1" if enabled else "0")

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
