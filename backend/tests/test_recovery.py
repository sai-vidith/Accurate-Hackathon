"""End-to-end recovery on a user-built trip, offline (rules instead of AI, distance estimates, fake nearby places)."""
import pytest

from app import engine, maps, planner, store
from app.timeutil import parse

ST = {"name": "Mysuru Junction", "lat": 12.3164, "lng": 76.6447}
HOTEL = {"name": "Hotel Royal", "lat": 12.3105, "lng": 76.6590}
PALACE = {"name": "Mysore Palace", "lat": 12.3052, "lng": 76.6552, "types": ["tourist_attraction"]}
MARKET = {"name": "Devaraja Market", "lat": 12.3110, "lng": 76.6545, "types": ["market", "park"], "indoor": False}
REST = {"name": "Spice Courtyard", "lat": 12.3125, "lng": 76.6520, "types": ["restaurant"]}
CHENNAI = {"name": "Chennai Central", "lat": 13.0827, "lng": 80.2707}
ALL_DAY = {str(d): [[600, 1080]] for d in range(7)}  # 10:00-18:00

FAKE_NEARBY = [
    {"name": "Rail Museum", "lat": 12.3170, "lng": 76.6400, "place_id": "p_museum", "types": ["museum"], "indoor": True,
     "hours": ALL_DAY, "est_cost": 50, "rating": 4.4, "source": "test"},
    {"name": "Karanji Lake Park", "lat": 12.3020, "lng": 76.6700, "place_id": "p_park", "types": ["park"], "indoor": False,
     "hours": ALL_DAY, "est_cost": 0, "rating": 4.3, "source": "test"},
    {"name": "Art Gallery", "lat": 12.3069, "lng": 76.6487, "place_id": "p_gallery", "types": ["art_gallery"], "indoor": True,
     "hours": ALL_DAY, "est_cost": 100, "rating": 4.5, "source": "test"},
]


@pytest.fixture(autouse=True)
def fake_maps(monkeypatch, tmp_path):
    monkeypatch.setattr(maps, "nearby", lambda center, cats, radius_m=3000, limit=20: [dict(p) for p in FAKE_NEARBY])
    monkeypatch.setattr(store, "TRIPS_DIR", tmp_path)


def make_trip(tour_priority="high"):
    t = store.blank_trip("Mysuru day", "Mysuru")
    t["center"] = {"lat": 12.31, "lng": 76.65}
    raw = [
        {"type": "transport", "title": "Train to Mysuru", "start": "2026-11-20T06:00", "end": "2026-11-20T10:00",
         "origin": CHENNAI, "location": ST, "booking": {"provider": "Indian Railways", "reference": "PNR123"}},
        {"type": "stay", "title": "Hotel Royal check-in", "start": "2026-11-20T10:30", "location": HOTEL,
         "booking": {"provider": "Hotel Royal", "reference": "HR9"}},
        {"type": "activity", "title": "Palace guided tour", "start": "2026-11-20T12:30", "end": "2026-11-20T15:30",
         "location": PALACE, "priority": tour_priority, "booking": {"provider": "Heritage Walks", "reference": "T55"}},
        {"type": "activity", "title": "Market walk", "start": "2026-11-20T16:00", "end": "2026-11-20T17:00",
         "location": MARKET, "fixed": False, "indoor": False},
        {"type": "meal", "title": "Dinner at Spice Courtyard", "start": "2026-11-20T19:00", "end": "2026-11-20T20:30",
         "location": REST, "fixed": True, "booking": {"provider": "Spice Courtyard", "reference": "D7"}},
    ]
    t["items"] = [engine.normalize_item(r) for r in raw]
    return t


def by_title(trip, title):
    return next(i for i in trip["items"] if i["title"] == title)


def status(d, trip, title):
    return d["impact"]["results"][by_title(trip, title)["id"]]["status"]


def test_plain_itinerary_is_feasible():
    t = make_trip()
    sim = engine.simulate(t["items"], parse("2026-11-20T05:00"))
    assert all(r["status"] == "unaffected" for r in sim["results"].values())


def test_three_hour_delay_selective_impact():
    t = make_trip()
    d = planner.analyze(t, "My train is delayed by 3 hours")
    assert d["understood_by"] == "rules"
    assert status(d, t, "Train to Mysuru") in ("disrupted", "in_progress")
    assert status(d, t, "Palace guided tour") == "affected"
    assert status(d, t, "Hotel Royal check-in") in ("unaffected", "shifted")
    assert status(d, t, "Dinner at Spice Courtyard") == "unaffected"


def test_plans_are_validated_and_keep_unaffected_bookings():
    t = make_trip()
    d = planner.analyze(t, "My train is delayed by 3 hours")
    planner.make_plans(t, d)
    assert d["status"] == "planned" and 2 <= len(d["plans"]) <= 3
    for p in d["plans"]:
        assert p["valid"] and all(c["ok"] for c in p["checks"] if "reachable" in c["text"])
        dinner = next(r for r in p["schedule"] if r["title"] == "Dinner at Spice Courtyard")
        assert dinner["start"] == "2026-11-20T19:00" and dinner["tag"] == "kept"
        assert any(r["title"] == "Palace guided tour" for r in p["removed"])
    assert any(r["tag"] == "new" for p in d["plans"] for r in p["schedule"]), "one plan should swap in a nearby place"


def test_approve_updates_itinerary_and_creates_tasks():
    t = make_trip()
    d = planner.analyze(t, "My train is delayed by 3 hours")
    planner.make_plans(t, d)
    swap = next(p for p in d["plans"] if p["counts"]["new"])
    planner.approve(t, d, swap["id"])
    train = by_title(t, "Train to Mysuru")
    assert train["end"] == "2026-11-20T13:00" and train["booking"]["status"] == "confirmed"
    tour = by_title(t, "Palace guided tour")
    assert tour["status"] == "cancelled" and tour["booking"]["status"] == "needs_attention"
    assert by_title(t, "Dinner at Spice Courtyard")["start"] == "2026-11-20T19:00"
    cancel = next(a for a in t["actions"] if a["kind"] == "cancel")
    planner.update_action(t, cancel["id"], "pending")
    planner.update_action(t, cancel["id"], "confirmed", "CX1")
    assert tour["booking"]["status"] == "cancelled"
    assert d["status"] == "resolved"


def test_rain_flags_outdoor_and_swaps_indoor():
    t = make_trip()
    d = planner.analyze(t, "Heavy rain expected this afternoon", as_of="2026-11-20T15:00")
    assert d["rain"]
    assert status(d, t, "Market walk") == "at_risk"
    planner.make_plans(t, d)
    swap = next((p for p in d["plans"] if p["counts"]["new"]), None)
    assert swap, "should offer an indoor alternative"
    new = [r for r in swap["schedule"] if r["tag"] == "new"]
    assert all(r["location"]["indoor"] for r in new)


def test_closed_attraction():
    t = make_trip()
    d = planner.analyze(t, "The palace guided tour is closed today", as_of="2026-11-20T11:00")
    assert status(d, t, "Palace guided tour") == "affected"


def test_must_do_unreachable_gives_honest_no_plan():
    t = make_trip(tour_priority="must")
    d = planner.analyze(t, "My train is delayed by 5 hours")
    planner.make_plans(t, d)
    assert d["status"] == "no_plan" and not d["plans"]
    assert any(any("must-do" in c["text"] for c in p["checks"]) for p in d["excluded"])


def test_small_delay_needs_no_change():
    t = make_trip()
    d = planner.analyze(t, "Train running 10 minutes late")
    assert not d["impact"]["needs_change"]


def test_failed_booking_triggers_new_plan_keeping_confirmed_items():
    t = make_trip()
    d = planner.analyze(t, "My train is delayed by 3 hours")
    planner.make_plans(t, d)
    swap = next(p for p in d["plans"] if p["counts"]["new"])
    planner.approve(t, d, swap["id"])
    book = next((a for a in t["actions"] if a["kind"] == "book"), None)
    assert book, "a paid new place should create a booking task"
    planner.update_action(t, book["id"], "failed")
    d2 = planner.structured(t, f"Couldn't complete: {book['title']}", [{"item_id": book["item_id"], "kind": "cancel", "note": "Booking not possible"}])
    planner.make_plans(t, d2)
    assert d2["status"] == "planned" and d2["plans"]
    for p in d2["plans"]:
        assert all(r["title"] != by_title(t, "Palace guided tour")["title"] or r["tag"] == "done" for r in p["schedule"])
        dinner = next(r for r in p["schedule"] if r["title"] == "Dinner at Spice Courtyard")
        assert dinner["start"] == "2026-11-20T19:00"


def test_cancelled_first_train_leaves_traveler_at_origin():
    t = make_trip()
    d = planner.analyze(t, "My train was cancelled")
    assert status(d, t, "Train to Mysuru") == "affected"
    # still in Chennai, ~350 km away: the 12:30 tour can't be reached
    assert status(d, t, "Palace guided tour") == "affected"


def test_plan_dropping_working_booking_is_rejected(monkeypatch):
    t = make_trip()
    d = planner.analyze(t, "My train is delayed by 3 hours")
    opts = {"candidates": [], "transits": [], "categories": []}
    spec = {"name": "Bad", "schedule": [{"ref": by_title(t, "Train to Mysuru")["id"]}]}  # leaves out dinner (still fine)
    monkeypatch.setattr(planner, "gather_options", lambda trip, dd: opts)
    monkeypatch.setattr(planner, "_ai_specs", lambda trip, dd, o: ([spec], "test"))
    planner.make_plans(t, d)
    bad = next(p for p in d["excluded"] if p["name"] == "Bad")
    assert any("Drops a confirmed booking" in c["text"] for c in bad["checks"])


def test_cancelled_transport_asks_for_replacement():
    t = make_trip()
    d = planner.analyze(t, "My train was cancelled")
    assert any("replacement" in q for q in d["questions"])
