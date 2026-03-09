@echo off
chcp 65001 >nul
echo 正在打包 kk.py ...

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
    echo 打包成功！输出目录: dist\kk\
    echo 分发时请将整个 dist\kk\ 文件夹打包给用户。
    echo.
    echo 等待文件释放...
    timeout /t 5 /nobreak >nul
    echo 正在压缩 dist\kk\ ...
    powershell -Command "$dt = Get-Date -Format 'yyyyMMdd-HHmmss'; $zip = \"dist\kk_$dt.zip\"; Compress-Archive -Path 'dist\kk\*' -DestinationPath $zip -Force; Write-Host \"压缩完成: $zip\""
    if %ERRORLEVEL% == 0 (
        echo 压缩成功！
    ) else (
        echo 压缩失败，请手动打包 dist\kk\ 文件夹。
    )
) else (
    echo 打包失败，请检查错误信息。
)
pause
