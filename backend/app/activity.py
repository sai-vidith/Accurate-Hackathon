"""Activity log: one line per API request (who, what, result, how long, which outside services it used).

Stored as JSON lines in backend/data/activity.jsonl and trimmed to the most recent MAX_LINES.
Only the admin can read it.
"""
from __future__ import annotations

import json
import re
import threading
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from .config import DATA_DIR

LOG_FILE = DATA_DIR / "activity.jsonl"
MAX_LINES = 20000
_lock = threading.Lock()
_writes = [0]

_ID = re.compile(r"^(trip|it|dis|plan|act|usr|chg)_[0-9a-f]{4,}$")


def route_of(path: str) -> str:
    """/api/trips/trip_ab12cd34/items/it_9f → /api/trips/:id/items/:id (so the same endpoint groups together)."""
    return "/".join(":id" if _ID.match(p) else p for p in path.split("/"))


AREAS = [("/api/auth", "login"), ("/api/admin", "admin"), ("/chat", "assistant"), ("/plans", "recovery plans"),
         ("/approve", "recovery plans"), ("/changes", "disruptions"), ("/import", "import"), ("/items", "itinerary"),
         ("/routes", "map"), ("/map.html", "map"), ("/weather", "weather"), ("/places", "places"),
         ("/actions", "bookings"), ("/api/trips", "trips"), ("/api/status", "status")]


def area_of(path: str) -> str:
    return next((a for key, a in AREAS if key in path), "other")


def record(entry: dict) -> None:
    from . import db
    if db.enabled():
        try:
            db.log_activity(entry, MAX_LINES)
        except Exception:  # noqa: BLE001 - the log must never break a request
            pass
        return
    line = json.dumps(entry, ensure_ascii=False)
    with _lock:
        with LOG_FILE.open("a") as f:
            f.write(line + "\n")
        _writes[0] += 1
        if _writes[0] % 500 == 0:  # trim now and then, not on every request
            lines = LOG_FILE.read_text().splitlines()
            if len(lines) > MAX_LINES:
                LOG_FILE.write_text("\n".join(lines[-MAX_LINES:]) + "\n")


def read(limit: int = 5000) -> list[dict]:
    from . import db
    if db.enabled():
        return db.read_activity(limit)
    if not LOG_FILE.exists():
        return []
    out = []
    for line in LOG_FILE.read_text().splitlines()[-limit:]:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def query(user: str | None = None, outcome: str | None = None, area: str | None = None, q: str | None = None,
          limit: int = 200) -> list[dict]:
    rows = read()
    if user:
        rows = [r for r in rows if r.get("user") == user]
    if outcome == "ok":
        rows = [r for r in rows if r["status"] < 400]
    elif outcome == "client_error":
        rows = [r for r in rows if 400 <= r["status"] < 500]
    elif outcome == "server_error":
        rows = [r for r in rows if r["status"] >= 500]
    elif outcome == "slow":
        rows = [r for r in rows if r["ms"] >= 3000]
    if area:
        rows = [r for r in rows if r.get("area") == area]
    if q:
        ql = q.lower()
        rows = [r for r in rows if ql in json.dumps(r, ensure_ascii=False).lower()]
    return list(reversed(rows))[:limit]


def _pct(values: list[float], p: float) -> int:
    if not values:
        return 0
    s = sorted(values)
    return round(s[min(len(s) - 1, int(p * len(s)))])


def stats(hours: int = 24) -> dict:
    since = (datetime.now() - timedelta(hours=hours)).isoformat(timespec="seconds")
    rows = [r for r in read() if r["at"] >= since]
    ms = [r["ms"] for r in rows]
    by_route: dict[str, list] = defaultdict(list)
    for r in rows:
        by_route[f'{r["method"]} {r["route"]}'].append(r)
    endpoints = sorted(({"endpoint": k, "count": len(v), "avg_ms": round(sum(x["ms"] for x in v) / len(v)),
                         "p95_ms": _pct([x["ms"] for x in v], 0.95),
                         "errors": sum(1 for x in v if x["status"] >= 400)} for k, v in by_route.items()),
                       key=lambda e: -e["count"])
    services: dict[str, dict] = defaultdict(lambda: {"n": 0, "ms": 0, "errors": 0})
    for r in rows:
        for k, c in (r.get("calls") or {}).items():
            s = services[k]
            s["n"] += c["n"]; s["ms"] += c["ms"]; s["errors"] += c["errors"]
    hourly = Counter(r["at"][:13] for r in rows)
    return {
        "hours": hours,
        "requests": len(rows),
        "users_active": len({r["user"] for r in rows if r.get("user") and r.get("role")}),  # signed-in users only
        "errors": sum(1 for r in rows if r["status"] >= 400),
        "server_errors": sum(1 for r in rows if r["status"] >= 500),
        "avg_ms": round(sum(ms) / len(ms)) if ms else 0,
        "p95_ms": _pct(ms, 0.95),
        "failed_logins": sum(1 for r in rows if r["route"] == "/api/auth/login" and r["status"] >= 400),
        "endpoints": endpoints[:15],
        "services": [{"service": k, **v, "avg_ms": round(v["ms"] / v["n"]) if v["n"] else 0}
                     for k, v in sorted(services.items(), key=lambda kv: -kv[1]["n"])],
        "areas": Counter(r.get("area", "other") for r in rows).most_common(),
        "per_hour": sorted(hourly.items()),
        "per_user": Counter(r.get("user") or "(not logged in)" for r in rows).most_common(10),
    }
