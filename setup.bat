@echo off
setlocal enabledelayedexpansion
set PYTHONUTF8=1
title Vibe-Sync Setup Wizard
color 0B

echo ===================================================
echo             Vibe-Sync Setup Wizard
echo ===================================================
echo.

:: 1. Check for Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH. 
    echo Please install Python 3.10+ and try again.
    pause
    exit /b 1
)
echo [OK] Python is installed.

:: 2. Check for Ollama
ollama --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Ollama is not installed or not in PATH. 
    echo Please install Ollama from https://ollama.com/.
    pause
    exit /b 1
)
echo [OK] Ollama is installed.

:: 3. Read configured model from vibe_config.yaml
set MODEL=llama3.2:1b
if exist vibe_config.yaml (
    for /f "tokens=1,2 delims=:" %%a in ('findstr "llm_model:" vibe_config.yaml') do (
        set val=%%b
        set val=!val: =!
        if not "!val!"=="" set MODEL=!val!
    )
)
echo.
echo [INFO] Detected LLM Model: !MODEL!
echo [INFO] Probing model via Ollama...
ollama pull !MODEL!
if %errorlevel% neq 0 (
    echo [WARNING] Failed to pull model !MODEL!. Make sure Ollama daemon is active!
) else (
    echo [OK] Model securely provisioned.
)

:: 4. Check for and install uv
uv --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] 'uv' packaging tool not found. Installing now...
    python -m pip install uv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install uv.
        pause
        exit /b 1
    )
)
echo [OK] uv is ready.

:: 5. Sync environment using uv
echo.
echo [INFO] Resolving cross-platform dependencies via uv...
uv sync
if %errorlevel% neq 0 (
    echo [ERROR] Dependency sync failed. Please check your internet connection.
    pause
    exit /b 1
)
echo [OK] Virtual environment constructed.

:: 6. Launch Configuration Wizard
echo.
echo ===================================================
echo     Launching Rich Command Line Interface...
echo ===================================================
uv run vibe-config init

echo.
echo [TIP] Run 'uv run vibe-config status' to see your dashboard.
echo [TIP] Run 'uv run vibe-monitor' to start background monitoring.
pause
