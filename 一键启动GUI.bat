@echo off
:: Project launcher - calls bootstrap.ps1 to ensure env is ready, then starts app
set "ROOT=%~dp0"
set "ENV=%ROOT%python_env"
set "APP=%ROOT%app.pyw"
set "FFMPEG_PATH_FILE=%ROOT%ffmpeg_path.txt"
set "FFMPEG_BIN="
set "SYSTEM_FFMPEG_BIN="
"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%ROOT%bootstrap.ps1"
if %errorlevel% neq 0 (
    echo [ERROR] Deployment failed!
    pause
    exit /b 1
)

:: Read resolved ffmpeg bin path from init_env output (if present)
if exist "%FFMPEG_PATH_FILE%" (
    set /p FFMPEG_BIN=<"%FFMPEG_PATH_FILE%"
)

:: Safety fallback: detect system ffmpeg from current shell before PATH isolation
if not defined FFMPEG_BIN (
    for /f "delims=" %%I in ('where ffmpeg 2^>nul') do (
        for %%J in ("%%I") do set "SYSTEM_FFMPEG_BIN=%%~dpJ"
        goto :ffmpeg_detect_done
    )
)
:ffmpeg_detect_done
if defined SYSTEM_FFMPEG_BIN set "SYSTEM_FFMPEG_BIN=%SYSTEM_FFMPEG_BIN:~0,-1%"

:: Isolate runtime environment before launching app
set "PYTHONNOUSERSITE=1"
set "PIP_USER=0"
set "PYTHONPATH="
set "PYTHONHOME="
set "VIRTUAL_ENV="
set "CONDA_PREFIX="
set "CONDA_DEFAULT_ENV="

:: Keep strict PATH isolation but include ffmpeg path with priority:
:: 1) ffmpeg_path.txt (written by init_env.py)
:: 2) detected system ffmpeg
:: 3) local project fallback ffmpeg\bin
if defined FFMPEG_BIN (
    set "PATH=%ENV%;%ENV%\Scripts;%FFMPEG_BIN%;%SystemRoot%\system32;%SystemRoot%"
) else if defined SYSTEM_FFMPEG_BIN (
    set "PATH=%ENV%;%ENV%\Scripts;%SYSTEM_FFMPEG_BIN%;%SystemRoot%\system32;%SystemRoot%"
) else (
    set "PATH=%ENV%;%ENV%\Scripts;%ROOT%ffmpeg\bin;%SystemRoot%\system32;%SystemRoot%"
)

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
