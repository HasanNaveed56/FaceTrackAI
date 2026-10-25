#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
python3 -m pip install -r requirements.txt
python3 download_models.py
echo "Open http://localhost:8000"
python3 -m uvicorn main:app --port 8000
