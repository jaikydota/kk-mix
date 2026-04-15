"""
Cython 编译脚本
用法: python setup_cython.py build_ext --inplace
生成: _license_core.cp3xx-win_amd64.pyd
"""

from setuptools import setup, Extension
from Cython.Build import cythonize

extensions = [
    Extension(
        "_license_core",
        ["_license_core.pyx"],
    ),
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
)
