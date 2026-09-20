@echo off
setlocal

echo ==========================================
echo Installing Python dependencies
echo ==========================================
echo.

python -m pip install --upgrade pip

echo.
echo Installing required packages...
echo.

python -m pip install "PySide6>=6.6,<7.0" "psutil>=5.9" "pytest>=7.4" "pyinstaller>=6.0"

echo.
echo ==========================================
echo Installation completed.
echo ==========================================
echo.

pause