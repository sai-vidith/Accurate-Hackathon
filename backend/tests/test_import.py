"""Itinerary import: day splitting, time labels, namesake rejection, transfers, plan-relative impact (offline)."""
import pytest

from app import engine, extract, maps, planner, store
from app.timeutil import parse

PLACES = {  # fake geocoder: name -> candidates (lat, lng, country)
    "dandeli": [("Dandeli", 15.249, 74.624, "in")],
    "campsite": [("Camping site", 14.105, 121.577, "ph")],          # namesake in the Philippines
    "nirvana beach": [("Nirvana Beach", 14.519, 74.315, "in")],     # really in Gokarna
    "murudeshwar": [("Murudeshwar", 14.094, 74.485, "in")],
    "gokarna": [("Gokarna", 14.544, 74.318, "in")],
    "hubballi": [("Hubballi", 15.364, 75.124, "in")],
    "hyderabad": [("Hyderabad", 17.385, 78.486, "in")],
    "camp ground": [("Camp Ground", 15.249, 74.624, "in"), ("Camp Ground", 12.5, 78.0, "in")],
    "karnataka": [("Karnataka", 15.0, 76.0, "in")],
    "vibhuti falls": [("Vibhuti Falls", 14.48, 74.47, "in")],
}


def fake(q, near=None, limit=5, country=None):
    key = q.split(",")[0].strip().lower()
    hits = [{"name": n, "lat": la, "lng": ln, "country": c, "place_id": f"x:{n}", "types": [], "source": "test"}
            for n, la, ln, c in PLACES.get(key, [])]
    return hits[:limit]


@pytest.fixture(autouse=True)
def fake_maps(monkeypatch, tmp_path):
    monkeypatch.setattr(maps, "search", lambda q, near=None, limit=5: fake(q, near, limit))
    monkeypatch.setattr(maps, "geocode", lambda q, near=None, country=None: (fake(q, near, 1, country) or [None])[0])
    monkeypatch.setattr(store, "TRIPS_DIR", tmp_path)


def item(title, start, end=None, typ="activity", location=None, area=None, origin=None, **kw):
    return {"type": typ, "title": title, "start": start, "end": end, "location": location, "area": area, "origin": origin, **kw}


def test_namesake_abroad_is_rejected_and_falls_back_to_town():
    data = {"title": "T", "destination": "Gokarna", "region": "Karnataka, India", "country_code": "in", "items": [
        item("Road transfer", "2026-11-20T08:00", "2026-11-20T10:00", "transport", "Dandeli", "Dandeli", "Hubballi"),
        item("Camp check-in", "2026-11-20T10:30", None, "stay", "Campsite, Dandeli", "Dandeli")]}
    t = extract.to_trip(data, "test")
    camp = next(i for i in t["items"] if i["title"] == "Camp check-in")["location"]
    assert camp["approximate"] and abs(camp["lat"] - 15.249) < 0.01   # Dandeli town, not the Philippines


def test_exact_name_in_a_different_nearby_town_is_accepted():
    data = {"title": "T", "destination": "Gokarna", "region": "Karnataka, India", "country_code": "in", "items": [
        item("Murudeshwar Temple", "2026-11-21T16:00", "2026-11-21T17:00", location="Murudeshwar", area="Murudeshwar"),
        item("Sunset", "2026-11-21T18:30", "2026-11-21T19:00", location="Nirvana Beach, Murudeshwar", area="Murudeshwar")]}
    t = extract.to_trip(data, "test")
    beach = next(i for i in t["items"] if i["title"] == "Sunset")["location"]
    assert not beach.get("approximate") and abs(beach["lat"] - 14.519) < 0.01  # the real Nirvana Beach (Gokarna)


def test_day_sections_and_document_time_labels():
    text = ("HEADER\nDAY 0 – START\n2:30–3:00 PM (SUGGESTED): Arrive.\n3:30 PM (ADVERTISED): Train.\n"
            "DAY 1 – NEXT\n8:00 AM (ADVERTISED): Reach.\n8:00–10:00 AM (SUGGESTED): Transfer.\n10:00 AM (SUGGESTED): Check-in.\n"
            "PACKAGE INCLUSIONS\n- stuff")
    header, secs = extract._sections(text)
    assert [n for _, n, _ in secs] == [0, 1] and "INCLUSIONS" not in secs[-1][2]
    assert extract._time_labels(secs[0][2]) == {"14:30": "suggested", "15:30": "advertised"}
    assert extract._time_labels(secs[1][2]) == {"10:00": "suggested"}       # 08:00 has two labels: left to the AI


def test_per_day_extraction_merges_and_drops_duplicate_arrivals(monkeypatch):
    replies = iter([
        ({"title": "T", "destination": "Gokarna", "first_date": "2026-11-19", "first_day_label": "DAY 0"}, "test"),
        ({"items": [item("Train", "2026-11-19T15:30", "2026-11-20T08:00", "transport", "Hubballi", fixed=True)]}, "test"),
        ({"items": [item("Reach Hubballi", "2026-11-20T08:00", None, "transport", "Hubballi"),
                    item("Check-in", "2026-11-20T10:00", None, "stay", "Campsite, Dandeli", fixed=True),
                    item("Stray next-day item", "2026-11-21T09:00", None)]}, "test"),
    ])
    monkeypatch.setattr(extract, "json_call", lambda *a, **k: next(replies))
    text = "H\nDAY 0 – A\n3:30 PM (ADVERTISED): Train.\nDAY 1 – B\n10:00 AM (SUGGESTED): Check-in.\n"
    data, _ = extract.extract("text", text)
    titles = [i["title"] for i in data["items"]]
    assert titles == ["Train", "Check-in"]                    # arrival marker and off-day item dropped
    checkin = data["items"][1]
    assert checkin["time_kind"] == "suggested" and checkin["day_label"] == "DAY 1"


def test_suggested_times_are_flexible_even_with_an_organiser():
    data = {"title": "T", "destination": "Gokarna", "country_code": "in", "items": [
        item("Breakfast", "2026-11-21T06:00", "2026-11-21T07:00", "meal", "Gokarna", "Gokarna",
             fixed=True, provider="Spirit Adventures", time_kind="suggested")]}
    t = extract.to_trip(data, "test")
    assert t["items"][0]["fixed"] is False and "suggested" in t["items"][0]["notes"]


def test_transfer_without_origin_does_not_add_travel_before_it():
    a = {"name": "Honnavar", "lat": 14.28, "lng": 74.44}
    b = {"name": "Murudeshwar", "lat": 14.094, "lng": 74.485}
    items = [engine.normalize_item(x) for x in (
        {"type": "activity", "title": "Mangroves", "start": "2026-11-21T14:00", "end": "2026-11-21T15:00", "location": a},
        {"type": "transport", "title": "Transfer", "start": "2026-11-21T15:00", "end": "2026-11-21T16:00", "location": b, "fixed": False},
        {"type": "activity", "title": "Temple", "start": "2026-11-21T16:00", "end": "2026-11-21T17:00", "location": b})]
    res = engine.simulate(items, parse("2026-11-21T13:00"))["results"]
    assert res[items[1]["id"]]["travel_min"] == 0 and res[items[1]["id"]]["status"] == "unaffected"
    assert res[items[2]["id"]]["status"] == "unaffected"


def test_tightness_already_in_the_plan_is_not_reported_as_a_delay():
    far = lambda km: {"name": f"P{km}", "lat": 14.5, "lng": 74.3 + km * 0.0093}
    t = store.blank_trip("Back to back", "X")
    t["items"] = [engine.normalize_item(x) for x in (
        {"type": "activity", "title": "A", "start": "2026-11-22T10:00", "end": "2026-11-22T11:00", "location": far(0)},
        {"type": "activity", "title": "B", "start": "2026-11-22T11:00", "end": "2026-11-22T13:00", "location": far(12)},  # no gap for travel
        {"type": "meal", "title": "Lunch", "start": "2026-11-22T13:00", "end": "2026-11-22T14:00", "location": far(12)},
        {"type": "activity", "title": "Far later stop", "start": "2026-11-22T17:00", "end": "2026-11-22T18:00", "location": far(4)})]
    d = planner.report_delay(t, t["items"][3]["id"], 20, "late_start", as_of="2026-11-22T09:00")
    res = {i["title"]: d["impact"]["results"][i["id"]] for i in t["items"]}
    assert res["B"]["status"] == "unaffected" and "already tight" in res["B"]["reason"]   # tight in the plan, not caused by the delay


def test_odd_ai_reply_for_one_day_does_not_crash_the_import(monkeypatch):
    replies = iter([
        ({"title": "T", "destination": "X", "first_date": "2026-11-19"}, "test"),
        ({"items": ["just text", {"title": "no start"}]}, "test"),   # day 0, attempt 1: junk
        ({"items": "also junk"}, "test"),                               # day 0, attempt 2: junk
        ({"items": [item("Visit", "2026-11-20T10:00")]}, "test"),      # day 1: fine
    ])
    monkeypatch.setattr(extract, "json_call", lambda *a, **k: next(replies))
    data, _ = extract.extract("text", "H\nDAY 0 – A\n9:00 AM: x\nDAY 1 – B\n10:00 AM: Visit\n")
    assert [i["title"] for i in data["items"]] == ["Visit"] and data["missed_sections"] == ["DAY 0 – A"]


def test_overnight_stay_cannot_drift_to_a_far_namesake():
    data = {"title": "T", "destination": "Dandeli", "region": "Karnataka, India", "country_code": "in", "items": [
        item("Arrive", "2026-11-20T10:00", "2026-11-20T10:30", location="Dandeli", area="Dandeli"),
        item("Night", "2026-11-20T21:00", None, "stay", "Camp Ground", None),
        item("Wake up", "2026-11-21T05:30", "2026-11-21T06:00", location="Camp Ground", area=None)]}
    t = extract.to_trip(data, "test")
    for i in t["items"]:
        assert maps.km(i["location"], {"lat": 15.249, "lng": 74.624}) < 5   # never the namesake ~400 km away


def test_a_state_is_never_used_as_the_town():
    data = {"title": "T", "destination": "Gokarna", "region": "Karnataka, India", "country_code": "in", "items": [
        item("Start", "2026-11-21T06:00", "2026-11-21T07:00", location="Gokarna", area="Gokarna"),
        item("Transfer", "2026-11-21T07:00", "2026-11-21T09:00", "transport", "Vibhuti Falls, Karnataka", "Karnataka")]}
    t = extract.to_trip(data, "test")
    falls = t["items"][1]["location"]
    assert not falls.get("approximate") and abs(falls["lat"] - 14.48) < 0.01


def test_town_in_the_place_name_beats_a_wrong_area_label():
    """'Return railway station, Gokarna' with the AI's area set to the destination (Hyderabad) is still in Gokarna."""
    data = {"title": "T", "destination": "Gokarna", "region": "Karnataka, India", "country_code": "in", "items": [
        item("Lunch", "2026-11-22T13:30", "2026-11-22T14:30", "meal", "Gokarna", "Gokarna"),
        item("Return train", "2026-11-22T20:30", "2026-11-23T11:00", "transport", "Hyderabad", "Hyderabad",
             "Return railway station, Gokarna", fixed=True)]}
    t = extract.to_trip(data, "test")
    train = next(i for i in t["items"] if i["title"] == "Return train")
    assert abs(train["origin"]["lat"] - 14.544) < 0.01 and abs(train["location"]["lat"] - 17.385) < 0.01


def test_journey_whose_start_was_mislocated_onto_its_end_departs_from_where_you_are():
    """A bad import put the return train's start point in Hyderabad (its destination): no 35-hour 'drive' to it."""
    gk, hyd = {"name": "Gokarna", "lat": 14.544, "lng": 74.318}, {"name": "Hyderabad", "lat": 17.385, "lng": 78.486}
    t = store.blank_trip("T", "Gokarna")
    t["items"] = [engine.normalize_item(x) for x in [
        {"type": "meal", "title": "Lunch", "start": "2026-11-22T13:30", "end": "2026-11-22T14:30", "location": gk},
        {"type": "transport", "title": "Return train", "start": "2026-11-22T20:30", "end": "2026-11-23T11:00",
         "origin": dict(hyd, name="Return railway station, Gokarna"), "location": hyd, "fixed": True}]]
    r = engine.simulate(t["items"], parse("2026-11-22T12:00"))["results"][t["items"][1]["id"]]
    assert r["status"] == "unaffected" and r["travel_min"] == 0
