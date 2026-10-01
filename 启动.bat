@echo off
cd /d "%~dp0"
if not exist "%~dp0python_embeded\pythonw.exe" (
    echo Missing embedded Python. Keep the portable folder complete.
    pause
    exit /b 1
)
"%~dp0python_embeded\python.exe" -c "import PySide6, av, numpy, PIL" 2>"%~dp0startup-error.log"
if errorlevel 1 (
    echo Dependency check failed. See startup-error.log.
    pause
    exit /b 1
)
start "" "%~dp0python_embeded\pythonw.exe" "%~dp0launch.py" %*
