@echo off
REM Windows launcher for the Shopee FastAPI backend (port 8000)
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo [api] creating virtualenv...
  python -m venv .venv
)
if not exist .venv\.deps_ok (
  echo [api] installing python dependencies...
  .venv\Scripts\python.exe -m pip install --quiet --upgrade pip
  .venv\Scripts\python.exe -m pip install --quiet -r requirements.txt && echo ok> .venv\.deps_ok
)
echo [api] starting uvicorn on :8000
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
