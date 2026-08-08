@echo off
setlocal EnableExtensions DisableDelayedExpansion

for %%I in ("%~dp0.") do set "ROOT=%%~fI"
set "TARGET=%ROOT%\.cloud"

if not exist "%TARGET%" (
    mkdir "%TARGET%"
    if errorlevel 1 (
        echo [ERROR] Cannot create target directory.
        pause
        exit /b 1
    )
)

robocopy "%ROOT%" "%TARGET%" /MIR /XJ /FFT /R:2 /W:2 /COPY:DAT /DCOPY:DAT /XD "%ROOT%\.git" "%ROOT%\.cloud" "%ROOT%\.runtime" "%ROOT%\__pycache__" "%ROOT%\_python_extract_temp"
set "RC=%ERRORLEVEL%"

if %RC% LEQ 7 (
    echo [OK] Cloud package is up to date.
    echo [INFO] Target: %TARGET%
    pause
    exit /b 0
)

echo [ERROR] Synchronization failed. Robocopy exit code: %RC%
pause
exit /b %RC%
