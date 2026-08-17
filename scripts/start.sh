#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

if [[ ! -d backend/.venv ]]; then
  python3 -m venv backend/.venv
  backend/.venv/bin/pip install -r backend/requirements.txt
fi

if [[ ! -d frontend/node_modules ]]; then
  (cd frontend && npm install)
fi

(
  cd backend
  .venv/bin/python - <<'PY'
from app.db import ensure_database
ensure_database()
print("database ready")
PY
)

kill_port() {
  local port="$1"
  local pids
  pids=$(lsof -ti tcp:"$port" 2>/dev/null || true)
  if [[ -n "$pids" ]]; then
    echo "Stopping existing process on port $port (PID: $pids)..."
    kill -9 $pids 2>/dev/null || true
  fi
}

kill_port 8000
kill_port 5173

backend/.venv/bin/uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload &
API_PID=$!

(cd frontend && npm run dev -- --host 127.0.0.1 --port 5173) &
UI_PID=$!

cleanup() {
  kill "$API_PID" "$UI_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo ""
echo "SetuHaul running:"
echo "  UI  http://127.0.0.1:5173"
echo "  API http://127.0.0.1:8000/api/health"
echo "  Demo password: pin1234  (try driver.ravi / ops / warehouse.jai / admin)"
echo ""
wait
