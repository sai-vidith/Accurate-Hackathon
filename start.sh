#!/usr/bin/env bash
# Start Disruption Copilot (backend + frontend). Works from any folder.
# Usage: ./start.sh        Stop with Ctrl+C (stops both).
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"

for port in 8000 5173; do
  if lsof -nP -iTCP:$port -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Port $port is already in use (an earlier run is probably still going)."
    echo "Either open http://localhost:5173, or stop it first with:  lsof -ti tcp:$port | xargs kill"
    exit 1
  fi
done

if [ ! -x "$ROOT/.venv/bin/uvicorn" ]; then
  echo "Setting up Python environment..."
  python3 -m venv "$ROOT/.venv"
  "$ROOT/.venv/bin/pip" install -q -r "$ROOT/backend/requirements.txt"
fi
if [ ! -d "$ROOT/frontend/node_modules" ]; then
  echo "Installing frontend packages..."
  (cd "$ROOT/frontend" && npm install --no-fund --no-audit)
fi

(cd "$ROOT/backend" && "$ROOT/.venv/bin/uvicorn" app.main:app --port 8000) &
BACK=$!
trap 'kill $BACK 2>/dev/null' EXIT

echo ""
echo "Backend:  http://localhost:8000/docs"
echo "App:      http://localhost:5173   (Ctrl+C to stop both)"
echo ""
cd "$ROOT/frontend" && npm run dev
