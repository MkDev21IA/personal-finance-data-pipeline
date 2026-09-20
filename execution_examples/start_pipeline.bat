@echo off
chcp 65001 >nul
title Financial Automation Pipeline
color 0A

echo ===================================================
echo   INITIALIZING LINUX (WSL) PIPELINE ENVIRONMENT...
echo ===================================================
echo.

REM Resolve current script directory in WSL format and execute orchestrator
wsl bash -c "cd $(wslpath '%~dp0..') && source venv/bin/activate && python main.py"

pause >nul
