# -*- mode: python ; coding: utf-8 -*-
"""Qt 版本 kk.exe 的 PyInstaller 打包脚本。

要点：
  1. 必须先用 `python setup_cython.py build_ext --inplace` 编译 `_license_core.pyd`
  2. PySide6 / Qt DLL 对 UPX 压缩敏感，全部加入 upx_exclude 白名单
  3. 明确 exclude 掉 Tkinter / moviepy，Qt 版本不需要
"""
import glob
import os


# 动态匹配 _license_core.cpXXX-win_amd64.pyd（文件名随 Python 版本变化）
_pyd = next(iter(glob.glob('_license_core*.pyd')), None)
if not _pyd:
    raise SystemExit('_license_core*.pyd 未找到，请先执行 setup_cython.py build_ext --inplace')


a = Analysis(
    ['kk_qt.py'],
    pathex=[],
    binaries=[
        ('ffmpeg.exe', '.'),
        ('ffprobe.exe', '.'),
        (_pyd, '.'),
    ],
    datas=[
        ('assets\\logo.ico', 'assets'),
        ('assets\\logo.png', 'assets'),
        # TTS 参考音（可选，不随仓库分发）：存在时一并打包
        *([('assets\\tts_reference.wav', 'assets')] if os.path.exists('assets/tts_reference.wav') else []),
    ],
    hiddenimports=[
        '_license_core',
        'cryptography',
        'cryptography.hazmat.primitives.ciphers',
        'cryptography.hazmat.primitives.ciphers.algorithms',
        'cryptography.hazmat.primitives.ciphers.modes',
        'cryptography.hazmat.primitives.padding',
        'cryptography.hazmat.backends',
        'cryptography.hazmat.backends.openssl',
        'PySide6.QtSvg',
        'PySide6.QtSvgWidgets',
        'qfluentwidgets',
        'qt.core.translations_en',   # i18n 译文表为函数内延迟导入，显式声明保险
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        '_tkinter',
        'Tkinter',
        'moviepy',
        'imageio_ffmpeg',
        'matplotlib',
        'notebook',
        'IPython',
        'test', 'tests',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)


# UPX 会破坏 PySide6/Qt 部分 DLL，必须排除
_upx_exclude = [
    'Qt6Core.dll',
    'Qt6Gui.dll',
    'Qt6Widgets.dll',
    'Qt6Network.dll',
    'Qt6Svg.dll',
    'Qt6SvgWidgets.dll',
    'Qt6OpenGL.dll',
    'Qt6Pdf.dll',
    'Qt6Qml.dll',
    'Qt6Quick.dll',
    'Qt6DBus.dll',
    'opengl32sw.dll',
    'd3dcompiler_47.dll',
    'vcruntime140.dll',
    'vcruntime140_1.dll',
    'msvcp140.dll',
    'msvcp140_1.dll',
    'msvcp140_2.dll',
    'VCRUNTIME140.dll',
    'VCRUNTIME140_1.dll',
    'MSVCP140.dll',
]


exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='kk_qt',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=_upx_exclude,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets\\logo.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=_upx_exclude,
    name='kk_qt',
)
