@echo off
setlocal
cd /d "%~dp0"
set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHONNOUSERSITE=1"

if not exist ".venv\Scripts\python.exe" (
    echo Run run_dev.bat once first to create the environment.
    pause
    exit /b 1
)

.venv\Scripts\python.exe -c "import encodings" >nul 2>&1
if errorlevel 1 (
    for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if exist "%%~fD\Lib\encodings\__init__.py" set "PYTHONHOME=%%~fD"
)
.venv\Scripts\python.exe -c "import encodings" >nul 2>&1 || (pause & exit /b 1)

echo === engine ===
.venv\Scripts\python.exe -m tests.test_engine
if errorlevel 1 goto :fail
echo.
echo === app ===
set QT_QPA_PLATFORM=offscreen
.venv\Scripts\python.exe -m tests.test_app
if errorlevel 1 goto :fail
echo.
echo All tests passed.
pause
exit /b 0

:fail
echo.
echo Tests failed.
pause
exit /b 1
