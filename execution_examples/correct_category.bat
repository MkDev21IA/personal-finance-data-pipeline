@echo off
chcp 65001 >nul
title Category Corrector - Finances
color 0A

echo ===================================================
echo   STARTING CATEGORY CORRECTOR (WSL)...
echo ===================================================
echo.

REM Resolve current script directory in WSL format and run category corrector
wsl bash -c "cd $(wslpath '%~dp0..') && source venv/bin/activate && python correct_category.py"

echo.
echo ===================================================
echo   EXECUTION COMPLETED. Press any key to exit...
echo ===================================================

pause >nul
