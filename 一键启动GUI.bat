@echo off
:: Project launcher - calls pyloader.ps1 to ensure env is ready, then starts app
set "ROOT=%~dp0"
set "ENV=%ROOT%.runtime\python"
set "APP=%ROOT%app.pyw"
"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%ROOT%pyloader.ps1"
if %errorlevel% neq 0 (
    echo [ERROR] 部署没有完成。请查看上方以 [ERROR] 开头的具体原因，并阅读同目录的必看说明.txt。
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
    echo [ERROR] 程序启动失败。请重新运行一键启动GUI.bat，并提供窗口中的错误内容。
    pause
)
