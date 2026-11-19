"""Manual progress tracking, delays at a specific stop, smarter alternatives, approval (offline)."""
import pytest

from app import engine, maps, planner, store
from app.timeutil import parse

LAT, LNG, KM = 12.30, 76.65, 0.0092  # ~1 km of longitude here


def at(x_km, name):
    return {"name": name, "lat": LAT, "lng": LNG + x_km * KM}


@pytest.fixture(autouse=True)
def offline_places(monkeypatch, tmp_path):
    monkeypatch.setattr(maps, "nearby", lambda *a, **k: [])
    monkeypatch.setattr(store, "TRIPS_DIR", tmp_path)


def day_trip(dinner_end="20:00"):
    t = store.blank_trip("City day", "Mysuru")
    raw = [
        ("meal", "Breakfast", "09:00", "10:00", at(0, "Cafe"), False, "normal", {}),
        ("activity", "Palace visit", "10:30", "12:00", at(0.5, "Palace"), False, "high", {}),
        ("activity", "Museum", "12:30", "14:00", at(2.5, "Museum"), False, "normal", {}),
        ("activity", "Market", "14:30", "15:30", at(1.0, "Market"), False, "optional", {}),
        ("activity", "Boat ride", "16:30", "18:00", at(5.0, "Lake"), True, "high", {"provider": "Lake Boats", "reference": "B1"}),
        ("meal", "Dinner", "19:00", dinner_end, at(1.5, "Restaurant"), True, "normal", {"provider": "Spice", "reference": "D1"}),
    ]
    t["items"] = [engine.normalize_item({"type": ty, "title": ti, "start": f"2026-11-20T{s}", "end": f"2026-11-20T{e}",
                                         "location": loc, "fixed": fx, "priority": pr, "booking": bk})
                  for ty, ti, s, e, loc, fx, pr, bk in raw]
    return t


def item(t, title):
    return next(i for i in t["items"] if i["title"] == title)


def done(t, title, at_hm):
    it = item(t, title)
    it["completed"], it["completed_at"] = True, f"2026-11-20T{at_hm}"


def res(d, t, title):
    return d["impact"]["results"][item(t, title)["id"]]


# ---------------------------------------------------------------- 1. delay at the third stop

def test_45_min_overrun_at_third_stop_is_absorbed_not_added():
    t = day_trip()
    done(t, "Breakfast", "10:00")
    done(t, "Palace visit", "12:05")
    d = planner.report_delay(t, item(t, "Museum")["id"], 45, "overrun")
    museum = res(d, t, "Museum")
    assert museum["end"].endswith("14:45")                      # ran over by 45
    market = res(d, t, "Market")
    shift = (parse(market["start"]) - parse("2026-11-20T14:30")).total_seconds() / 60
    assert 0 < shift < 45, f"market shifted {shift} min: slack and travel should absorb part of the delay"
    # exact arithmetic: museum end + real travel + buffer, not "+45"
    assert parse(market["start"]) == parse(museum["end"]) + __import__("datetime").timedelta(minutes=market["travel_min"] + market["buffer"])
    assert "After Museum ends 14:45" in market["why"]          # the explanation names the cause
    assert res(d, t, "Dinner")["start"].endswith("19:00")     # fixed booking keeps its time
    planner.make_plans(t, d)
    assert any(any(r["title"] == "Boat ride" and r["start"].endswith("16:30") for r in p["schedule"]) for p in d["plans"]), \
        "at least one plan keeps the 16:30 boat ride"


def test_completed_items_are_protected():
    t = day_trip()
    done(t, "Breakfast", "10:10")
    done(t, "Palace visit", "12:20")
    d = planner.report_delay(t, item(t, "Museum")["id"], 90, "overrun")
    for title, fin in (("Breakfast", "10:10"), ("Palace visit", "12:20")):
        r = res(d, t, title)
        assert r["status"] == "completed" and r["end"].endswith(fin)
    planner.make_plans(t, d)
    assert d["plans"]
    for p in d["plans"]:
        rows = {r["title"]: r for r in p["schedule"]}
        assert rows["Breakfast"]["tag"] == "done" and rows["Breakfast"]["start"].endswith("09:00")
        assert rows["Palace visit"]["tag"] == "done"
        assert all(r["title"] not in ("Breakfast", "Palace visit") for r in p["removed"])
    planner.approve(t, d, d["plans"][0]["id"])
    assert item(t, "Breakfast")["start"].endswith("09:00") and item(t, "Breakfast")["completed"]
    with pytest.raises(ValueError):
        planner.report_delay(t, item(t, "Palace visit")["id"], 10)  # can't delay something already done


def test_progress_sets_now_and_unticked_earlier_items_are_skipped_not_removed():
    t = day_trip()
    done(t, "Palace visit", "12:00")             # breakfast never ticked
    d = planner.report_delay(t, item(t, "Museum")["id"], 30, "late_start")
    assert d["as_of"] >= "2026-11-20T12:00"
    assert res(d, t, "Breakfast")["status"] == "skipped"
    planner.make_plans(t, d)
    for p in d["plans"]:
        assert all(r["title"] != "Breakfast" for r in p["removed"])
    item(t, "Palace visit")["completed"] = False  # untick fixes a mistake
    sim = engine.simulate(t["items"], parse("2026-11-20T08:00"))
    assert sim["results"][item(t, "Palace visit")["id"]]["status"] != "completed"


# ---------------------------------------------------------------- 4. longer / shorter delays

def test_delay_size_changes_are_recalculated_from_original_times():
    t = day_trip()
    done(t, "Breakfast", "10:00")
    done(t, "Palace visit", "12:00")
    d = planner.report_delay(t, item(t, "Museum")["id"], 15, "overrun")
    affected = {}
    for m in (15, 45, 150, 45):
        planner.update_delay(t, d, m)
        assert res(d, t, "Museum")["end"] == f"2026-11-20T{14 + (m // 60):02d}:{m % 60:02d}"  # from the ORIGINAL 14:00, never stacked
        affected[m] = sum(r["status"] in ("affected", "shifted") for r in d["impact"]["results"].values())
    assert affected[15] <= affected[45] <= affected[150]
    planner.update_delay(t, d, 15)
    assert res(d, t, "Boat ride")["status"] == "unaffected"  # a short overrun is absorbed
    planner.update_delay(t, d, 150)
    assert res(d, t, "Boat ride")["status"] == "affected"  # museum now ends 16:30: the 16:30 boat is out of reach


# ---------------------------------------------------------------- 3. alternative strategies

def test_shorten_strategy_keeps_stops_within_minimum_durations():
    t = day_trip()
    done(t, "Breakfast", "10:00")
    done(t, "Palace visit", "12:00")
    d = planner.report_delay(t, item(t, "Museum")["id"], 40, "overrun")
    planner.make_plans(t, d)
    kinds = {p["kind"]: p for p in d["plans"] + d["excluded"]}
    assert "shorten" in kinds, [p["name"] for p in d["plans"]]
    p = kinds["shorten"]
    assert p["valid"]
    short = [r for r in p["schedule"] if "shortened" in r["flags"]]
    assert short and all("Shortened from" in r["why"] for r in short)
    for r in short:
        assert r["duration"] >= engine.min_duration(item(t, r["title"]))
    boat = next(r for r in p["schedule"] if r["title"] == "Boat ride")
    assert boat["start"].endswith("16:30")


def test_postpone_strategy_moves_low_priority_to_evening():
    t = day_trip()
    done(t, "Breakfast", "10:00")
    done(t, "Palace visit", "12:00")
    d = planner.report_delay(t, item(t, "Museum")["id"], 120, "overrun")
    planner.make_plans(t, d)
    pp = next((p for p in d["plans"] if p["kind"] == "postpone"), None)
    assert pp, [p["name"] for p in d["plans"] + d["excluded"]]
    market = next(r for r in pp["schedule"] if r["title"] == "Market")
    assert "postponed" in market["flags"] and parse(market["start"]).hour >= 20
    assert "Postponed" in market["why"]


def test_reorder_strategy_cuts_travel():
    t = store.blank_trip("Zigzag", "X")
    raw = [("activity", "Start point", "09:00", "09:30", at(0, "Start"), False, "normal", {}),
           ("activity", "Far market", "10:00", "11:00", at(6.0, "Far"), False, "normal", {}),
           ("activity", "Near museum", "11:30", "12:30", at(2.0, "Near"), False, "normal", {}),
           ("activity", "Lake cruise", "15:00", "16:00", at(8.0, "Lake"), True, "high", {"provider": "L", "reference": "R"})]
    t["items"] = [engine.normalize_item({"type": ty, "title": ti, "start": f"2026-11-20T{s}", "end": f"2026-11-20T{e}",
                                         "location": loc, "fixed": fx, "priority": pr, "booking": bk})
                  for ty, ti, s, e, loc, fx, pr, bk in raw]
    done(t, "Start point", "09:30")
    d = planner.report_delay(t, item(t, "Far market")["id"], 20, "late_start")
    planner.make_plans(t, d)
    rp = next((p for p in d["plans"] if p["kind"] == "reorder"), None)
    shift = next(p for p in d["plans"] + d["excluded"] if p["kind"] == "shift")
    assert rp, [p["name"] for p in d["plans"]]
    order = [r["title"] for r in rp["schedule"] if r["tag"] not in ("done",)]
    assert order.index("Near museum") < order.index("Far market")
    assert any("reordered" in r["flags"] for r in rp["schedule"])
    assert rp["travel_min"] < shift["travel_min"]


def test_plans_explain_pros_cons_and_rank():
    t = day_trip()
    done(t, "Breakfast", "10:00")
    done(t, "Palace visit", "12:00")
    d = planner.report_delay(t, item(t, "Museum")["id"], 75, "overrun")
    planner.make_plans(t, d)
    assert 2 <= len(d["plans"]) <= 4
    assert d["plans"][0].get("recommended")
    assert [p["score"] for p in d["plans"]] == sorted([p["score"] for p in d["plans"]], reverse=True)
    for p in d["plans"]:
        assert p["pros"] and p["cons"]
        for r in p["schedule"]:
            if r["tag"] in ("moved", "shortened", "reordered", "postponed"):
                assert r["was"] and r["why"]


# ---------------------------------------------------------------- 4. approval, baseline, consistency

def test_approval_applies_changes_keeps_baseline_and_consistent_times():
    t = day_trip()
    done(t, "Breakfast", "10:00")
    done(t, "Palace visit", "12:00")
    d = planner.report_delay(t, item(t, "Museum")["id"], 40, "overrun")
    planner.make_plans(t, d)
    sp = next(p for p in d["plans"] if p["kind"] == "shorten")
    planner.approve(t, d, sp["id"])
    assert t["baseline"]["items"] and next(i for i in t["baseline"]["items"] if i["title"] == "Museum")["end"].endswith("14:00")
    assert d["before"]
    shortened = [r for r in sp["schedule"] if "shortened" in r["flags"]]
    for r in shortened:
        it = item(t, r["title"])
        assert it["end"] == r["end"] and it["previous_end"]
    # the updated itinerary is internally consistent: nothing unreachable afterwards
    sim = engine.simulate(t["items"], parse(d["as_of"]), planner.overrides_for(d))
    assert not [k for k, v in sim["results"].items() if v["status"] == "affected"]


def test_skip_low_priority_to_rescue_booking():
    t = day_trip()
    done(t, "Breakfast", "10:00")
    done(t, "Palace visit", "12:00")
    d = planner.report_delay(t, item(t, "Museum")["id"], 75, "overrun")
    assert res(d, t, "Boat ride")["status"] == "affected"   # the optional market pushes the boat out of reach
    planner.make_plans(t, d)
    trim = next(p for p in d["plans"] if p["kind"] == "trim")
    assert [r["title"] for r in trim["removed"]] == ["Market"]  # only the optional stop is skipped
    assert any(r["title"] == "Boat ride" and r["start"].endswith("16:30") for r in trim["schedule"])
    assert d["plans"][0]["kind"] == "trim"                       # and it ranks first: it saves a high-priority booking
    pp = next((p for p in d["plans"] if p["kind"] == "postpone"), None)
    if pp:  # moving the market to the evening also frees the boat
        assert any(r["title"] == "Boat ride" for r in pp["schedule"])


def test_hotel_delay_means_later_check_in():
    t = day_trip()
    hotel = engine.normalize_item({"type": "stay", "title": "Hotel", "start": "2026-11-20T13:00", "location": at(0.2, "Hotel")})
    t["items"].append(hotel)
    d = planner.report_delay(t, hotel["id"], 60, "overrun")  # "runs over" makes no sense for a check-in
    c = d["changes"][0]
    assert c["delay_mode"] == "late_start" and c["new_start"].endswith("14:00") and "Check in" in c["note"]


# ---------------------------------------------------------------- done toggles cascade; finished parts can't change

def test_ticking_a_stop_marks_all_earlier_stops_done():
    t = day_trip()
    planner.set_done(t, item(t, "Museum")["id"], True, "2026-11-20T14:05")
    for title, fin in (("Breakfast", "10:00"), ("Palace visit", "12:00")):   # earlier stops: their planned finish
        assert item(t, title)["completed"] and item(t, title)["completed_at"].endswith(fin)
    assert item(t, "Museum")["completed_at"].endswith("14:05")                # the ticked stop keeps the given time
    assert not item(t, "Market")["completed"]


def test_ticking_keeps_actual_times_already_given():
    t = day_trip()
    planner.set_done(t, item(t, "Breakfast")["id"], True, "2026-11-20T10:20")
    planner.set_done(t, item(t, "Museum")["id"], True)
    assert item(t, "Breakfast")["completed_at"].endswith("10:20")


def test_unticking_a_stop_unticks_everything_after_it():
    t = day_trip()
    planner.set_done(t, item(t, "Market")["id"], True)
    planner.set_done(t, item(t, "Palace visit")["id"], False)
    assert item(t, "Breakfast")["completed"]
    assert not any(item(t, x)["completed"] for x in ("Palace visit", "Museum", "Market"))


def test_delay_on_a_done_stop_changes_nothing():
    t = day_trip()
    planner.set_done(t, item(t, "Museum")["id"], True)
    before = [dict(i) for i in t["items"]]
    for title in ("Breakfast", "Palace visit", "Museum"):
        with pytest.raises(ValueError, match="nothing changed"):
            planner.report_delay(t, item(t, title)["id"], 30)
    assert t["items"] == before and t["disruptions"] == []


def test_typed_change_to_a_done_stop_is_ignored():
    t = day_trip()
    planner.set_done(t, item(t, "Palace visit")["id"], True)
    d = planner.analyze(t, "Breakfast was delayed by 30 minutes")       # rule parser targets the (done) breakfast
    assert d["status"] == "dismissed" and d["changes"] == []
    assert any("already marked done" in x for x in d["ignored"])
    assert item(t, "Breakfast")["start"].endswith("09:00")


def test_ticking_done_retires_an_open_delay_on_that_stop():
    t = day_trip()
    planner.set_done(t, item(t, "Palace visit")["id"], True)
    d = planner.report_delay(t, item(t, "Museum")["id"], 45, "overrun")
    assert d["status"] == "analyzed"
    planner.set_done(t, item(t, "Museum")["id"], True, "2026-11-20T14:10")  # it actually finished: delay is moot
    assert d["status"] == "dismissed" and "already finished" in d["dismiss_reason"]


def test_delay_is_never_checked_before_latest_done_time():
    t = day_trip()
    planner.set_done(t, item(t, "Palace visit")["id"], True, "2026-11-20T12:20")
    d = planner.report_delay(t, item(t, "Market")["id"], 20, "late_start", as_of="2026-11-20T09:00")
    assert d["as_of"] >= "2026-11-20T12:20"
    assert all(d["impact"]["results"][item(t, x)["id"]]["status"] == "completed" for x in ("Breakfast", "Palace visit"))


def test_unticked_flexible_stop_is_still_to_do_even_after_its_time():
    t = day_trip()
    planner.set_done(t, item(t, "Palace visit")["id"], True, "2026-11-20T15:00")  # palace ran very late
    sim = engine.simulate(t["items"], parse("2026-11-20T15:00"))
    museum = sim["results"][item(t, "Museum")["id"]]        # 12:30-14:00 has passed, but it isn't ticked
    assert museum["status"] != "completed" and museum["start"] > "2026-11-20T15:00"


def test_delay_mid_trip_counts_earlier_unticked_days_as_behind_you():
    """Nothing ticked on days 1-2; a delay reported on day 3 must not try to fit days 1-2 in after it."""
    t = store.blank_trip("Multi-day", "Mysuru")
    t["items"] = [engine.normalize_item({"type": ty, "title": ti, "start": s, "end": e, "location": at(km, ti)})
                  for ty, ti, s, e, km in [
                      ("activity", "Day 1 walk", "2026-11-19T10:00", "2026-11-19T12:00", 0),
                      ("meal", "Day 2 lunch", "2026-11-20T13:00", "2026-11-20T14:00", 1),
                      ("activity", "Falls", "2026-11-21T10:00", "2026-11-21T11:00", 2),
                      ("meal", "Day 3 lunch", "2026-11-21T13:00", "2026-11-21T14:00", 3)]]
    falls = item(t, "Falls")
    d = planner.report_delay(t, falls["id"], 60, "overrun")
    res = d["impact"]["results"]
    for title in ("Day 1 walk", "Day 2 lunch"):
        r = res[item(t, title)["id"]]
        assert r["status"] == "completed" and r.get("assumed"), (title, r)
    assert res[item(t, "Day 3 lunch")["id"]]["status"] in ("unaffected", "shifted")
    assert not item(t, "Day 1 walk")["completed"]   # counted as done for planning only; your ticks are unchanged
    planner.make_plans(t, d)
    assert d["plans"], [x["checks"] for x in d["excluded"]]   # plans aren't rejected over days already behind you
    for p in d["plans"]:
        assert not any("Day 1" in c["text"] or "Day 2" in c["text"] for c in p["checks"] if not c["ok"])
