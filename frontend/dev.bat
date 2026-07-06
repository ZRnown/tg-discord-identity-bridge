@echo off
cd /d "%~dp0"
echo [*] Starting frontend dev server (port 3001)...
cd frontend
if not exist node_modules (
    echo [*] Installing frontend dependencies...
    call pnpm install
)
call pnpm dev
