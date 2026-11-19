#!/bin/sh
# Start the app. With SEED_DEMO=1 and no accounts yet (files or DATABASE_URL), the four demo stories are created first.
set -e
mkdir -p "${COPILOT_DATA_DIR:-/data}"
if [ "${SEED_DEMO:-0}" = "1" ]; then
  python seed_demo.py --if-empty || true
fi
# One worker on purpose: trips are JSON files guarded by in-process locks and caches.
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1 --proxy-headers --forwarded-allow-ips="*"
