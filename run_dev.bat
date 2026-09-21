@echo off
setlocal
cd /d "%~dp0"
set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHONNOUSERSITE=1"

set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY where python >nul 2>&1 && set "PY=python"
if not defined PY (
    echo No Python found. Install Python 3.10 or newer first.
    pause
    exit /b 1
)

set "FIRST_RUN="
if not exist ".venv\Scripts\python.exe" (
    echo First run: creating TubeClipper's environment...
    %PY% -m venv .venv || (pause & exit /b 1)
    set "FIRST_RUN=1"
)

.venv\Scripts\python.exe -c "import encodings" >nul 2>&1
if errorlevel 1 (
    for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if exist "%%~fD\Lib\encodings\__init__.py" set "PYTHONHOME=%%~fD"
)
.venv\Scripts\python.exe -c "import encodings" >nul 2>&1 || (pause & exit /b 1)

if defined FIRST_RUN (
    .venv\Scripts\python.exe -m pip install --upgrade pip --quiet
    .venv\Scripts\python.exe -m pip install -r requirements.txt || (pause & exit /b 1)
)

.venv\Scripts\python.exe tools\make_icons.py || (pause & exit /b 1)
.venv\Scripts\python.exe TubeClipper.py %*
if errorlevel 1 pause
