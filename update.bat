@echo off
setlocal enabledelayedexpansion

REM ============================================================
REM  update.bat - Bump version, build exe, push, GitHub release
REM
REM  Usage:
REM    update.bat              Bump patch (1.0.0 -> 1.0.1) and release
REM    update.bat patch        Same as default
REM    update.bat minor        Bump minor (1.0.0 -> 1.1.0)
REM    update.bat major        Bump major (1.0.0 -> 2.0.0)
REM    update.bat 1.2.3        Set exact version and release
REM    update.bat --no-bump    Release current VERSION as-is
REM
REM  First release tip:  update.bat 1.0.0
REM ============================================================

cd /d "%~dp0"
set "ROOT=%CD%"
set "VERSION_FILE=%ROOT%\VERSION"
set "EXE_PATH=%ROOT%\Buildit\dist\OutOfOreGPS.exe"
set "NOTES_FILE=%ROOT%\Buildit\release_notes.md"
set "REPO=tonyoo/out-of-ore-gps-tool"
set "BUMP_MODE=%~1"
if "%BUMP_MODE%"=="" set "BUMP_MODE=patch"

echo ============================================
echo  Out Of Ore GPS Tool - Release Updater
echo ============================================
echo.

REM --- Prerequisites -------------------------------------------------
where git >nul 2>&1
if errorlevel 1 (
    echo ERROR: git not found on PATH.
    exit /b 1
)
where gh >nul 2>&1
if errorlevel 1 (
    echo ERROR: GitHub CLI ^(gh^) not found on PATH.
    exit /b 1
)
where pyinstaller >nul 2>&1
if errorlevel 1 (
    echo ERROR: pyinstaller not found on PATH.
    echo Install with: pip install pyinstaller
    exit /b 1
)

gh auth status >nul 2>&1
if errorlevel 1 (
    echo ERROR: GitHub CLI is not authenticated. Run: gh auth login
    exit /b 1
)

if not exist "%VERSION_FILE%" (
    >"%VERSION_FILE%" echo 1.0.0
    echo Created VERSION file with 1.0.0
)

REM --- Resolve + write new version -----------------------------------
echo [1/6] Resolving version (mode: %BUMP_MODE%)...

for /f "usebackq delims=" %%V in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\scripts\bump_version.ps1" -VersionFile "%VERSION_FILE%" -Mode "%BUMP_MODE%"`) do set "NEW_VERSION=%%V"

if not defined NEW_VERSION (
    echo ERROR: Failed to compute new version.
    exit /b 1
)
if /i "%NEW_VERSION:~0,6%"=="ERROR:" (
    echo %NEW_VERSION%
    exit /b 1
)

set "TAG=v%NEW_VERSION%"
echo       New version: %NEW_VERSION%  ^(tag %TAG%^)

REM Abort if tag already exists locally or on remote
git rev-parse -q --verify "refs/tags/%TAG%" >nul 2>&1
if not errorlevel 1 (
    echo ERROR: Tag %TAG% already exists locally. Choose a higher version.
    exit /b 1
)
for /f "delims=" %%R in ('git ls-remote --tags origin "refs/tags/%TAG%" 2^>nul') do (
    echo ERROR: Tag %TAG% already exists on GitHub.
    exit /b 1
)

REM --- Build exe first (fail before pushing) -------------------------
echo.
echo [2/6] Building executable...
call "%ROOT%\Buildit\build_exe.bat" nopause
if errorlevel 1 (
    echo ERROR: Build failed. VERSION is %NEW_VERSION% but nothing was pushed.
    exit /b 1
)
if not exist "%EXE_PATH%" (
    echo ERROR: Expected exe not found: %EXE_PATH%
    exit /b 1
)

REM --- Commit source + version ---------------------------------------
echo.
echo [3/6] Committing release %TAG%...
git add -A
git status --short

git diff --cached --quiet
if errorlevel 1 (
    git commit -m "Release %TAG%"
    if errorlevel 1 (
        echo ERROR: git commit failed.
        exit /b 1
    )
) else (
    echo       Nothing new to commit.
)

git tag -a "%TAG%" -m "Release %TAG%"
if errorlevel 1 (
    echo ERROR: Failed to create tag %TAG%.
    exit /b 1
)

REM --- Push branch + tag ---------------------------------------------
echo.
echo [4/6] Pushing main and tag to GitHub...
git push origin HEAD
if errorlevel 1 (
    echo ERROR: git push failed.
    exit /b 1
)
git push origin "%TAG%"
if errorlevel 1 (
    echo ERROR: git push tag failed.
    exit /b 1
)

REM --- Create GitHub Release with exe --------------------------------
echo.
echo [5/6] Creating GitHub Release %TAG%...

>"%NOTES_FILE%" echo ## Out Of Ore GPS Tool %TAG%
>>"%NOTES_FILE%" echo.
>>"%NOTES_FILE%" echo ### Download
>>"%NOTES_FILE%" echo - **OutOfOreGPS.exe** - standalone Windows build (no Python required)
>>"%NOTES_FILE%" echo.
>>"%NOTES_FILE%" echo ### Notes
>>"%NOTES_FILE%" echo - Windows may show a SmartScreen warning; choose More info then Run anyway.
>>"%NOTES_FILE%" echo - On first save, settings.json is created next to the exe.
>>"%NOTES_FILE%" echo - Source tag: %TAG%

gh release create "%TAG%" "%EXE_PATH%" --repo "%REPO%" --title "Out Of Ore GPS Tool %TAG%" --notes-file "%NOTES_FILE%"
if errorlevel 1 (
    echo ERROR: gh release create failed. Tag is on GitHub; you can retry:
    echo   gh release create %TAG% "%EXE_PATH%" --repo %REPO% --title "Out Of Ore GPS Tool %TAG%" --notes-file "%NOTES_FILE%"
    exit /b 1
)

del "%NOTES_FILE%" >nul 2>&1

REM --- Done ----------------------------------------------------------
echo.
echo [6/6] Done.
echo ============================================
echo  Released %TAG%
echo ============================================
echo.
echo  Repo:    https://github.com/%REPO%
echo  Release: https://github.com/%REPO%/releases/tag/%TAG%
echo  Asset:   OutOfOreGPS.exe
echo.
exit /b 0
