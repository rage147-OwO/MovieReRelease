@echo off
echo Installing AiMate dependencies...
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://python.org
    pause
    exit /b 1
)

echo ✓ Python found

REM Create virtual environment if it doesn't exist
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo Error: Failed to create virtual environment
        pause
        exit /b 1
    )
    echo ✓ Virtual environment created
)

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Upgrade pip
echo Upgrading pip...
python -m pip install --upgrade pip

REM Install requirements
echo Installing Python packages...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo Error: Failed to install Python packages
    pause
    exit /b 1
)

echo ✓ Python packages installed

REM Install Playwright browsers
echo Installing Playwright browsers (this may take a few minutes)...
playwright install chromium
if %errorlevel% neq 0 (
    echo Warning: Failed to install Playwright browsers
    echo You may need to run: playwright install chromium
) else (
    echo ✓ Playwright browsers installed
)

REM Create logs directory
if not exist "logs" (
    mkdir logs
    echo ✓ Created logs directory
)

echo.
echo ========================================
echo ✓ Setup complete!
echo ========================================
echo.
echo Next steps:
echo 1. Copy .env.example to .env and configure your credentials
echo 2. Run: python quickstart.py to test your setup
echo 3. Start the server: python -m uvicorn src.main:app --reload
echo.
echo For help, see README.md or visit the docs at /docs when the server is running.
echo.
pause
