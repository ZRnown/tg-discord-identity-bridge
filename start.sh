#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# Check config
if [ ! -f config.json ]; then
    echo "[!] config.json not found — copying config.sample.json"
    cp config.sample.json config.json
    echo "[!] Edit config.json with your API keys, tokens, and group IDs, then re-run."
    exit 1
fi

# Install deps
if [ ! -f bridge/.deps_installed ]; then
    echo "[*] Installing Python dependencies..."
    pip install -r requirements.txt -q
    touch bridge/.deps_installed
fi

echo "[*] Starting bridge..."
python -m bridge "$@"
