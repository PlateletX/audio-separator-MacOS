@echo off
:: Project launcher - calls bootstrap.ps1 to ensure env is ready, then starts app
set "ROOT=%~dp0"
set "ENV=%ROOT%python_env"
set "APP=%ROOT%app.pyw"
"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%ROOT%bootstrap.ps1"
if %errorlevel% neq 0 (
    echo [ERROR] Deployment failed!
    pause
    exit /b 1
)

:: Isolate runtime environment before launching app
set "PYTHONNOUSERSITE=1"
set "PIP_USER=0"
set "PYTHONPATH="
set "PYTHONHOME="
set "VIRTUAL_ENV="
set "CONDA_PREFIX="
set "CONDA_DEFAULT_ENV="

:: Keep strict PATH isolation. FFmpeg runtime is resolved inside Python via imageio-ffmpeg.
set "PATH=%ENV%;%ENV%\Scripts;%SystemRoot%\system32;%SystemRoot%"

:: Use pythonw to avoid persistent console window during GUI runtime
if exist "%ENV%\pythonw.exe" (
    start "" /B "%ENV%\pythonw.exe" "%APP%"
    exit /b 0
)

"%ENV%\python.exe" "%APP%"
if %errorlevel% neq 0 (
    echo [ERROR] App exited with an error.
    pause
)
