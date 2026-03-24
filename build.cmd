@echo off
chcp 65001 >nul

echo ============================================
echo  [1/2] 正在打包 kk.py (主程序) ...
echo ============================================

uv run pyinstaller ^
    --onedir ^
    --windowed ^
    --add-binary "ffmpeg.exe;." ^
    --add-binary "ffprobe.exe;." ^
    --add-data "assets\logo.ico;assets" ^
    --icon "assets\logo.ico" ^
    --name kk ^
    --clean ^
    kk.py

echo.
if %ERRORLEVEL% == 0 (
    echo 主程序打包成功！输出目录: dist\kk\
) else (
    echo 主程序打包失败，请检查错误信息。
    pause
    exit /b 1
)

echo.
echo ============================================
echo  [2/2] 正在打包 keygen.py (授权码生成器) ...
echo ============================================

uv run pyinstaller ^
    --onefile ^
    --windowed ^
    --add-data "assets\logo.ico;assets" ^
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
echo  正在压缩主程序 dist\kk\ ...
echo ============================================
echo 等待文件释放...
timeout /t 5 /nobreak >nul
powershell -Command "$dt = Get-Date -Format 'yyyyMMdd-HHmmss'; $zip = \"dist\kk_$dt.zip\"; Compress-Archive -Path 'dist\kk\*' -DestinationPath $zip -Force; Write-Host \"压缩完成: $zip\""
if %ERRORLEVEL% == 0 (
    echo 压缩成功！
) else (
    echo 压缩失败，请手动打包 dist\kk\ 文件夹。
)

echo.
echo ============================================
echo  全部打包完成！
echo  主程序:       dist\kk\
echo  授权码生成器: dist\keygen.exe
echo ============================================
pause
