@echo off
chcp 65001 >nul

echo ============================================
echo  [0/3] 编译 _license_core.pyd (Cython) ...
echo ============================================

uv run python setup_cython.py build_ext --inplace
if %ERRORLEVEL% NEQ 0 (
    echo Cython 编译失败！请确认已安装 cython 和 C 编译器。
    pause
    exit /b 1
)

:: 查找生成的 .pyd 文件（文件名含 Python 版本号，如 _license_core.cp314-win_amd64.pyd）
for %%f in (_license_core*.pyd) do set PYD_FILE=%%f
if not defined PYD_FILE (
    echo 找不到编译后的 .pyd 文件！
    pause
    exit /b 1
)
echo Cython 编译成功: %PYD_FILE%

echo.
echo ============================================
echo  [1/3] 正在打包 kk_qt.py (Qt 主程序) ...
echo ============================================

uv run pyinstaller kk_qt.spec --clean --noconfirm

echo.
if %ERRORLEVEL% == 0 (
    echo Qt 主程序打包成功！输出目录: dist\kk_qt\
) else (
    echo Qt 主程序打包失败，请检查错误信息。
    pause
    exit /b 1
)

echo.
echo ============================================
echo  [2/3] 正在打包 keygen.py (授权码生成器) ...
echo ============================================

uv run pyinstaller ^
    --onefile ^
    --windowed ^
    --add-binary "%PYD_FILE%;." ^
    --add-data "assets\logo.ico;assets" ^
    --hidden-import "_license_core" ^
    --hidden-import "cryptography" ^
    --hidden-import "cryptography.hazmat.primitives.ciphers" ^
    --hidden-import "cryptography.hazmat.primitives.ciphers.algorithms" ^
    --hidden-import "cryptography.hazmat.primitives.ciphers.modes" ^
    --hidden-import "cryptography.hazmat.primitives.padding" ^
    --hidden-import "cryptography.hazmat.backends" ^
    --hidden-import "cryptography.hazmat.backends.openssl" ^
    --icon "assets\logo.ico" ^
    --name keygen ^
    --clean ^
    keygen.py

echo.
if %ERRORLEVEL% == 0 (
    echo 授权码生成器打包成功！输出: dist\keygen.exe
) else (
    echo 授权码生成器打包失败，请检查错误信息。
    pause
    exit /b 1
)

echo.
echo ============================================
echo  [3/3] 正在压缩主程序 dist\kk_qt\ ...
echo ============================================
echo 等待文件释放...
timeout /t 5 /nobreak >nul
powershell -Command "$dt = Get-Date -Format 'yyyyMMdd-HHmmss'; $zip = \"dist\kk_qt_$dt.zip\"; Compress-Archive -Path 'dist\kk_qt\*' -DestinationPath $zip -Force; Write-Host \"压缩完成: $zip\""
if %ERRORLEVEL% == 0 (
    echo 压缩成功！
) else (
    echo 压缩失败，请手动打包 dist\kk_qt\ 文件夹。
)

echo.
echo ============================================
echo  全部打包完成！
echo  Qt 主程序:    dist\kk_qt\
echo  授权码生成器: dist\keygen.exe
echo ============================================
echo.
echo  重要：请勿将 _license_core.pyx 源码分发给用户！
echo  只分发编译后的 .pyd 文件。
echo ============================================
pause
