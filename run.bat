@echo off
cd /d "%~dp0"

if exist venv (
    echo Virtual environment already exists
) else (
    echo Creating virtual environment...
    python -m venv venv
)

echo Activating virtual environment...
call venv\Scripts\activate.bat

echo Installing/updating requirements...
pip install -r requirements.txt

echo Running pixel monitor...
python out_of_ore_gps_tool.py