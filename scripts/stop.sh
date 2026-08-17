#!/usr/bin/env bash
set -euo pipefail

kill_port() {
  local port="$1"
  local pids
  pids=$(lsof -ti tcp:"$port" 2>/dev/null || true)
  if [[ -n "$pids" ]]; then
    echo "Stopping process(es) on port $port (PID: $pids)..."
    kill -9 $pids 2>/dev/null || true
  else
    echo "Port $port is clear."
  fi
}

echo "Stopping SetuHaul services..."
kill_port 8000
kill_port 5173
echo "All SetuHaul processes stopped."
