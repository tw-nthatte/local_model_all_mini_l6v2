#!/bin/bash
# RBI Master Directives Monitor - Startup Script

echo "========================================="
echo "RBI Master Directives Monitor"
echo "========================================="

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python version: $PYTHON_VERSION"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install/upgrade dependencies
echo "Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

# Create directories if they don't exist
mkdir -p logs data/pdfs

# Initialize database
echo "Initializing database..."
python3 << 'EOF'
from app.database import init_db
from app.config import setup_logging
setup_logging()
init_db()
print("✓ Database initialized")
EOF

# Start application
echo ""
echo "========================================="
echo "Starting application..."
echo "Dashboard: http://localhost:8000"
echo "API Docs: http://localhost:8000/docs"
echo "========================================="
echo ""

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
