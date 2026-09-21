@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHONNOUSERSITE=1"

echo.
echo  ============================================
echo   TubeClipper - Windows build
echo  ============================================
echo.

set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY where python >nul 2>&1 && set "PY=python"
if not defined PY (
    echo  [X] Python 3.10 or newer is required.
    pause
    exit /b 1
)

if not exist ".venv-build\Scripts\python.exe" (
    echo  Creating build environment...
    %PY% -m venv .venv-build || goto :fail
)
set "VPY=.venv-build\Scripts\python.exe"

rem Some Windows Store/Python repair installs leave python.exe in C:\Python
rem while the standard library remains under LocalAppData. Recover that
rem split installation without changing the user's global environment.
"%VPY%" -c "import encodings" >nul 2>&1
if errorlevel 1 (
    for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if exist "%%~fD\Lib\encodings\__init__.py" set "PYTHONHOME=%%~fD"
)
"%VPY%" -c "import encodings" >nul 2>&1 || goto :fail

echo  Installing dependencies...
"%VPY%" -m pip install --upgrade pip --quiet || goto :fail
"%VPY%" -m pip install -r requirements.txt --quiet || goto :fail

echo  Generating app icons...
"%VPY%" tools\make_icons.py || goto :fail

echo  Preparing bundled ffmpeg...
"%VPY%" tools\fetch_ffmpeg.py || goto :fail

set "VERFILE=%TEMP%\tubeclipper_version.txt"
if exist "%VERFILE%" del /q "%VERFILE%"
"%VPY%" tools\version.py --write "%VERFILE%" >nul || goto :fail
set "TCVER="
set /p TCVER=<"%VERFILE%"
if exist "%VERFILE%" del /q "%VERFILE%"
if not defined TCVER goto :fail
echo  Building TubeClipper !TCVER!...

"%VPY%" -m tests.test_engine || goto :fail
set QT_QPA_PLATFORM=offscreen
"%VPY%" -m tests.test_app || goto :fail
set QT_QPA_PLATFORM=

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
"%VPY%" -m PyInstaller --clean --noconfirm TubeClipper.spec || goto :fail

if not exist "dist\TubeClipper\TubeClipper.exe" goto :fail
if not exist "dist\TubeClipper\TubeClipper-check.exe" goto :fail
"%VPY%" tools\version.py --write "dist\TubeClipper\VERSION.txt" >nul

echo.
echo  Verifying the frozen build...
"dist\TubeClipper\TubeClipper-check.exe" --selftest || goto :fail

echo.
echo  ============================================
echo   Done: dist\TubeClipper\TubeClipper.exe
echo  ============================================
echo.
pause
exit /b 0

:fail
echo.
echo  [X] Build failed. See the lines above.
echo.
pause
exit /b 1
