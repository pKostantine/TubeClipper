@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHONNOUSERSITE=1"

echo.
echo  ============================================
echo   TubeClipper - Windows installer
echo  ============================================
echo.

call build.bat
if not exist "dist\TubeClipper\TubeClipper.exe" goto :fail

.venv-build\Scripts\python.exe -c "import encodings" >nul 2>&1
if errorlevel 1 (
    for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if exist "%%~fD\Lib\encodings\__init__.py" set "PYTHONHOME=%%~fD"
)

.venv-build\Scripts\python.exe tools\version.py --check "dist\TubeClipper\VERSION.txt"
if errorlevel 1 goto :fail
set "TCVER="
set /p TCVER=<"dist\TubeClipper\VERSION.txt"

set "ISCC="
set "PF86=%ProgramFiles(x86)%"
if exist "%PF86%\Inno Setup 6\ISCC.exe" set "ISCC=%PF86%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC for /f "delims=" %%I in ('where ISCC.exe 2^>nul') do set "ISCC=%%I"

if not defined ISCC (
    echo  [X] Inno Setup 6 is not installed.
    echo      Install it from https://jrsoftware.org/isdl.php
    echo      then run make_installer.bat again.
    pause
    exit /b 1
)

del /q "dist\TubeClipper-Setup-*.exe" >nul 2>&1
"%ISCC%" /Q "/DAppVersion=!TCVER!" "installer\TubeClipper.iss"
if errorlevel 1 goto :fail

if not exist "dist\TubeClipper-Setup-!TCVER!.exe" goto :fail
echo.
echo  Done: dist\TubeClipper-Setup-!TCVER!.exe
echo.
pause
exit /b 0

:fail
echo.
echo  [X] Installer build failed. See the lines above.
echo.
pause
exit /b 1
