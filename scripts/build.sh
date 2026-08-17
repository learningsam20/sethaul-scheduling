#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

backend/.venv/bin/pip install -r backend/requirements.txt
(cd frontend && npm ci && npm run build)

echo "Build complete."
echo "  Frontend: frontend/dist"
echo "  Serve via: backend/.venv/bin/uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000"
