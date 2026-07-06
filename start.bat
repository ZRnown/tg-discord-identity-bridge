@echo off
echo ============================================
echo  TG -^> Discord Identity Bridge
echo ============================================

cd /d "%~dp0"

REM Check for config
if not exist config.json (
    echo [!] config.json not found — copying config.sample.json
    copy config.sample.json config.json
    echo [!] Edit config.json with your API keys, tokens, and group IDs, then re-run.
    pause
    exit /b 1
)

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [!] Python not found — install Python 3.10+ first
    pause
    exit /b 1
)

REM Install dependencies if needed
if not exist bridge\.deps_installed (
    echo [*] Installing Python dependencies...
    pip install -r requirements.txt --quiet
    type nul > bridge\.deps_installed
    echo [*] Done.
)

echo [*] Starting bridge...
python -m bridge

pause
