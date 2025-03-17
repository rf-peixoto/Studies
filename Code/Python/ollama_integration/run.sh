#!/bin/bash

# Create a virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate the virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip to the latest version
echo "Upgrading pip..."
pip install --upgrade pip

# Upgrade setuptools and wheel to avoid build issues
echo "Upgrading setuptools and wheel..."
pip install --upgrade setuptools wheel

# Install the required dependencies
echo "Installing dependencies from requirements.txt..."
pip install -r requirements.txt

# Run the main script
echo "Running main.py..."
python main.py

# Optionally, deactivate the virtual environment when done
deactivate
