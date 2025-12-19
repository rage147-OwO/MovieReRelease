#!/bin/bash

echo "Installing AiMate dependencies..."
echo

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed"
    echo "Please install Python 3.8+ from your package manager or https://python.org"
    exit 1
fi

echo "✓ Python found"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo "Error: Failed to create virtual environment"
        exit 1
    fi
    echo "✓ Virtual environment created"
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install requirements
echo "Installing Python packages..."
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "Error: Failed to install Python packages"
    exit 1
fi

echo "✓ Python packages installed"

# Install Playwright browsers
echo "Installing Playwright browsers (this may take a few minutes)..."
playwright install chromium
if [ $? -ne 0 ]; then
    echo "Warning: Failed to install Playwright browsers"
    echo "You may need to run: playwright install chromium"
else
    echo "✓ Playwright browsers installed"
fi

# Create logs directory
if [ ! -d "logs" ]; then
    mkdir logs
    echo "✓ Created logs directory"
fi

echo
echo "========================================"
echo "✓ Setup complete!"
echo "========================================"
echo
echo "Next steps:"
echo "1. Copy .env.example to .env and configure your credentials"
echo "2. Run: python quickstart.py to test your setup"
echo "3. Start the server: python -m uvicorn src.main:app --reload"
echo
echo "For help, see README.md or visit the docs at /docs when the server is running."
echo
