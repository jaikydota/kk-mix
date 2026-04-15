# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['kk.py'],
    pathex=[],
    binaries=[('ffmpeg.exe', '.'), ('ffprobe.exe', '.'), ('_license_core.cp314-win_amd64.pyd', '.')],
    datas=[('assets\\logo.ico', 'assets'), ('docs\\使用前必看.txt', 'docs')],
    hiddenimports=['_license_core', 'cryptography', 'cryptography.hazmat.primitives.ciphers', 'cryptography.hazmat.primitives.ciphers.algorithms', 'cryptography.hazmat.primitives.ciphers.modes', 'cryptography.hazmat.primitives.padding', 'cryptography.hazmat.backends', 'cryptography.hazmat.backends.openssl'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='kk',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
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
    upx_exclude=[],
    name='kk',
)
