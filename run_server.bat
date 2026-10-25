@echo off
cd /d "%~dp0"
python -m pip install -r requirements.txt
python download_models.py
echo Open http://localhost:8000
python -m uvicorn main:app --port 8000
pause
