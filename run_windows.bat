@echo off
setlocal
cd /d "%~dp0"
where uv >nul 2>nul
if not errorlevel 1 (
  set "UV_CACHE_DIR=%~dp0.uv-cache"
  uv run --no-project --python 3.8 --with-requirements requirements.txt game.py %*
  if errorlevel 1 pause
  exit /b %errorlevel%
)
if not exist .venv\Scripts\python.exe (
  python -m venv .venv
  if errorlevel 1 goto :python_error
)
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto :install_error
.venv\Scripts\python.exe game.py %*
exit /b %errorlevel%
:python_error
echo Python 3.8 or newer is required. See README.md.
pause
exit /b 1
:install_error
echo Package installation failed. Check internet access and README.md.
pause
exit /b 1
