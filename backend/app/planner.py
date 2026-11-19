"""Disruption handling: understand the change -> impact -> real alternatives -> 2-3 validated plans -> approve."""
from __future__ import annotations

import copy
import itertools
import json
import re
from datetime import datetime, timedelta

from . import engine, maps, store
from .llm import LLMUnavailable, json_call
from .timeutil import add, fmt, hm, minutes_between, parse

INTEREST_TO_CATEGORY = {"sightseeing": "sightseeing", "culture": "culture", "food": "food", "shopping": "shopping",
                        "nature": "nature", "rest": "rest"}


# ------------------------------------------------------------------ 1. understand the message

PARSE_SYSTEM = """You map a traveler's message about something that changed onto their itinerary.
Return JSON only:
{"summary": one plain sentence of what changed,
 "as_of": "YYYY-MM-DDTHH:MM" or null (the moment the traveler is speaking, only if stated or clearly implied),
 "changes": [{"item_id": id from the list, "kind": "delay"|"cancel"|"closed"|"reschedule"|"skip",
              "new_start": "YYYY-MM-DDTHH:MM"|null, "new_end": "YYYY-MM-DDTHH:MM"|null, "note": short reason}],
 "rain": {"start": "YYYY-MM-DDTHH:MM", "end": "YYYY-MM-DDTHH:MM"} or null,
 "busy": [{"start": "...", "end": "...", "title": short}] (new personal commitments that block time),
 "questions": [only essential unknowns, e.g. "When does the replacement train arrive?"]}
Rules:
- A transport delay of N hours shifts both new_start and new_end by N. If only a new arrival is given, set new_end only.
- A cancelled train/flight with no replacement given: kind "cancel". If replacement times are given: kind "reschedule" with them.
- "Closed" attraction: kind "closed". "Skip X" or "can't make X": kind "skip".
- Rain: give the time window (default the rest of that day 10:00-20:00 if unspecified).
- Use only item ids from the list. Never invent times that the message doesn't imply."""


def compact_items(trip: dict) -> list[dict]:
    return [{"id": i["id"], "type": i["type"], "title": i["title"], "day": parse(i["start"]).strftime("%A %d %b %Y"),
             "start": i["start"], "end": i.get("end"),
             "where": (i.get("location") or {}).get("name"), "fixed": i["fixed"], "priority": i["priority"]}
            for i in sorted(trip["items"], key=lambda x: x["start"]) if i.get("status") != "cancelled"]


def _rule_parse(trip: dict, message: str) -> dict:
    """Small fallback when no AI is reachable: delays, cancellations, closures and rain."""
    msg = message.lower()
    items = [i for i in sorted(trip["items"], key=lambda x: x["start"]) if i.get("status") != "cancelled"]

    def match():
        best, score = None, 0
        for i in items:
            words = [w for w in re.findall(r"[a-z0-9]+", i["title"].lower()) if len(w) > 3]
            s = sum(1 for w in words if w in msg)
            if s > score:
                best, score = i, s
        if best is None and any(w in msg for w in ("train", "flight", "bus", "cab", "taxi")):
            best = next((i for i in items if i["type"] == "transport"), None)
        return best

    out = {"summary": message.strip(), "as_of": None, "changes": [], "rain": None, "busy": [], "questions": []}
    target = match()
    m = re.search(r"(\d+(?:\.\d+)?)\s*(hours?|hrs?|h\b|minutes?|mins?)", msg)
    if target and m and any(w in msg for w in ("delay", "late", "running")):
        mins = float(m.group(1)) * (60 if m.group(2).startswith("h") else 1)
        s = add(parse(target["start"]), mins)
        e = add(parse(target["end"]), mins) if target.get("end") else None
        out["changes"].append({"item_id": target["id"], "kind": "delay", "new_start": fmt(s), "new_end": fmt(e),
                               "note": f"Delayed by {int(mins)} min"})
    elif target and "cancel" in msg:
        out["changes"].append({"item_id": target["id"], "kind": "cancel", "note": "Cancelled"})
    elif target and ("closed" in msg or "shut" in msg):
        out["changes"].append({"item_id": target["id"], "kind": "closed", "note": "Closed"})
    elif target and ("skip" in msg or "can't make" in msg):
        out["changes"].append({"item_id": target["id"], "kind": "skip", "note": "Skipping"})
    if re.search(r"\b(rain|raining|rainy|storm|downpour|monsoon)\b", msg):
        day = (target or (items[0] if items else None))
        d = parse(day["start"]).date() if day else datetime.now().date()
        out["rain"] = {"start": f"{d}T10:00", "end": f"{d}T20:00"}
    if not out["changes"] and not out["rain"]:
        out["questions"].append("I couldn't tell which part of your trip changed. Which booking is affected, and how?")
    return out


def default_as_of(trip: dict, parsed: dict) -> datetime:
    items = {i["id"]: i for i in trip["items"]}
    cands = []
    for c in parsed.get("changes", []):
        it = items.get(c.get("item_id"))
        if it:
            s = parse(it["start"])
            cands.append(s if it["type"] == "transport" else s - timedelta(minutes=60))
    if parsed.get("rain"):
        cands.append(parse(parsed["rain"]["start"]) - timedelta(minutes=60))
    guess = min(cands) if cands else None
    last = last_done_time(trip)
    if last:  # the traveler's progress defines "now" on the trip
        return max([last] + ([guess] if guess else []))
    now = datetime.now().replace(second=0, microsecond=0)
    starts = sorted(parse(i["start"]) for i in trip["items"])
    if starts and starts[0].date() <= now.date() <= (starts[-1] + timedelta(days=1)).date():
        return max(now, guess) if guess and guess > now else now  # the trip is happening now
    return guess or (starts[0] if starts else now)


def here_of(trip: dict, d: dict) -> str | None:
    """The stop the reported change is about: the traveler is there now, so unticked stops before it are behind them."""
    ids = {c.get("item_id") for c in d.get("changes", [])}
    hits = [i for i in trip["items"] if i["id"] in ids]
    return min(hits, key=lambda i: parse(i.get("seq") or i["start"]))["id"] if hits else None


def overrides_for(d: dict) -> dict:
    ov = {}
    for c in d.get("changes", []):
        iid = c.get("item_id")
        if not iid:
            continue
        kind = c.get("kind")
        if kind in ("delay", "reschedule") and (c.get("new_start") or c.get("new_end")):
            ov[iid] = {"start": c.get("new_start"), "end": c.get("new_end"), "note": c.get("note")}
        elif kind == "cancel":
            ov[iid] = {"cancelled": True, "note": c.get("note") or "Cancelled"}
        elif kind == "closed":
            ov[iid] = {"closed": True, "note": c.get("note") or "Closed"}
        elif kind == "skip":
            ov[iid] = {"cancelled": True, "note": c.get("note") or "You're skipping this"}
    return ov


def busy_items(d: dict) -> list[dict]:
    return [engine.normalize_item({"id": f"busy_{n}", "type": "other", "title": b.get("title") or "Busy",
                                   "start": b["start"], "end": b["end"], "fixed": True, "priority": "must",
                                   "location": None, "source": "busy"})
            for n, b in enumerate(d.get("busy") or []) if b.get("start") and b.get("end")]


def analyze(trip: dict, message: str, as_of: str | None = None) -> dict:
    ai = None
    try:
        parsed, ai = json_call(PARSE_SYSTEM, json.dumps({"today": datetime.now().strftime("%Y-%m-%dT%H:%M"),
                                                          "itinerary": compact_items(trip), "message": message}))
        known = {i["id"] for i in trip["items"]}
        parsed["changes"] = [c for c in parsed.get("changes", []) if c.get("item_id") in known]
    except LLMUnavailable:
        parsed = _rule_parse(trip, message)
    # Ignore an "as of" outside the trip's dates (models sometimes answer with today's date).
    ai_as_of = parsed.get("as_of")
    starts = sorted(i["start"][:10] for i in trip["items"])
    try:
        if ai_as_of and starts and not (starts[0] <= parse(ai_as_of).strftime("%Y-%m-%d") <= starts[-1]):
            ai_as_of = None
    except ValueError:
        ai_as_of = None
    parsed["as_of"] = ai_as_of
    # Keep rain on the trip's dates: match a stated weekday to the trip day with that weekday.
    rain = parsed.get("rain")
    trip_days = sorted({i["start"][:10] for i in trip["items"]})
    try:
        if rain and trip_days and rain["start"][:10] not in trip_days:
            wd = parse(rain["start"]).weekday()
            target = next((dd for dd in trip_days if parse(dd + "T00:00").weekday() == wd), trip_days[0] if len(trip_days) == 1 else None)
            if target:
                rain["start"], rain["end"] = target + rain["start"][10:], target + rain["end"][10:]
    except (KeyError, ValueError, TypeError):
        parsed["rain"] = None
    # A cancelled leg with no replacement: ask for the replacement's arrival so plans can use real times.
    items_by_id = {i["id"]: i for i in trip["items"]}
    for c in parsed.get("changes", []):
        it = items_by_id.get(c.get("item_id"))
        if it and it["type"] == "transport" and c.get("kind") == "cancel" and not c.get("new_end"):
            q = (f"Have you found a replacement for {it['title']}? Tell me when it arrives "
                 f"(e.g. 'next train arrives 15:30') and I'll replan around it.")
            parsed.setdefault("questions", [])
            if q not in parsed["questions"]:
                parsed["questions"].append(q)
    d = {"id": store.new_id("dis"), "message": message, "summary": parsed.get("summary") or message,
         "changes": parsed.get("changes", []), "rain": parsed.get("rain"), "busy": parsed.get("busy") or [],
         "questions": parsed.get("questions") or [], "understood_by": ai or "rules", "ignored": [],
         "as_of": as_of or parsed.get("as_of") or fmt(default_as_of(trip, parsed)),
         "created_at": datetime.now().isoformat(timespec="seconds"), "status": "analyzed", "plans": [], "excluded": []}
    ensure_baseline(trip)
    trip["disruptions"].append(d)
    recompute_impact(trip, d)
    store.log(trip, f"Change reported: {d['summary']}", "disruption")
    return d


def structured(trip: dict, summary: str, changes: list[dict], as_of: str | None = None) -> dict:
    """A change we already know precisely (e.g. a booking that failed): no AI needed."""
    parsed = {"changes": changes}
    d = {"id": store.new_id("dis"), "message": summary, "summary": summary, "changes": changes, "rain": None, "busy": [],
         "questions": [], "understood_by": "app", "ignored": [], "as_of": as_of or fmt(default_as_of(trip, parsed)),
         "created_at": datetime.now().isoformat(timespec="seconds"), "status": "analyzed", "plans": [], "excluded": []}
    ensure_baseline(trip)
    trip["disruptions"].append(d)
    recompute_impact(trip, d)
    store.log(trip, f"Change: {summary}", "disruption")
    return d


# ------------------------------------------------------------------ progress (done toggles)

def _sequence(trip: dict) -> list[dict]:
    return sorted([i for i in trip["items"] if i.get("status") != "cancelled"], key=lambda i: i["start"])


def _planned_end(it: dict) -> str:
    return it.get("end") or fmt(add(parse(it["start"]), engine.duration(it)))


def last_done_time(trip: dict) -> datetime | None:
    done = [parse(i.get("completed_at") or _planned_end(i)) for i in trip["items"] if i.get("completed")]
    return max(done) if done else None


def set_done(trip: dict, item_id: str, done: bool, at: str | None = None) -> dict:
    """Tick a stop done: every earlier stop counts as done too. Untick: every later stop is unticked too."""
    seq = _sequence(trip)
    idx = next((n for n, i in enumerate(seq) if i["id"] == item_id), None)
    if idx is None:
        raise ValueError("Item not found (or it was dropped).")
    it = seq[idx]
    changed = []
    if done:
        when = at or _planned_end(it)
        parse(when)
        for prev in seq[:idx]:
            if not prev.get("completed"):
                prev["completed"], prev["completed_at"] = True, _planned_end(prev)
                changed.append(prev["title"])
        it["completed"], it["completed_at"] = True, when
        store.log(trip, f"Marked done: {it['title']} at {when[11:16]}"
                        + (f"; earlier stops marked done too: {', '.join(changed)}" if changed else "") + ".", "progress")
    else:
        for later in seq[idx:]:
            if later.get("completed"):
                later["completed"], later["completed_at"] = False, None
                changed.append(later["title"])
        store.log(trip, "Marked not done: " + ", ".join(changed or [it["title"]]) + ".", "progress")
    # Open changes are re-checked against the new progress.
    for d in trip["disruptions"]:
        if d["status"] in ("analyzed", "planned", "no_plan"):
            recompute_impact(trip, d)
    return {"changed": changed}


def _sanitize(trip: dict, d: dict) -> None:
    """Nothing that already happened can be changed: drop changes to done stops, never check before progress."""
    done_ids = {i["id"]: i for i in trip["items"] if i.get("completed")}
    kept, ignored = [], list(d.get("ignored") or [])
    for c in d.get("changes", []):
        it = done_ids.get(c.get("item_id"))
        if it:
            note = f"Ignored: {it['title']} is already marked done (at {(it.get('completed_at') or '')[11:16]}), so it can't change."
            if note not in ignored:
                ignored.append(note)
        else:
            kept.append(c)
    d["changes"], d["ignored"] = kept, ignored
    last = last_done_time(trip)
    if last and parse(d["as_of"]) < last:
        d["as_of"] = fmt(last)
    if last and d.get("rain"):
        if parse(d["rain"]["end"]) <= last:
            d["ignored"].append("Ignored: the rain window ends before your latest finished stop.")
            d["rain"] = None
        elif parse(d["rain"]["start"]) < last:
            d["rain"]["start"] = fmt(last)
    if not d["changes"] and not d.get("rain") and not d.get("busy") and d["ignored"]:
        d["status"] = "dismissed"
        d["dismiss_reason"] = "This change only concerned parts of the trip you've already finished, so nothing was changed."


# ------------------------------------------------------------------ delay at a specific item

DELAY_MODES = {"late_start": "starts late", "overrun": "runs over", "arrives_late": "arrives late"}


def _delay_change(it: dict, minutes: int, mode: str, as_of: datetime) -> dict:
    s = parse(it["start"])
    e = parse(it.get("end")) or add(s, engine.duration(it))
    if it["type"] == "transport":
        mode = "arrives_late"
        departed = as_of >= s
        ns, ne = (s if departed else add(s, minutes)), add(e, minutes)
        note = f"Arrives {minutes} min late ({hm(ne)} instead of {hm(e)})"
    elif it["type"] == "stay":  # a check-in can only happen later
        mode = "late_start"
        ns, ne = add(s, minutes), add(e, minutes)
        note = f"Check in {minutes} min later: {hm(ns)} instead of {hm(s)}"
    elif mode == "overrun":
        ns, ne = s, add(e, minutes)
        note = f"Runs {minutes} min over: ends {hm(ne)} instead of {hm(e)}"
    else:
        mode = "late_start"
        ns, ne = add(s, minutes), add(e, minutes)
        note = f"Starts {minutes} min late: {hm(ns)} instead of {hm(s)}"
    return {"item_id": it["id"], "kind": "delay", "new_start": fmt(ns), "new_end": fmt(ne), "note": note,
            "delay_min": minutes, "delay_mode": mode, "base_start": it["start"], "base_end": fmt(e)}


def report_delay(trip: dict, item_id: str, minutes: int, mode: str = "auto", as_of: str | None = None) -> dict:
    it = next((i for i in trip["items"] if i["id"] == item_id), None)
    if not it:
        raise ValueError("Unknown item.")
    if it.get("completed"):
        raise ValueError(f"{it['title']} is already marked done (at {(it.get('completed_at') or '')[11:16]}), "
                         "so this delay was ignored and nothing changed. Untick it if it's actually still going on.")
    if not 1 <= minutes <= 24 * 60:
        raise ValueError("Delay must be between 1 minute and 24 hours.")
    s = parse(it["start"])
    last_done = last_done_time(trip)
    if it["type"] == "stay":
        mode = "late_start"
    if mode == "auto":
        mode = "overrun" if (last_done and last_done >= s - timedelta(minutes=30)) else "late_start"
    if as_of:
        when = max([parse(as_of)] + ([last_done] if last_done else []))  # never before what's already finished
    elif mode == "overrun" or it["type"] == "transport":
        when = max([s] + ([last_done] if last_done else []))
    else:
        when = max([s - timedelta(minutes=30)] + ([last_done] if last_done else []))
    change = _delay_change(it, minutes, mode, when)
    return structured(trip, f"{it['title']}: {change['note']}", [change], fmt(when))


def update_delay(trip: dict, d: dict, minutes: int) -> dict:
    """Change the size of a reported delay; everything is recalculated from the original times."""
    if not 1 <= minutes <= 24 * 60:
        raise ValueError("Delay must be between 1 minute and 24 hours.")
    for n, c in enumerate(d["changes"]):
        if c.get("delay_min") is not None:
            it = next(i for i in trip["items"] if i["id"] == c["item_id"])
            base = dict(it, start=c["base_start"], end=c["base_end"])
            d["changes"][n] = _delay_change(base, minutes, c["delay_mode"], parse(d["as_of"]))
            d["summary"] = d["message"] = f"{it['title']}: {d['changes'][n]['note']}"
    recompute_impact(trip, d)
    store.log(trip, f"Delay changed to {minutes} min. Impact recalculated.", "disruption")
    return d


def ensure_baseline(trip: dict) -> None:
    """Keep the itinerary as it was before the first change, for comparison later."""
    if not trip.get("baseline"):
        trip["baseline"] = {"taken_at": datetime.now().isoformat(timespec="seconds"),
                            "items": copy.deepcopy([i for i in trip["items"] if i.get("status") != "cancelled"])}


def base_schedule(trip: dict) -> dict:
    """The schedule as booked (no delays), with travel times between stops."""
    items = [dict(i, completed=False, completed_at=None) for i in trip["items"] if i.get("status") != "cancelled"]
    if not items:
        return {}
    first = min(parse(i["start"]) for i in items)
    sim = engine.simulate(items, first - timedelta(minutes=1))
    return {iid: {"start": next(i["start"] for i in items if i["id"] == iid),
                  "end": next(i.get("end") for i in items if i["id"] == iid) or r.get("end"),
                  "travel_min": r.get("travel_min", 0), "travel_mode": r.get("travel_mode")}
            for iid, r in sim["results"].items()}


def recompute_impact(trip: dict, d: dict) -> None:
    _sanitize(trip, d)
    if d["status"] == "dismissed":
        d["plans"], d["excluded"] = [], []
        store.log(trip, d["dismiss_reason"], "disruption")
        return
    here = here_of(trip, d)
    sim = engine.simulate(trip["items"] + busy_items(d), parse(d["as_of"]), overrides_for(d), d.get("rain"), here=here)
    # Same moment, no change reported: anything already tight in the plan itself isn't caused by this change.
    plain = engine.simulate(trip["items"], parse(d["as_of"]), here=here)["results"]
    rank = {"affected": 3, "at_risk": 2, "shifted": 1}
    for iid, r in sim["results"].items():
        b = plain.get(iid)
        if not b or r["status"] not in rank or iid in overrides_for(d):
            continue
        worse_status = rank[r["status"]] > rank.get(b["status"], 0)
        later = r.get("start") and b.get("start") and parse(r["start"]) > parse(b["start"]) + timedelta(minutes=engine.SMALL_SHIFT)
        if not worse_status and not later:
            if r["status"] == "affected":
                # Can't happen even without this change: still a real problem to solve, just not caused by it.
                r["preexisting"] = True
                r["reason"] = "Already a problem in your own plan (not caused by this change). " + r["reason"]
                continue
            r["plan_status"], r["status"] = r["status"], "unaffected"
            r["reason"] = "Not changed by this: your plan is already tight here. " + r["reason"]
    d["impact"] = {"results": sim["results"], "position": sim["position"], **engine.impact_summary(sim),
                   "base": base_schedule(trip)}
    d["plans"], d["excluded"] = [], []
    d["status"] = "analyzed"
    d.pop("dismiss_reason", None)


# ------------------------------------------------------------------ 2. real-world alternatives

def _anchor_points(trip: dict, d: dict) -> list[dict]:
    res = d["impact"]["results"]
    items = {i["id"]: i for i in trip["items"]}
    pts = []
    for iid, r in res.items():
        it = items.get(iid)
        if it and r["status"] in ("affected", "at_risk") and it["type"] != "transport":
            loc = it.get("location")
            if loc and loc.get("lat") is not None:
                pts.append(loc)
    # where the traveler will be after the disruption (destination of disrupted transport, or last stop)
    for c in d.get("changes", []):
        it = items.get(c.get("item_id"))
        if it and it["type"] == "transport" and it.get("location", {}) and it["location"].get("lat") is not None:
            pts.append(it["location"])
    if not pts and trip.get("center"):
        pts.append(trip["center"])
    uniq = []
    for p in pts:
        if all(maps.km(p, q) > 1.0 for q in uniq):
            uniq.append(p)
    return uniq[:3]


def gather_options(trip: dict, d: dict) -> dict:
    prefs = trip["preferences"]
    cats = [INTEREST_TO_CATEGORY[i] for i in prefs.get("interests", []) if i in INTEREST_TO_CATEGORY][:4] or ["sightseeing", "food"]
    if d.get("rain"):
        cats = [c for c in cats if c in maps.INDOOR_CATEGORIES] or maps.INDOOR_CATEGORIES
    existing = {(i.get("location") or {}).get("place_id") for i in trip["items"]}
    cands, seen = [], set()
    for anchor in _anchor_points(trip, d):
        for p in maps.nearby(anchor, cats, radius_m=2000, limit=20):
            if p["place_id"] in seen or p["place_id"] in existing:
                continue
            if d.get("rain") and p.get("indoor") is False:
                continue
            if prefs.get("accessibility") and "wheelchair" in p.get("types", []):
                pass
            seen.add(p["place_id"])
            p = dict(p, distance_km=round(maps.km(anchor, p), 2))
            cands.append(p)
    interest_rank = {c: n for n, c in enumerate(cats)}

    def interest_of(p):
        types = set(p.get("types", []))
        for c in cats:
            allow = maps.CATEGORIES.get(c, {}).get("allow")
            if allow is None and types & {"attraction", "museum", "monument", "castle", "fort", "memorial", "viewpoint", "palace"}:
                return c
            if allow and types & allow:
                return c
        return None

    def score(p):
        s = -(interest_rank.get(interest_of(p), 5)) * 2 - p["distance_km"]
        s += 1.5 if p.get("hours") else 0
        s += 2 if d.get("rain") and p.get("indoor") else 0
        return s

    cands.sort(key=score, reverse=True)
    cands = cands[:12]
    for n, c in enumerate(cands, 1):
        c["cid"] = f"C{n}"

    # next public-transport options for disrupted transport legs
    transits, items = [], {i["id"]: i for i in trip["items"]}
    for c in d.get("changes", []):
        it = items.get(c.get("item_id"))
        if it and it["type"] == "transport" and (c.get("kind") == "cancel" or
                                                  (c.get("kind") == "delay" and c.get("new_end") and it.get("end")
                                                   and minutes_between(parse(it["end"]), parse(c["new_end"])) >= 120)):
            for n, t in enumerate(maps.transit_options(it.get("origin"), it.get("location"), parse(d["as_of"]),
                                                        trip.get("timezone_offset", "+05:30")), 1):
                transits.append({**t, "tid": f"T{len(transits) + 1}", "replaces": it["id"],
                                 "origin": it.get("origin"), "location": it.get("location")})
    return {"candidates": cands, "transits": transits, "categories": cats}


# ------------------------------------------------------------------ 3. plans

PLAN_SYSTEM = """You are a travel recovery planner. Using ONLY the itinerary items, candidate places (C1..) and
alternative transport options (T1.., e.g. going by road instead of a cancelled train) provided, propose 2 or 3 DISTINCT recovery plans for the rest of the trip from "as_of".
Each plan lists the full remaining schedule in time order. Return JSON only:
{"plans": [{"name": 2-4 words, "summary": one sentence, "tradeoffs": [2-4 short honest points],
            "schedule": [{"ref": item id | "C#" | "T#", "start": "YYYY-MM-DDTHH:MM", "end": "YYYY-MM-DDTHH:MM"|null, "why": short}]}]}
Rules:
- Keep unaffected bookings at their exact times (copy their start/end) and NEVER leave them out. Never move a fixed booking unless it is affected.
- Leave out items you drop; they will be cancelled. Never drop a "must" item if any plan can keep it.
- Use candidates to replace affected or rained-out activities; respect their opening hours and the traveler's interests.
- If a transport leg is cancelled and a T option exists, you may include it (it replaces that leg); weigh its cost and duration.
- Make plans genuinely different. Consider: shortening flexible activities (set an earlier "end"; never below ~60% of
  the planned time), reordering flexible stops between fixed bookings, postponing lower-priority stops to later,
  replacing with nearby candidates, alternative transport, or dropping what no longer fits.
- Items whose status_now is "completed" or "skipped" are history: never include, move or change them.
- Give a short "why" for every entry whose time, length or order changes.
- Allow realistic travel time between stops. Times use the trip's local clock. Stay within the extra budget."""


def _candidate_item(c: dict, start: str, end: str | None) -> dict:
    food = bool(set(c.get("types", [])) & {"restaurant", "cafe", "bakery", "food"})
    s = parse(start)
    e = parse(end) if end else add(s, 60 if food else 75)
    it = engine.normalize_item({"type": "meal" if food else "activity", "title": c["name"], "start": fmt(s), "end": fmt(e),
                                "location": {k: c.get(k) for k in ("name", "address", "lat", "lng", "place_id", "types", "indoor", "hours", "maps_url", "source", "rating")},
                                "fixed": False, "priority": "normal", "indoor": c.get("indoor"), "source": "recovery",
                                "booking": {"status": "none"}})
    it["est_cost"] = c.get("est_cost")
    it["latest_start"] = fmt(add(s, 90))
    return it


def _transit_item(t: dict) -> dict:
    it = engine.normalize_item({"type": "transport", "title": " + ".join(t["lines"]) + f" ({t['from_stop']} → {t['to_stop']})",
                                "start": t["depart"], "end": t["arrive"], "origin": t.get("origin"), "location": t.get("location"),
                                "fixed": True, "priority": "high", "source": "recovery",
                                "booking": {"status": "needs_attention", "provider": " / ".join(t["lines"])}})
    it["transit"] = t
    it["est_cost"] = t.get("est_cost")
    it["notes"] = t.get("note", "")
    return it


def _materialize(trip: dict, d: dict, spec: dict, opts: dict) -> tuple[list[dict], dict]:
    """Turn a plan spec into concrete items (with the disruption's new times baked in)."""
    as_of = parse(d["as_of"])
    ov = overrides_for(d)
    originals = {i["id"]: i for i in trip["items"] if i.get("status") != "cancelled"}
    cands = {c["cid"]: c for c in opts["candidates"]}
    trans = {t["tid"]: t for t in opts["transits"]}
    out, used = [], set()
    # a chosen road/transit alternative replaces the broken leg; never keep both
    for entry in spec.get("schedule", []):
        ref = entry.get("ref") if isinstance(entry, dict) else entry
        if ref in trans:
            used.add(trans[ref]["replaces"])
    # anything done, skipped, finished or under way stays exactly as it is
    res0 = d["impact"]["results"]
    for iid, it in originals.items():
        s, e = engine.effective(it, ov)
        if it.get("completed"):  # history, shown with the actual finish time
            out.append({**it, "end": it.get("completed_at") or it.get("end"), "seq": it["start"]})
            used.add(iid)
        elif res0.get(iid, {}).get("status") == "skipped":
            out.append({**it, "seq": it["start"]})
            used.add(iid)
        elif e <= as_of or (s <= as_of < e and not ov.get(iid, {}).get("cancelled")):
            out.append({**it, "start": fmt(s), "end": fmt(e), "seq": it["start"]})
            used.add(iid)
    for entry in spec.get("schedule", []):
        if isinstance(entry, str):
            entry = {"ref": entry}
        if not isinstance(entry, dict):
            continue
        ref = entry.get("ref")
        if ref in originals and ref not in used:
            if ov.get(ref, {}).get("cancelled") or ov.get(ref, {}).get("closed"):
                continue
            it = originals[ref]
            s, e = engine.effective(it, ov)
            if not it["fixed"]:
                dur = engine.duration({**it, "start": fmt(s), "end": fmt(e)})  # its own length (incl. any reported overrun)
                if entry.get("start"):
                    s = parse(entry["start"])
                if entry.get("duration"):
                    dur = int(entry["duration"])
                elif entry.get("end") and it["type"] != "stay":
                    want = round((parse(entry["end"]) - s).total_seconds() / 60)
                    dur = want if want > 0 else dur  # validation rejects anything below the minimum
                e = add(s, dur)
            out.append({**it, "start": fmt(s), "end": fmt(e) if it.get("end") or it["type"] != "stay" else it.get("end"),
                        "seq": entry.get("seq") or it["start"], "plan_why": entry.get("why")})
            used.add(ref)
        elif ref in cands and entry.get("start") and ref not in used:
            ci = _candidate_item(cands[ref], entry["start"], entry.get("end"))
            ci["seq"], ci["plan_why"] = entry.get("seq") or ci["start"], entry.get("why")
            out.append(ci)
            used.add(ref)
        elif ref in trans and ref not in used:
            ti = _transit_item(trans[ref])
            ti["seq"] = originals.get(trans[ref]["replaces"], {}).get("start", ti["start"])  # takes the cancelled leg's place
            out.append(ti)
            used.add(ref)
    for b in busy_items(d):
        out.append(b)
    out.sort(key=lambda i: (i.get("seq") or i["start"], i["start"]))
    return out, originals


PRIO_W = {"must": 100, "high": 30, "normal": 10, "optional": 3}


def _upcoming(trip: dict, d: dict) -> list[dict]:
    """Items still to come (not done, skipped, past or under way), in booked order."""
    as_of, ov, res = parse(d["as_of"]), overrides_for(d), d["impact"]["results"]
    out = []
    for i in sorted([i for i in trip["items"] if i.get("status") != "cancelled"], key=lambda x: x["start"]):
        s_, e_ = engine.effective(i, ov)
        if i.get("completed") or res.get(i["id"], {}).get("status") in ("completed", "skipped") or e_ <= as_of or s_ <= as_of < e_:
            continue
        out.append(i)
    return out


def _try(trip: dict, d: dict, spec: dict, opts: dict) -> dict:
    items, originals = _materialize(trip, d, spec, opts)
    return engine.validate_plan(trip, items, parse(d["as_of"]), {}, d.get("rain"), originals, here=here_of(trip, d))


def _entry(i: dict, res: dict) -> dict:
    r = res.get(i["id"], {})
    return {"ref": i["id"], "start": r.get("start") or i["start"], "end": r.get("end") or i.get("end")}


def _flexible(i: dict) -> bool:
    return not i["fixed"] and i["type"] in ("activity", "meal", "other")


def _shorten_spec(trip, d, opts, upcoming, ov) -> dict | None:
    """Trim flexible activities (never below their minimum) so later stops still fit. If trimming isn't
    enough, skip the lowest-priority flexible stop in the way, but only to rescue something more important."""
    items = [i for i in upcoming if not ov.get(i["id"], {}).get("cancelled") and not ov.get(i["id"], {}).get("closed")]
    dur = {i["id"]: engine.duration(i) for i in items}
    full = dict(dur)
    dropped: list[str] = []
    spec = None
    for _ in range(60):
        spec = {"schedule": [{"ref": i["id"], "start": engine.effective(i, ov)[0].strftime("%Y-%m-%dT%H:%M"),
                              **({"duration": dur[i["id"]]} if _flexible(i) else {})} for i in items if i["id"] not in dropped]}
        v = _try(trip, d, spec, opts)
        bad = [i for i in items if i["id"] not in dropped and v["results"].get(i["id"], {}).get("status") == "affected"]
        if not bad:
            break
        target = bad[0]
        live_before = [i for i in items if i["id"] not in dropped and i["start"] < target["start"] and _flexible(i)]
        trimmable = [i for i in live_before if dur[i["id"]] > engine.min_duration(i)]
        skippable = [i for i in live_before if PRIO_W[i["priority"]] < PRIO_W[target["priority"]] and i["priority"] != "must"]
        if trimmable:
            pick = min(trimmable, key=lambda i: (PRIO_W[i["priority"]], -items.index(i)))
            dur[pick["id"]] = max(engine.min_duration(pick), dur[pick["id"]] - 10)
        elif skippable:
            pick = min(skippable, key=lambda i: (PRIO_W[i["priority"]], -items.index(i)))
            dropped.append(pick["id"])
            dur.update({i["id"]: full[i["id"]] for i in items})  # retry with full lengths now that a stop is gone
        elif not target["fixed"] and target["priority"] != "must":
            dropped.append(target["id"])
        else:
            return None
    else:
        return None
    cut = {iid: (full[iid], dur[iid]) for iid in dur if dur[iid] < full[iid] and iid not in dropped}
    titles = {i["id"]: i["title"] for i in items}
    rescued = [i for i in items if i["id"] not in dropped
               and d["impact"]["results"].get(i["id"], {}).get("status") == "affected"]
    if not cut and not (dropped and rescued):
        return None
    for e in spec["schedule"]:
        if e["ref"] in cut:
            a, b = cut[e["ref"]]
            e["why"] = f"Shortened from {a} to {b} min so the stops after it still fit."
    parts = []
    if cut:
        parts.append("spend less time at " + ", ".join(f"{titles[k]} ({a}→{b} min)" for k, (a, b) in cut.items()))
    if dropped:
        parts.append("skip " + ", ".join(titles[k] for k in dropped))
    if rescued:
        parts.append("to keep " + ", ".join(i["title"] for i in rescued))
    name = "Shorten to fit" if not dropped else ("Skip to keep bookings" if not cut else "Shorten and skip to keep bookings")
    return {"name": name, "kind": "shorten" if not dropped else "trim", "source": "rules", "schedule": spec["schedule"],
            "summary": parts[0].capitalize() + (", " + ", ".join(parts[1:]) if len(parts) > 1 else "") + "."}


def _reorder_spec(trip, d, opts, upcoming, ov, base_v) -> dict | None:
    """Try every order of flexible stops between fixed bookings; keep the best feasible one."""
    flex_runs, run = [], []
    for i in upcoming:
        if _flexible(i) and not ov.get(i["id"], {}).get("closed") and not ov.get(i["id"], {}).get("cancelled"):
            run.append(i)
        else:
            if len(run) >= 2:
                flex_runs.append(run)
            run = []
    if len(run) >= 2:
        flex_runs.append(run)
    if not flex_runs:
        return None

    def metric(v, group):
        ok = [i for i in group if v["results"].get(i["id"], {}).get("status") not in ("affected", None)]
        late = sum(max(0, (parse(v["results"][i["id"]]["start"]) - parse(i["start"])).total_seconds() / 60) for i in ok)
        return (len(ok) + (5 if v["valid"] else 0), -v["travel_min"] - late / 4)

    order = {i["id"]: i for i in upcoming}
    best_spec = None
    changed_titles = []
    seqs: dict[str, str] = {}
    for group in flex_runs[:3]:
        slots = sorted(i["start"] for i in group)
        best, best_m, ident_m, evals = None, None, None, 0
        for perm in itertools.permutations(group):
            evals += 1
            if evals > 720:
                break
            trial = dict(seqs)
            trial.update({i["id"]: slots[n] for n, i in enumerate(perm)})
            spec = {"schedule": [{"ref": i["id"], "seq": trial.get(i["id"]),
                                  "start": trial.get(i["id"]) or engine.effective(i, ov)[0].strftime("%Y-%m-%dT%H:%M")}
                                 for i in upcoming if not ov.get(i["id"], {}).get("cancelled")]}
            v = _try(trip, d, spec, opts)
            m = metric(v, group)
            if perm == tuple(group):
                ident_m = m
            if best_m is None or m > best_m:
                best, best_m = perm, m
        if best and best != tuple(group) and ident_m is not None and best_m > ident_m:
            seqs.update({i["id"]: slots[n] for n, i in enumerate(best)})
            changed_titles.append(" → ".join(i["title"] for i in best))
    if not changed_titles:
        return None
    spec = {"schedule": [{"ref": i["id"], "seq": seqs.get(i["id"]),
                          "start": seqs.get(i["id"]) or engine.effective(i, ov)[0].strftime("%Y-%m-%dT%H:%M"),
                          **({"why": "Visited in a different order to cut travel time or fit opening hours."} if i["id"] in seqs else {})}
                         for i in upcoming if not ov.get(i["id"], {}).get("cancelled")]}
    v = _try(trip, d, spec, opts)
    spec["schedule"] = [e for e in spec["schedule"] if v["results"].get(e["ref"], {}).get("status") != "affected"
                        or order[e["ref"]]["fixed"]]
    return {"name": "Reorder stops", "kind": "reorder", "source": "rules", "schedule": spec["schedule"],
            "summary": "Visit flexible stops in a smarter order: " + "; ".join(changed_titles) + "."}


def _postpone_spec(trip, d, opts, upcoming, ov) -> dict | None:
    """Move lower-priority stops that are squeezed out to the evening (or the next trip day)."""
    res = d["impact"]["results"]
    movers = [i for i in upcoming if _flexible(i) and i["priority"] in ("normal", "optional") and i["type"] != "meal"
              and res.get(i["id"], {}).get("status") in ("affected", "shifted") and not ov.get(i["id"], {}).get("closed")]
    if not movers:
        return None
    # Try to keep everything else, including bookings that only became unreachable because of the movers.
    stay = [i for i in upcoming if i not in movers and not ov.get(i["id"], {}).get("cancelled")
            and not ov.get(i["id"], {}).get("closed")]
    trial = _try(trip, d, {"schedule": [{"ref": i["id"], "start": engine.effective(i, ov)[0].strftime("%Y-%m-%dT%H:%M")} for i in stay]}, opts)
    stay = [i for i in stay if trial["results"].get(i["id"], {}).get("status") != "affected"]
    sched = [{"ref": i["id"], "start": trial["results"][i["id"]].get("start") or i["start"],
              "end": trial["results"][i["id"]].get("end") or i.get("end")} for i in stay]
    days = sorted({i["start"][:10] for i in trip["items"]})
    moved = []
    for i in movers:
        dur = engine.duration(i)
        placed = False
        for day in [i["start"][:10]] + [x for x in days if x > i["start"][:10]]:
            ends = [parse(e.get("end") or e["start"]) for e in sched if e["start"][:10] == day]
            start = (max(ends) if ends else parse(day + "T10:00")) + timedelta(minutes=30)
            start = start.replace(minute=(start.minute // 15) * 15) + timedelta(minutes=15 if start.minute % 15 else 0)
            if start + timedelta(minutes=dur) > start.replace(hour=21, minute=30):
                continue
            if maps.open_check(i.get("location"), start, start + timedelta(minutes=dur))[0] is False:
                continue
            st = fmt(start)
            sched.append({"ref": i["id"], "start": st, "seq": st, "end": fmt(start + timedelta(minutes=dur)),
                          "why": f"Postponed to {hm(start)}{' on ' + day if day != i['start'][:10] else ''} so the rest of the day isn't squeezed."})
            moved.append(i["title"])
            placed = True
            break
        if not placed:
            continue
    if not moved:
        return None
    return {"name": "Postpone lower priorities", "kind": "postpone", "source": "rules", "schedule": sched,
            "summary": "Keep your bookings and priorities on time; move " + ", ".join(moved) + " to later."}


def _rule_specs(trip: dict, d: dict, opts: dict) -> list[dict]:
    """Deterministic strategies; every one is checked by the same validator as the AI's plans."""
    res = d["impact"]["results"]
    ov = overrides_for(d)
    upcoming = _upcoming(trip, d)
    keep = [i for i in upcoming if res.get(i["id"], {}).get("status") != "affected"]
    transit = [t for t in opts["transits"][:1] if ov.get(t["replaces"], {}).get("cancelled")]  # rules: only for cancelled legs
    base = [_entry(i, res) for i in keep] + [{"ref": t["tid"], "start": t["depart"], "end": t["arrive"]} for t in transit]
    specs = [{"name": "Shift and keep what fits", "kind": "shift", "source": "rules", "schedule": base,
              "summary": "Keep every booking; flexible stops start only as late as travel time requires. Anything that no longer fits is dropped."}]
    base_v = _try(trip, d, {"schedule": base}, opts)

    for fn in (lambda: _shorten_spec(trip, d, opts, upcoming, ov),
               lambda: _reorder_spec(trip, d, opts, upcoming, ov, base_v),
               lambda: _postpone_spec(trip, d, opts, upcoming, ov)):
        sp = fn()
        if sp:
            if transit:
                sp["schedule"] += [{"ref": t["tid"], "start": t["depart"], "end": t["arrive"]} for t in transit]
            specs.append(sp)

    # Replace affected / rained-out activities with the best nearby open alternative.
    replace, used = list(base), set()
    for i in upcoming:
        r = res.get(i["id"], {})
        if i["type"] in ("activity", "meal") and r.get("status") in ("affected", "at_risk"):
            if r.get("status") == "at_risk":
                replace = [e for e in replace if e["ref"] != i["id"]]
            start = parse(r.get("earliest") or r.get("start") or i["start"])
            start = max(start, parse(i["start"]))
            for c in opts["candidates"]:
                if c["cid"] in used:
                    continue
                if d.get("rain") and c.get("indoor") is not True:
                    continue
                ok, _ = maps.open_check(c, start, add(start, 75))
                if ok is False:
                    continue
                replace.append({"ref": c["cid"], "start": fmt(start), "why": f"Nearby alternative to {i['title']}, open at {hm(start)}."})
                used.add(c["cid"])
                break
    if any(e["ref"].startswith("C") for e in replace):
        specs.append({"name": "Swap in nearby options", "kind": "swap", "source": "rules",
                      "summary": "Replace what you'd miss with open places nearby.",
                      "schedule": sorted(replace, key=lambda e: e["start"])})

    easy = [e for e, i in zip(base, keep + [None] * len(transit))
            if i is None or i["fixed"] or i["type"] in ("stay", "meal", "transport") or i["priority"] in ("must", "high")]
    if len(easy) < len(base):
        specs.append({"name": "Take it easy", "kind": "easy", "source": "rules", "schedule": easy,
                      "summary": "Keep only bookings and priorities; free up the rest of the time."})
    return specs


def _ai_specs(trip: dict, d: dict, opts: dict) -> tuple[list[dict], str | None]:
    res = d["impact"]["results"]
    payload = {
        "as_of": d["as_of"], "what_changed": d["summary"], "rain": d.get("rain"),
        "traveler": {k: trip["preferences"][k] for k in ("interests", "pace", "extra_budget", "currency", "travelers", "group", "accessibility")},
        "itinerary": [{**ci, "status_now": res.get(ci["id"], {}).get("status"), "reason": res.get(ci["id"], {}).get("reason"),
                       "earliest_possible": res.get(ci["id"], {}).get("start"),
                       "min_minutes": engine.min_duration(next(i for i in trip["items"] if i["id"] == ci["id"]))} for ci in compact_items(trip)],
        "busy": d.get("busy"),
        "candidates": [{"id": c["cid"], "name": c["name"], "types": c.get("types", [])[:4], "indoor": c.get("indoor"),
                        "km_away": c["distance_km"], "rating": c.get("rating"), "est_cost": c.get("est_cost"),
                        "hours_today": _hours_text(c, parse(d["as_of"]))} for c in opts["candidates"]],
        "transport_alternatives": [{"id": t["tid"], "depart": t["depart"], "arrive": t["arrive"], "how": t["lines"], "replaces": t["replaces"],
                                    "est_cost": t.get("est_cost"), "note": t.get("note")}
                            for t in opts["transits"]],
    }
    try:
        data, provider = json_call(PLAN_SYSTEM, json.dumps(payload), temperature=0.4)
    except LLMUnavailable:
        return [], None
    specs = []
    for p in data.get("plans", [])[:3]:
        if p.get("schedule"):
            specs.append({**p, "source": provider})
    return specs, provider


def _hours_text(place: dict, day: datetime) -> str:
    h = (place.get("hours") or {}).get(str(day.weekday()))
    if h is None:
        return "unknown"
    if not h:
        return "closed"
    return ", ".join(f"{o // 60:02d}:{o % 60:02d}-{c // 60:02d}:{c % 60:02d}" for o, c in h)


def _mins(a: datetime, b: datetime) -> int:
    return round((b - a).total_seconds() / 60)


def _describe(trip: dict, d: dict, spec: dict, v: dict, originals: dict) -> dict:
    as_of = parse(d["as_of"])
    ov = overrides_for(d)
    res, res0 = v["results"], d["impact"]["results"]
    plan_ids = {i["id"] for i in v["items"]}
    def _postponed(i):
        o = originals.get(i["id"])
        if not o:
            return False
        eff_s = engine.effective(o, ov)[0]
        return _mins(eff_s, parse(i["start"])) >= 120 or i["start"][:10] != fmt(eff_s)[:10]

    skip_rank = {i["id"] for i in v["items"] if _postponed(i)}
    up_orig = [oid for oid, o in sorted(originals.items(), key=lambda kv: kv[1]["start"]) if oid not in skip_rank]
    plan_order = [i["id"] for i in v["items"] if i["id"] in originals and i["id"] not in skip_rank]
    orig_rank = {oid: n for n, oid in enumerate([x for x in up_orig if x in plan_order])}
    plan_rank = {oid: n for n, oid in enumerate(plan_order)}
    rows, cons, shortened_min = [], [], 0
    for i in v["items"]:
        iid, r = i["id"], res.get(i["id"], {})
        flags: list[str] = []
        was = was_end = None
        if iid.startswith("busy_"):
            tag = "busy"
        elif iid not in originals:
            tag = "new"
        else:
            o = originals[iid]
            eff_s, eff_e = engine.effective(o, ov)
            was, was_end = o["start"], o.get("end")
            st0 = res0.get(iid, {}).get("status")
            if o.get("completed") or (st0 == "completed"):
                tag = "done"
            elif st0 == "skipped":
                tag = "skipped"
            elif eff_e <= as_of:
                tag = "done"
            else:
                now_s = parse(i["start"])
                dur_now, dur_eff = engine.duration(i), _mins(eff_s, eff_e)
                if ov.get(iid, {}).get("start") or ov.get(iid, {}).get("end"):
                    flags.append("updated")
                if i["start"] != fmt(eff_s):
                    flags.append("moved")
                if o["type"] not in ("stay", "transport") and dur_now <= dur_eff - 5:
                    flags.append("shortened")
                    shortened_min += dur_eff - dur_now
                    cons.append(f"Shortens {o['title']} ({dur_eff}→{dur_now} min)")
                if iid not in skip_rank and plan_rank.get(iid) != orig_rank.get(iid):
                    flags.append("reordered")
                if _mins(eff_s, now_s) >= 120 or i["start"][:10] != fmt(eff_s)[:10]:
                    flags.append("postponed")
                    cons.append(f"Moves {o['title']} to {hm(now_s)}")
                tag = next((t for t in ("postponed", "reordered", "shortened", "moved", "updated") if t in flags), "kept")
        rows.append({"id": iid, "title": i["title"], "type": i["type"], "start": i["start"], "end": i.get("end"),
                     "was": was if tag not in ("kept", "done", "skipped", "new", "busy") else None, "was_end": was_end,
                     "tag": tag, "flags": flags, "why": i.get("plan_why") or r.get("why") or "",
                     "duration": engine.duration(i) if i["type"] != "stay" else None,
                     "travel_min": r.get("travel_min", 0), "travel_mode": r.get("travel_mode"),
                     "status": r.get("status"), "location": i.get("location"), "est_cost": i.get("est_cost"),
                     "transit": i.get("transit")})
    if any("reordered" in r["flags"] for r in rows):
        cons.append("Changes the order: " + " → ".join(r["title"] for r in rows if r["tag"] not in ("done", "skipped", "busy")))
    removed = [{"id": oid, "title": o["title"], "start": o["start"], "booked": o["booking"].get("status") != "none",
                "why": res0.get(oid, {}).get("reason") or "Left out of this plan"}
               for oid, o in originals.items() if oid not in plan_ids and not o.get("completed")
               and res0.get(oid, {}).get("status") != "skipped" and engine.effective(o, ov)[1] > as_of]
    new = [r for r in rows if r["tag"] == "new"]
    remaining = [oid for oid in originals if res0.get(oid, {}).get("status") not in ("completed", "skipped")
                 and not originals[oid].get("completed") and engine.effective(originals[oid], ov)[1] > as_of]
    kept_n = sum(1 for oid in remaining if oid in plan_ids)
    cur = trip["preferences"]["currency"]
    pros = []
    if remaining and kept_n == len(remaining):
        pros.append("Keeps every remaining stop")
    elif remaining:
        pros.append(f"Keeps {kept_n} of {len(remaining)} remaining stops")
    kept_prio = [originals[oid]["title"] for oid in remaining if oid in plan_ids and originals[oid]["priority"] in ("must", "high")]
    if kept_prio:
        pros.append("Keeps priorities: " + ", ".join(kept_prio[:3]))
    if new:
        pros.append("Adds " + ", ".join(r["title"] for r in new))
    pros.append("No known extra cost" if not v["extra_cost"] else f"Extra cost about {cur} {v['extra_cost']:,.0f}")
    if removed:
        cons.insert(0, "Drops " + ", ".join(r["title"] for r in removed))
    if v["extra_cost"]:
        cons.append(f"Costs about {cur} {v['extra_cost']:,.0f} more")
    last = max((parse(r["end"] or r["start"]) for r in rows), default=as_of)
    if last.hour >= 21:
        cons.append(f"Long day: ends {hm(last)}")
    score = (sum(PRIO_W[originals[oid]["priority"]] for oid in remaining if oid in plan_ids) + 4 * len(new)
             - v["extra_cost"] / 250 - v["travel_min"] / 20 - shortened_min / 15
             - 3 * sum("postponed" in r["flags"] for r in rows) - sum("reordered" in r["flags"] for r in rows) * 0.5)
    counts = {t: sum(r["tag"] == t for r in rows) for t in ("kept", "moved", "shortened", "reordered", "postponed", "new")}
    counts["removed"] = len(removed)
    return {
        "id": store.new_id("plan"), "name": spec.get("name") or "Plan", "kind": spec.get("kind", "ai"),
        "summary": spec.get("summary") or "", "tradeoffs": (spec.get("tradeoffs") or [])[:4] or (pros + cons)[:4],
        "pros": pros, "cons": cons or ["No downsides found by the checks"], "facts": pros + cons,
        "source": spec.get("source", "rules"), "schedule": rows, "removed": removed, "checks": v["checks"],
        "dropped": v["dropped"], "valid": v["valid"], "extra_cost": v["extra_cost"], "travel_min": v["travel_min"],
        "day_ends": hm(last), "counts": counts, "score": round(score, 1), "_items": v["items"],
    }


def make_plans(trip: dict, d: dict) -> dict:
    opts = gather_options(trip, d)
    specs, provider = _ai_specs(trip, d, opts)
    specs += _rule_specs(trip, d, opts)
    plans, excluded, seen = [], [], set()
    for spec in specs:
        items, originals = _materialize(trip, d, spec, opts)
        v = engine.validate_plan(trip, items, parse(d["as_of"]), {}, d.get("rain"), originals, here=here_of(trip, d))
        # Never drop a confirmed booking that still works.
        kept_ids = {i["id"] for i in v["items"]}
        res0 = d["impact"]["results"]
        lost = [o["title"] for oid, o in originals.items() if oid not in kept_ids
                and o["booking"].get("status") in ("confirmed", "pending")
                and res0.get(oid, {}).get("status") in ("unaffected", "shifted", "in_progress")]
        if lost:
            v["valid"] = False
            v["checks"].append({"ok": False, "text": "Drops a confirmed booking that still works: " + ", ".join(lost)})
        else:
            v["checks"].append({"ok": True, "text": "Keeps every confirmed booking that still works"})
        sig = tuple((i["id"] if i["id"] in originals else i["title"], i["start"]) for i in v["items"])
        if sig in seen:
            continue
        seen.add(sig)
        p = _describe(trip, d, spec, v, originals)
        (plans if v["valid"] else excluded).append(p)
    plans.sort(key=lambda p: -p["score"])
    plans = plans[:4]
    if plans:
        plans[0]["recommended"] = True
    d["plans"], d["excluded"] = plans, excluded
    d["options"] = {"candidates": [{k: c.get(k) for k in ("cid", "name", "lat", "lng", "indoor", "rating", "est_cost", "distance_km", "maps_url", "source")}
                                   for c in opts["candidates"]], "transits": opts["transits"], "categories": opts["categories"],
                    "planned_by": provider or "rules"}
    d["status"] = "planned" if plans else "no_plan"
    store.log(trip, f"{len(plans)} recovery plan(s) ready ({provider or 'rules'}), {len(excluded)} rejected by checks.", "plan")
    return d


# ------------------------------------------------------------------ 4. approve

def approve(trip: dict, d: dict, plan_id: str) -> dict:
    plan = next((p for p in d["plans"] if p["id"] == plan_id), None)
    if not plan:
        raise ValueError("That plan is no longer available.")
    ov = overrides_for(d)
    ensure_baseline(trip)
    d["before"] = copy.deepcopy(trip["items"])  # the itinerary just before this change, for comparison
    by_id = {i["id"]: i for i in trip["items"]}
    actions = []

    def action(item, kind, title, detail, provider=None):
        a = {"id": store.new_id("act"), "disruption_id": d["id"], "item_id": item["id"] if item else None, "kind": kind,
             "title": title, "detail": detail, "provider": provider, "status": "needs_attention", "reference": None,
             "created_at": datetime.now().isoformat(timespec="seconds"), "history": [{"status": "needs_attention", "at": datetime.now().isoformat(timespec="seconds")}]}
        actions.append(a)
        return a

    # The disruption itself is now a fact (e.g. the train's new times).
    for iid, o in ov.items():
        it = by_id.get(iid)
        if not it:
            continue
        if o.get("start") or o.get("end"):
            it["previous_start"] = it.get("previous_start") or it["start"]
            s, e = engine.effective(it, ov)
            it["start"], it["end"] = fmt(s), fmt(e) if it.get("end") else it.get("end")
            it["notes"] = (o.get("note") or "Changed") + (f". {it['notes']}" if it.get("notes") else "")
        if o.get("cancelled") or o.get("closed"):
            it["status"] = "cancelled"
            it["cancel_reason"] = o.get("note")

    plan_items = {i["id"]: i for i in plan["_items"]}
    for row in plan["schedule"]:
        if row["tag"] in ("moved", "shortened", "reordered", "postponed"):
            it = by_id[row["id"]]
            if it.get("completed"):
                continue  # done items are history
            it["previous_start"] = it.get("previous_start") or it["start"]
            it["previous_end"] = it.get("previous_end") or it.get("end")
            start_changed = row["start"] != it["start"]
            it["start"] = row["start"]
            if it.get("end") and row.get("end"):
                it["end"] = row["end"]
            it["changed_by"] = d["id"]
            it["change_note"] = row.get("why") or row["tag"]
            if start_changed and it["fixed"] and it["booking"].get("status") not in ("none", None):  # flexible items move freely
                it["booking"]["status"] = "needs_attention"
                action(it, "change", f"Move {it['title']} to {hm(parse(row['start']))}",
                       f"Ask {it['booking'].get('provider') or 'the provider'} to change your booking"
                       + (f" (ref {it['booking']['reference']})" if it["booking"].get("reference") else "") + ".",
                       it["booking"].get("provider"))
        elif row["tag"] == "new":
            new = dict(plan_items[row["id"]])
            new["added_by"] = d["id"]
            trip["items"].append(new)
            if new["type"] == "transport":
                action(new, "book", f"Book {new['title']}", f"Departs {hm(parse(new['start']))}, arrives {hm(parse(new['end']))}. Buy the ticket, then mark it confirmed with the reference.",
                       new["booking"].get("provider"))
            elif new.get("est_cost"):
                new["booking"]["status"] = "needs_attention"
                action(new, "book", f"Book or pay for {new['title']}", f"Estimated {trip['preferences']['currency']} {new['est_cost']:,.0f}. Check tickets/entry before you go.")
    for r in plan["removed"]:
        it = by_id.get(r["id"])
        if not it or it["status"] == "cancelled" or it.get("completed"):
            continue
        it["status"] = "cancelled"
        it["cancel_reason"] = f"Dropped by plan '{plan['name']}'"
        if it["booking"].get("status") not in ("none", None):
            it["booking"]["status"] = "needs_attention"
            action(it, "cancel", f"Cancel {it['title']}",
                   f"Contact {it['booking'].get('provider') or 'the provider'}"
                   + (f" (ref {it['booking']['reference']})" if it["booking"].get("reference") else "")
                   + " to cancel and ask about a refund.", it["booking"].get("provider"))
    for b in d.get("busy") or []:
        trip["items"].append(engine.normalize_item({"type": "other", "title": b.get("title") or "Busy", "start": b["start"],
                                                     "end": b["end"], "fixed": True, "priority": "must", "source": "recovery"}))
    trip["items"].sort(key=lambda i: i["start"])
    trip["actions"].extend(actions)
    d["status"] = "resolved"
    d["chosen"] = {"id": plan["id"], "name": plan["name"]}
    c = plan["counts"]
    store.log(trip, f"Approved '{plan['name']}': {c['moved']} moved, {c['shortened']} shortened, {c['reordered']} reordered, "
                    f"{c['postponed']} postponed, {c['new']} added, {c['removed']} dropped. "
                    f"{len(actions)} task(s) need your attention.", "approval")
    return {"plan": plan["name"], "actions": len(actions)}


# ------------------------------------------------------------------ 5. booking tasks

def update_action(trip: dict, action_id: str, status: str, reference: str | None = None) -> dict:
    if status not in ("needs_attention", "pending", "confirmed", "failed"):
        raise ValueError("Unknown status.")
    a = next((x for x in trip["actions"] if x["id"] == action_id), None)
    if not a:
        raise ValueError("Unknown task.")
    a["status"] = status
    if reference:
        a["reference"] = reference
    a["history"].append({"status": status, "at": datetime.now().isoformat(timespec="seconds"), "reference": reference})
    it = next((i for i in trip["items"] if i["id"] == a.get("item_id")), None)
    if it:
        if a["kind"] == "cancel" and status == "confirmed":
            it["booking"]["status"] = "cancelled"
        else:
            it["booking"]["status"] = {"failed": "needs_attention"}.get(status, status)
        if reference and a["kind"] != "cancel":
            it["booking"]["reference"] = reference
    store.log(trip, f"Task '{a['title']}' → {status}" + (f" (ref {reference})" if reference else ""), "action")
    return a
