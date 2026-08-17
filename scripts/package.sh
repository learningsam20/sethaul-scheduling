#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

./scripts/build.sh

STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="dist/setuhaul-${STAMP}"
mkdir -p "$OUT"

rsync -a --exclude '.venv' --exclude 'node_modules' --exclude '__pycache__' \
  --exclude '.git' --exclude 'dist' --exclude '.env' \
  backend "$OUT/"
rsync -a frontend/dist "$OUT/frontend-dist"
cp -f .env.example "$OUT/.env.example"
echo "Note: .env is not packaged. Rotate OpenRouter / Geoapify / LangSmith keys before any recording or distribution."
cp -f scripts/start.sh scripts/reset_db.sh scripts/deploy.sh "$OUT/" 2>/dev/null || true
cp -f README.md "$OUT/" 2>/dev/null || true
mkdir -p "$OUT/data" "$OUT/database"
rsync -a database/ "$OUT/database/"

ARCHIVE="dist/setuhaul-${STAMP}.tar.gz"
tar -czf "$ARCHIVE" -C dist "setuhaul-${STAMP}"
echo "Packaged: $ARCHIVE"
