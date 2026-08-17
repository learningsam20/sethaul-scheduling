#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"
.venv/bin/python - <<'PY'
from app.db import rebuild_database
rebuild_database(force=True)
print("Database rebuilt from seed + migrations + demo users")
PY
