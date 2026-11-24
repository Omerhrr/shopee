#!/bin/bash
# Shopee API - FastAPI + SQLAlchemy backend service (port 8000)
set -e
cd "$(dirname "$0")"

# Create project-local venv (persists under /home/z/my-project) and install deps once
if [ ! -x .venv/bin/python ]; then
  echo "[api] creating virtualenv..."
  python3 -m venv .venv
fi
if [ ! -f .venv/.deps_ok ]; then
  echo "[api] installing python dependencies..."
  .venv/bin/pip install --quiet --upgrade pip
  .venv/bin/pip install --quiet -r requirements.txt
  touch .venv/.deps_ok
fi

echo "[api] starting uvicorn on :8000"
exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
