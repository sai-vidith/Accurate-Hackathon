import os
from pathlib import Path

import certifi
from dotenv import load_dotenv

# python.org builds of Python on macOS ship without system CA certificates; use certifi's bundle
# so geopy / openrouteservice / osmnx (requests-based) can make HTTPS calls.
os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())

ROOT = Path(__file__).resolve().parents[2]
# .env.local first (written by `neon deploy` when there is no .env); earlier files win
load_dotenv(ROOT / ".env.local")
load_dotenv(ROOT / ".env")

# COPILOT_DATA_DIR lets a test run use a separate copy of the data (accounts, trips, activity log)
DATA_DIR = Path(os.getenv("COPILOT_DATA_DIR") or Path(__file__).resolve().parents[1] / "data")
TRIPS_DIR = DATA_DIR / "trips"
TRIPS_DIR.mkdir(parents=True, exist_ok=True)


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def offline() -> bool:
    """Tests set this to avoid any network calls."""
    return bool(os.getenv("COPILOT_OFFLINE"))
