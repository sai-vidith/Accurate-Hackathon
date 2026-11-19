"""Trips are stored as one JSON file each under backend/data/trips/."""
import json
import uuid
from datetime import datetime

from . import db
from .config import TRIPS_DIR

DEFAULT_PREFS = {
    "interests": ["sightseeing", "food", "culture", "shopping", "nature", "rest"],
    "pace": "moderate",          # relaxed | moderate | packed
    "extra_budget": 3000,        # hard limit for extra spending on recovery
    "currency": "INR",
    "travelers": 1,
    "group": "solo",             # solo | couple | friends | family
    "accessibility": False,      # step-free needed
}


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def blank_trip(title: str = "My trip", destination: str = "", timezone_offset: str = "+05:30") -> dict:
    from .auth import current_user  # a new trip belongs to whoever is logged in
    me = current_user()
    return {
        "id": new_id("trip"),
        "owner": me["id"] if me else None,
        "kind": "manual",  # "manual" = made by a person; "test" = created by automated tests
        "title": title,
        "destination": destination,
        "timezone_offset": timezone_offset,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "preferences": dict(DEFAULT_PREFS),
        "items": [],
        "disruptions": [],
        "actions": [],
        "log": [],
    }


def path(trip_id: str):
    safe = "".join(c for c in trip_id if c.isalnum() or c in "_-")
    return TRIPS_DIR / f"{safe}.json"


def save(trip: dict) -> dict:
    if db.enabled():
        db.save_trip(trip)
    else:
        path(trip["id"]).write_text(json.dumps(trip, indent=2, ensure_ascii=False))
    return trip


def load(trip_id: str) -> dict | None:
    if db.enabled():
        return db.load_trip(trip_id)
    p = path(trip_id)
    return json.loads(p.read_text()) if p.exists() else None


def delete(trip_id: str) -> bool:
    if db.enabled():
        return db.delete_trip(trip_id)
    p = path(trip_id)
    if p.exists():
        p.unlink()
        return True
    return False


def all_trips() -> list[dict]:
    if db.enabled():
        return db.trips()
    return [json.loads(p.read_text()) for p in TRIPS_DIR.glob("*.json")]


def _newest_first(owner: str | None):
    if db.enabled():
        yield from db.trips(owner, all_owners=owner is None)
        return
    for p in sorted(TRIPS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        yield json.loads(p.read_text())


def list_trips(owner: str | None = None) -> list[dict]:
    """Trips of one user (newest first); owner=None lists everyone's (admin view)."""
    out = []
    for t in _newest_first(owner):
        if owner is not None and t.get("owner") != owner:
            continue
        starts = sorted(i["start"] for i in t["items"] if i.get("start"))
        out.append({"id": t["id"], "title": t["title"], "destination": t.get("destination", ""), "kind": t.get("kind", "manual"), "owner": t.get("owner"),
                    "items": len(t["items"]), "from": starts[0][:10] if starts else None,
                    "done": sum(1 for i in t["items"] if i.get("completed")),
                    "to": starts[-1][:10] if starts else None,
                    "open_actions": sum(1 for a in t["actions"] if a["status"] in ("needs_attention", "pending"))})
    return out


def log(trip: dict, text: str, kind: str = "info") -> None:
    trip["log"].append({"at": datetime.now().isoformat(timespec="seconds"), "kind": kind, "text": text})
    trip["log"] = trip["log"][-100:]
