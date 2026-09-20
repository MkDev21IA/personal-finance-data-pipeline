#!/bin/bash
echo "==================================================="
echo "  STARTING LOCAL FINANCIAL PIPELINE..."
echo "==================================================="

# Activate virtual environment and run main pipeline
source venv/bin/activate
python main.py
