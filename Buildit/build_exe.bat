@echo off
setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
set DIST_DIR=%SCRIPT_DIR%dist
set BUILD_DIR=%SCRIPT_DIR%build
set SPEC_FILE=%SCRIPT_DIR%OutOfOreGPS.spec
set DO_PAUSE=1
if /i "%~1"=="nopause" set DO_PAUSE=0

echo ============================================
echo  Building OutOfOre GPS Tool .exe
echo ============================================
echo.

if not exist "%SPEC_FILE%" (
    echo ERROR: Spec file not found at %SPEC_FILE%
    if %DO_PAUSE%==1 pause
    exit /b 1
)

rmdir /s /q "%DIST_DIR%" 2>nul
rmdir /s /q "%BUILD_DIR%" 2>nul

cd /d "%SCRIPT_DIR%"
pyinstaller OutOfOreGPS.spec --distpath "%DIST_DIR%" --workpath "%BUILD_DIR%" --noconfirm

if %ERRORLEVEL% neq 0 (
    echo.
    echo ERROR: Build failed with error code %ERRORLEVEL%
    if %DO_PAUSE%==1 pause
    exit /b 1
)

echo.
echo ============================================
echo  Build successful!
echo ============================================
echo.
echo Executable: %DIST_DIR%\OutOfOreGPS.exe
echo.
echo NOTE: The .exe will create settings.json in the same
echo directory it is launched from.
echo.

if %DO_PAUSE%==1 pause
exit /b 0
