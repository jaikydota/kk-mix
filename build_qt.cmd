@echo off

echo ============================================
echo  [0/3] Build _license_core.pyd (Cython) ...
echo ============================================

uv run python setup_cython.py build_ext --inplace
if %ERRORLEVEL% NEQ 0 (
    echo Cython build FAILED!
    pause
    exit /b 1
)

:: Find the generated .pyd file (name includes Python version, e.g. _license_core.cp314-win_amd64.pyd)
for %%f in (_license_core*.pyd) do set PYD_FILE=%%f
if not defined PYD_FILE (
    echo Cannot find compiled .pyd file!
    pause
    exit /b 1
)
echo Cython build OK: %PYD_FILE%

echo.
echo ============================================
echo  [1/3] Packaging kk_qt.py (Qt app) ...
echo ============================================

uv run pyinstaller kk_qt.spec --clean --noconfirm

echo.
if %ERRORLEVEL% == 0 (
    echo Qt app packaged OK! Output: dist\kk_qt\
) else (
    echo Qt app packaging FAILED!
    pause
    exit /b 1
)

echo.
echo ============================================
echo  [2/3] Packaging keygen.py ...
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
    echo Keygen packaged OK! Output: dist\keygen.exe
) else (
    echo Keygen packaging FAILED!
    pause
    exit /b 1
)

echo.
echo ============================================
echo  [3/3] Compressing dist\kk_qt\ ...
echo ============================================
echo Waiting for file release...
timeout /t 5 /nobreak >nul
powershell -Command "$dt = Get-Date -Format 'yyyyMMdd-HHmmss'; $zip = \"dist\kk_qt_$dt.zip\"; Compress-Archive -Path 'dist\kk_qt\*' -DestinationPath $zip -Force; Write-Host \"Done: $zip\""
if %ERRORLEVEL% == 0 (
    echo Compress OK!
) else (
    echo Compress failed. Please zip dist\kk_qt\ manually.
)

echo.
echo ============================================
echo  All done!
echo  Qt app:    dist\kk_qt\
echo  Keygen:    dist\keygen.exe
echo ============================================
echo.
echo  IMPORTANT: Do NOT distribute _license_core.pyx source!
echo  Only distribute the compiled .pyd file.
echo ============================================
pause
