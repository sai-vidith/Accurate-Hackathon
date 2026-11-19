"""Deterministic timing engine: reachability, impact and plan validation for ANY itinerary.

The AI never decides feasibility: everything here is arithmetic over item times, travel times
from the maps service, opening hours and the traveler's budget.
"""
from __future__ import annotations

from datetime import datetime

from . import maps
from .store import new_id
from .timeutil import add, fmt, hm, parse

DEFAULT_MIN = {"activity": 90, "meal": 60, "other": 45, "stay": 15, "transport": 60}
BUFFER = 10            # minutes of slack before anything
STATION_BUFFER = 20    # be at the station/airport this early for transport
SMALL_SHIFT = 30       # flexible items can slip this much without counting as a problem
FLEX_WINDOW = {"activity": 240, "meal": 90, "other": 180, "stay": 12 * 60, "transport": 180}


# ------------------------------------------------------------------ items

def normalize_item(item: dict) -> dict:
    it = dict(item)
    it.setdefault("id", new_id("it"))
    it["type"] = it.get("type") or "other"
    booking = it.get("booking") or {}
    booking.setdefault("status", "confirmed" if (booking.get("reference") or booking.get("provider")) else "none")
    it["booking"] = booking
    if it.get("fixed") is None:
        it["fixed"] = it["type"] == "transport" or bool(booking.get("reference")) or it["type"] == "meal" and bool(booking.get("provider"))
    if it["type"] == "stay":
        it["fixed"] = False  # check-in is a window (until late evening), not a time slot
    it.setdefault("priority", "normal")
    it.setdefault("status", "planned")
    it.setdefault("completed", False)      # ticked done by the traveler
    it.setdefault("completed_at", None)    # actual finish time they gave (never rescheduled afterwards)
    it.setdefault("notes", "")
    it.setdefault("indoor", None)
    if it.get("indoor") is None and it.get("location"):
        it["indoor"] = it["location"].get("indoor")
    if it["type"] != "transport":
        it["origin"] = None
    return it


def duration(it: dict) -> int:
    s, e = parse(it["start"]), parse(it.get("end"))
    if it["type"] == "stay":
        return DEFAULT_MIN["stay"]
    if e and e > s:
        return round((e - s).total_seconds() / 60)
    return DEFAULT_MIN.get(it["type"], 45)


def min_duration(it: dict) -> int:
    """Shortest sensible version of an activity (used when shortening to absorb a delay)."""
    full = duration(it)
    if it.get("min_duration"):
        return min(full, int(it["min_duration"]))
    if it["fixed"] or it["type"] in ("transport", "stay"):
        return full
    share = {"activity": 0.6, "meal": 0.75, "other": 0.5}.get(it["type"], 0.6)
    return min(full, max(30 if it["type"] != "other" else 15, round(full * share)))


def start_loc(it: dict) -> dict | None:
    if it["type"] == "transport":
        # a transfer with no stated starting point departs from wherever the traveler already is
        o, dest = it.get("origin"), it.get("location")
        if o and dest and o.get("lat") is not None and dest.get("lat") is not None and maps.km(o, dest) < 1 \
                and duration(it) >= 60:
            return None  # an hours-long journey can't start where it ends: the start point was mislocated
        return o or None
    return it.get("location")


def leg(a: dict | None, b: dict | None) -> dict:
    """Travel between two stops. If either spot is only approximate (town centre) and both are in the same
    area, the real distance is unknown: treat them as the same venue instead of inventing travel time."""
    if a and b and a.get("lat") is not None and b.get("lat") is not None and (a.get("approximate") or b.get("approximate")) \
            and maps.km(a, b) <= 15:
        return {"minutes": 0, "mode": "here", "km": 0, "source": "same area (exact spot unknown)"}
    return maps.travel(a, b)


def end_loc(it: dict) -> dict | None:
    return it.get("location")


def latest_start(it: dict, start: datetime) -> datetime:
    if it.get("latest_start"):
        return parse(it["latest_start"])
    if it["type"] == "stay":
        return start.replace(hour=23, minute=0)
    return add(start, FLEX_WINDOW.get(it["type"], 180))


def is_outdoor(it: dict) -> bool:
    if it.get("indoor") is False:
        return True
    types = set((it.get("location") or {}).get("types", []))
    return it.get("indoor") is None and bool(types & maps.OUTDOOR)


def _rain_overlap(rain: dict | None, s: datetime, e: datetime) -> bool:
    if not rain:
        return False
    rs, re_ = parse(rain.get("start")), parse(rain.get("end"))
    if not rs or not re_:
        return False
    return s < re_ and e > rs


def effective(it: dict, overrides: dict) -> tuple[datetime, datetime]:
    o = overrides.get(it["id"], {})
    s = parse(o.get("start") or it["start"])
    if o.get("end"):
        e = parse(o["end"])
    elif o.get("start") and it.get("end"):  # shifted start keeps the same duration
        e = add(s, duration(it))
    else:
        e = parse(it.get("end")) or add(s, duration(it))
    if it["type"] == "stay":
        e = add(s, DEFAULT_MIN["stay"])
    return s, e


# ------------------------------------------------------------------ simulation

def simulate(items: list[dict], as_of: datetime, overrides: dict | None = None, rain: dict | None = None,
             start_place: dict | None = None, here: str | None = None) -> dict:
    """Walk the itinerary from `as_of`, computing when each item can really happen.

    Items ticked done by the traveler are history: they keep their times, set where the traveler is,
    and are never rescheduled. Earlier items left unticked are "skipped" and kept out of replanning.
    """
    overrides = overrides or {}
    active = [i for i in items if i.get("status") != "cancelled"]
    # Order follows the booked sequence ("seq"), not delayed times: a late train doesn't jump behind the hotel.
    timed = sorted(((effective(i, overrides), i) for i in active), key=lambda x: (parse(x[1].get("seq") or x[1]["start"]), x[0][0]))
    results: dict[str, dict] = {}
    if start_place is None and timed:  # the traveler starts where their first leg starts (e.g. the departure station)
        start_place = start_loc(timed[0][1])
    cur_t, cur_loc = as_of, start_place
    prev_title, position = "your current position", "Start"

    # 0. Ticked-done items fix the traveler's progress.
    done_idx = [n for n, (_, it) in enumerate(timed) if it.get("completed")]
    last_done = max(done_idx) if done_idx else -1
    rest = []
    for n, ((s, e), it) in enumerate(timed):
        if it.get("completed"):
            fin = parse(it.get("completed_at")) or e
            results[it["id"]] = {"status": "completed", "manual": True, "start": fmt(s), "end": fmt(fin),
                                 "reason": f"Marked done{' at ' + hm(fin) if fin else ''}. Never rescheduled.",
                                 "why": "Done: kept exactly as it happened."}
            if n == last_done:
                cur_t, cur_loc, prev_title = max(cur_t, fin), end_loc(it) or cur_loc, it["title"]
                position = f"Done: {it['title']}"
        elif n < last_done:
            results[it["id"]] = {"status": "skipped", "start": fmt(s), "end": fmt(e),
                                 "reason": "Not ticked done, though later stops are. Left out of replanning: tick it, or edit it.",
                                 "why": "Skipped (not marked done)."}
        else:
            rest.append(((s, e), it))

    # Where is the traveler now? A booked slot under way (on the train), or the stop the reported change is about (a delay at
    # Vibhuti Falls means you're at Vibhuti Falls). Unticked stops before it whose time has passed are behind them.
    # (A ticked stop is stronger evidence still: those are handled above.)
    anchor = -1
    for n, ((s, e), it) in enumerate(rest):
        o = overrides.get(it["id"], {})
        if (s <= as_of < e and it["fixed"] and not o.get("cancelled")) or o.get("start") or o.get("end") or it["id"] == here:
            anchor = n  # a flexible stop "in progress by the clock" isn't evidence: you may still be running late

    # 1. Past and in-progress items (by the clock) fix where the traveler is.
    upcoming = []
    for n, ((s, e), it) in enumerate(rest):
        o = overrides.get(it["id"], {})
        if e <= as_of and n < anchor and not it["fixed"] and not o:
            results[it["id"]] = {"status": "completed", "assumed": True, "start": fmt(s), "end": fmt(e),
                                 "reason": "Before where you are now, so counted as done. Tick it to confirm.",
                                 "why": "Earlier than your current stop: counted as done."}
            cur_loc, prev_title, position = end_loc(it) or cur_loc, it["title"], it["title"]
            continue
        if e <= as_of and not it["fixed"] and not o.get("cancelled"):
            upcoming.append(((s, e), it))  # an unticked flexible stop can still happen later
            continue
        if e <= as_of:
            results[it["id"]] = {"status": "completed", "assumed": True, "start": fmt(s), "end": fmt(e),
                                 "reason": f"Its time ({hm(s)}) has passed. Tick it if you did it.", "why": "Booked time already past."}
            if not o.get("cancelled"):
                cur_loc, prev_title = end_loc(it) or cur_loc, it["title"]
                position = it["title"]
        elif s <= as_of < e and not o.get("cancelled") and not o.get("closed"):
            label = "On board" if it["type"] == "transport" else "In progress"
            delayed = o.get("start") or o.get("end")
            results[it["id"]] = {"status": "disrupted" if delayed else "in_progress",
                                 "reason": (o.get("note") or f"Now ends {hm(e)}.") if delayed else f"{label} until {hm(e)}.",
                                 "start": fmt(s), "end": fmt(e),
                                 "why": (f"Delay reported here: now ends {hm(e)}." if delayed else f"{label}; ends {hm(e)}.")}
            cur_t, cur_loc, prev_title, position = max(cur_t, e), end_loc(it) or cur_loc, it["title"], f"{label}: {it['title']}"
        else:
            upcoming.append(((s, e), it))

    # 2. Upcoming items in order.
    for (s, e), it in upcoming:
        o = overrides.get(it["id"], {})
        r = {"start": fmt(s), "end": fmt(e), "booked_start": it["start"]}
        if o.get("cancelled") or o.get("closed"):
            r.update(status="affected", reason=o.get("note") or ("Cancelled." if o.get("cancelled") else "Closed."),
                     why=o.get("note") or "Not available.")
            results[it["id"]] = r
            continue
        tr = leg(cur_loc, start_loc(it))
        if it["type"] == "transport" and cur_loc and start_loc(it) and cur_loc.get("lat") is not None \
                and (start_loc(it) or {}).get("lat") is not None and maps.km(cur_loc, start_loc(it)) <= 30:
            tr = {"minutes": 0, "mode": "here", "km": 0, "source": "departs from where you are"}
        buf = (STATION_BUFFER if it["type"] == "transport" else BUFFER) if tr["minutes"] > 0 else 0
        earliest = add(cur_t, tr["minutes"] + buf)
        path = (f"After {prev_title} ends {hm(cur_t)}: {tr['minutes']} min {'walk' if tr['mode'] == 'walk' else 'by road'}"
                f" + {buf} min buffer → earliest {hm(earliest)}." if tr["minutes"] > 0 else f"Free from {hm(cur_t)} (same place).")
        r.update(travel_min=tr["minutes"], travel_mode=tr["mode"], travel_source=tr["source"], earliest=fmt(earliest), buffer=buf)
        changed = bool(o.get("start") or o.get("end"))
        if it["fixed"]:
            if earliest > s:
                r.update(status="affected", reason=f"Unreachable: earliest arrival {hm(earliest)}, but it starts {hm(s)}.",
                         why=f"{path} Fixed booking at {hm(s)} can't be reached.")
                results[it["id"]] = r
                continue
            ok_reason = ("Start of your journey." if cur_loc is None or tr["mode"] == "here" and it is timed[0][1] else
                         f"Reachable: there by {hm(add(cur_t, tr['minutes']))} for {hm(s)}.")
            r.update(status="disrupted" if changed else "unaffected",
                     reason=(o.get("note") or f"Moved to {hm(s)}.") if changed else ok_reason,
                     why=(f"{path} Booking time {hm(s)} " + ("changed by the provider." if changed else "kept: fixed slot.")))
            new_s, new_e = s, e
        else:
            new_s = max(s, earliest)
            latest = latest_start(it, s)
            if new_s > latest:
                r.update(status="affected", reason=f"Can't fit: earliest {hm(new_s)}, latest sensible start {hm(latest)}.",
                         why=f"{path} Later than the latest sensible start {hm(latest)}.")
                results[it["id"]] = r
                continue
            new_e = add(new_s, duration(it))
            ok, why_open = maps.open_check(it.get("location"), new_s, new_e)
            if ok is False:
                r.update(status="affected", reason=f"{why_open} at {hm(new_s)}.", why=f"{path} {why_open}.")
                results[it["id"]] = r
                continue
            late = round((new_s - s).total_seconds() / 60)
            if it["type"] == "stay" and late > 0:  # check-in is a window: arriving later is fine
                r.update(status="unaffected", reason=f"Check in around {hm(new_s)} (window open until {hm(latest)}).")
            elif late > SMALL_SHIFT:
                r.update(status="shifted", reason=f"Can still happen, starting {hm(new_s)} instead of {hm(s)}.")
            elif late > 0:
                r.update(status="unaffected", reason=f"Starts about {late} min later ({hm(new_s)}); still fine.")
            else:
                r.update(status="disrupted" if changed else "unaffected", reason=o.get("note") or "On track.")
            r["why"] = (f"{path} Starts {hm(new_s)} ({late} min later than planned)." if late > 0
                        else f"{path} Planned start {hm(s)} still works.")
            r.update(start=fmt(new_s), end=fmt(new_e))
        if is_outdoor(it) and _rain_overlap(rain, new_s, new_e) and r["status"] in ("unaffected", "shifted"):
            r.update(status="at_risk", reason="Rain expected while you're outdoors here.")
        results[it["id"]] = r
        cur_t, cur_loc, prev_title = new_e, end_loc(it) or cur_loc, it["title"]

    return {"results": results, "position": position, "as_of": fmt(as_of)}


def impact_summary(sim: dict) -> dict:
    counts: dict[str, int] = {}
    for r in sim["results"].values():
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    needs = counts.get("affected", 0) + counts.get("at_risk", 0) + counts.get("shifted", 0) > 0
    return {"counts": counts, "needs_change": needs}


# ------------------------------------------------------------------ plan validation

def validate_plan(trip: dict, plan_items: list[dict], as_of: datetime, overrides: dict, rain: dict | None,
                  originals: dict, here: str | None = None) -> dict:
    """Check a candidate plan (full list of items after as_of) and repair small timing issues.

    plan_items: items with final start/end; new items have no entry in `originals`.
    Returns {"valid", "checks", "items", "dropped"}.
    """
    prefs = trip["preferences"]
    checks, dropped = [], []
    items = [dict(i) for i in plan_items]

    for _ in range(4):  # repair loop: drop new items that don't fit, then re-check
        sim = simulate(items, as_of, overrides=overrides, rain=rain, here=here)
        bad_new = [i for i in items if i["id"] not in originals and sim["results"].get(i["id"], {}).get("status") == "affected"]
        if not bad_new:
            break
        for i in bad_new:
            dropped.append({"title": i["title"], "why": sim["results"][i["id"]]["reason"]})
            items.remove(i)

    res = sim["results"]
    ok = True
    for i in items:
        r = res.get(i["id"], {})
        if r.get("status") == "affected":
            ok = False
            checks.append({"ok": False, "text": f"{i['title']}: {r['reason']}"})
        # use the engine's corrected times (never for done or skipped items)
        if r.get("start") and r.get("status") not in ("completed", "skipped"):
            i["start"], i["end"] = r["start"], r["end"]
    reachable = all(res.get(i["id"], {}).get("status") != "affected" for i in items)
    checks.insert(0, {"ok": reachable, "text": "Every stop is reachable in time, with travel times and buffers" if reachable
                      else "Some stops can't be reached in time"})

    # opening hours for new or moved activities
    unknown = []
    for i in items:
        if i["type"] in ("activity", "meal") and (i["id"] not in originals or i["start"] != originals[i["id"]]["start"]):
            st, en = parse(i["start"]), parse(i["end"]) or add(parse(i["start"]), duration(i))
            o, why = maps.open_check(i.get("location"), st, en)
            if o is None:
                unknown.append(i["title"])
            elif o is False:
                ok = False
                checks.append({"ok": False, "text": f"{i['title']}: {why}"})
    checks.append({"ok": True, "text": "Opening hours checked" + (f" (unknown for {', '.join(unknown)}: confirm before going)" if unknown else "")})

    # shortened activities stay worthwhile
    too_short = [f"{i['title']} ({duration(i)} min, minimum {min_duration(originals[i['id']])})" for i in items
                 if i["id"] in originals and not originals[i["id"]].get("completed")
                 and duration(i) < min_duration(originals[i["id"]])]
    if too_short:
        ok = False
        checks.append({"ok": False, "text": "Shortened too much: " + ", ".join(too_short)})

    # completed items untouched
    touched = [o["title"] for oid, o in originals.items() if o.get("completed")
               and not any(i["id"] == oid and i["start"] == o["start"] for i in items)]
    if touched:
        ok = False
        checks.append({"ok": False, "text": "Would change completed items: " + ", ".join(touched)})

    # must-do items kept
    kept_ids = {i["id"] for i in items}
    lost_must = [o["title"] for oid, o in originals.items() if o.get("priority") == "must" and oid not in kept_ids
                 and not o.get("completed") and effective(o, overrides)[1] > as_of]
    if lost_must:
        ok = False
        checks.append({"ok": False, "text": "Drops must-do: " + ", ".join(lost_must)})

    # budget
    extra = sum((i.get("est_cost") or 0) for i in items if i["id"] not in originals) + \
        sum((i.get("change_fee") or 0) for i in items)
    within = extra <= prefs["extra_budget"]
    if not within:
        ok = False
    checks.append({"ok": within, "text": f"Extra cost {prefs['currency']} {extra:,.0f} vs limit {prefs['currency']} {prefs['extra_budget']:,.0f}"})

    # rain
    risky = [i["title"] for i in items if res.get(i["id"], {}).get("status") == "at_risk"]
    if rain:
        checks.append({"ok": not risky, "text": "No outdoor stops during the rain" if not risky else "Outdoors in the rain: " + ", ".join(risky)})

    travel_total = sum(res.get(i["id"], {}).get("travel_min", 0) for i in items)
    return {"valid": ok, "checks": checks, "items": items, "dropped": dropped, "results": res,
            "extra_cost": extra, "travel_min": travel_total}
