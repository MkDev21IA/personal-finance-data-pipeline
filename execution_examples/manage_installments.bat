@echo off
chcp 65001 >nul
title Installment Manager - Finances
color 0A

echo ===================================================
echo   STARTING INSTALLMENT MANAGER (WSL)...
echo ===================================================
echo.

REM Resolve current script directory in WSL format and run installment manager
wsl bash -c "cd $(wslpath '%~dp0..') && source venv/bin/activate && python manage_portions.py"

pause >nul
