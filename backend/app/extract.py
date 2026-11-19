"""Turn an uploaded itinerary (PDF, Word, text, image) or a typed description into a structured trip."""
from __future__ import annotations

import base64
import io
import re
import zipfile
from datetime import date

from pypdf import PdfReader

from . import maps, store
from .llm import LLMUnavailable, json_call

ITEM_TYPES = {"transport", "stay", "activity", "meal", "other"}

SYSTEM = """You turn travel itineraries into structured JSON. Extract ONLY what the document states; never invent bookings,
times, prices or references. Use null for anything unknown. Include EVERY timed entry in the text you are given.

Return exactly:
{"title": str, "destination": str (main town/city of the trip), "region": str (state/province + country, e.g. "Karnataka, India"),
 "country_code": two-letter ISO code (e.g. "in"),
 "timezone_offset": "+HH:MM" (best guess from the destination, India = "+05:30"), "travelers": int|null,
 "items": [{"type": "transport"|"stay"|"activity"|"meal"|"other",
            "title": short label e.g. "Train Hyderabad → Hubballi", "Camp check-in", "Explore Vibhuti Falls",
            "start": "YYYY-MM-DDTHH:MM" (departure for transport, check-in for stays),
            "end": "YYYY-MM-DDTHH:MM"|null (arrival for transport, check-out for stays),
            "location": specific place name WITH its town, e.g. "Mirjan Fort, Kumta" or "Murudeshwar Temple, Murudeshwar".
                        Generic places (camp, hotel, restaurant, lunch stop) must name the town: "Campsite, Dandeli".
                        Transport: the ARRIVAL place (airport/station/town). Flights: arrival airport's full name,
            "origin": departure airport/station/place WITH town (transport only, else null),
            "area": the town/locality where this happens (e.g. "Gokarna", "Dandeli", "Honnavar"),
            "provider": str|null, "reference": str|null (PNR, booking id), "cost": number|null,
            "time_kind": how the document labels this time: "suggested" (SUGGESTED/estimated/approx/tentative),
                         "advertised" (ADVERTISED/scheduled), "confirmed" (booked/confirmed), or null if unlabelled,
            "fixed": true only for booked/scheduled slots (tickets, reservations, scheduled trains/flights, ADVERTISED/CONFIRMED times);
                     false for SUGGESTED/estimated times, road transfers in your own vehicle, free time and meals without a reservation,
            "priority": "must"|"high"|"normal"|"optional",
            "indoor": true|false|null, "notes": str|null (e.g. "suggested time", "subject to availability")}]}
Dates must be absolute. If the year is missing, use the next occurrence on or after TODAY. Sort items by start.
Times after midnight in an overnight section belong to the next date.
ONE journey = ONE transport item: departure time as start, arrival time as end (even if the arrival is written under a later
day). Never add separate "departure", "overnight", "reach/arrive" items for the same train/flight/bus.
If a stay has no check-in time, use the time you arrive there (or 14:00) and add "check-in time assumed" to notes.
Entries with a part of day but no clock time (e.g. "Sunset", "Evening") get a sensible time and the note "time assumed"."""

META = """You read the header of a travel itinerary. Return JSON only:
{"title": str, "destination": str (main town/city), "region": "state/province, country", "country_code": "two-letter ISO",
 "timezone_offset": "+HH:MM", "travelers": int|null,
 "first_date": "YYYY-MM-DD" (the date of the FIRST day section listed; if only weekdays are given, the next such
               weekday on or after TODAY; if nothing is given, null),
 "first_day_label": the first day heading exactly as written (e.g. "DAY 0")}"""


def _pdf_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n".join((p.extract_text() or "") for p in reader.pages)[:30000]


def _docx_text(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        xml = z.read("word/document.xml").decode("utf8", "ignore")
    xml = re.sub(r"</w:p>", "\n", xml)
    return re.sub(r"<[^>]+>", "", xml)[:30000]


def file_to_input(filename: str, data: bytes, content_type: str) -> tuple[str, str | list]:
    """Returns (kind, payload) where payload is text, or a multimodal message for images."""
    name = filename.lower()
    if name.endswith(".pdf") or content_type == "application/pdf":
        text = _pdf_text(data)
        if len(text.strip()) < 40:
            raise ValueError("This PDF has no readable text (it may be a scan). Upload a photo or screenshot of it instead.")
        return "text", text
    if name.endswith(".docx"):
        return "text", _docx_text(data)
    if name.endswith((".txt", ".md", ".csv", ".eml", ".html")) or content_type.startswith("text/"):
        return "text", data.decode("utf8", "ignore")[:30000]
    if content_type.startswith("image/") or name.endswith((".png", ".jpg", ".jpeg", ".webp")):
        mime = content_type if content_type.startswith("image/") else "image/jpeg"
        url = f"data:{mime};base64,{base64.b64encode(data).decode()}"
        return "image", [{"type": "text", "text": "Extract the itinerary in this image."},
                         {"type": "image_url", "image_url": {"url": url}}]
    raise ValueError("Unsupported file. Use PDF, Word (.docx), text, or an image (PNG/JPG).")


def _minutes(a: str | None, b: str | None) -> int | None:
    from datetime import datetime
    try:
        return round((datetime.strptime(b[:16], "%Y-%m-%dT%H:%M") - datetime.strptime(a[:16], "%Y-%m-%dT%H:%M")).total_seconds() / 60)
    except (TypeError, ValueError):
        return None


DAY_RE = re.compile(r"(?im)^\s*(DAY\s*(\d+))\b[^\n]*$")


def _sections(text: str) -> tuple[str, list[tuple[str, int, str]]]:
    """Split on 'DAY n' headings. Returns (header, [(heading line, n, section text)])."""
    hits = list(DAY_RE.finditer(text))
    if len(hits) < 2:
        return text, []
    header = text[:hits[0].start()]
    secs = []
    for n, m in enumerate(hits):
        end = hits[n + 1].start() if n + 1 < len(hits) else len(text)
        body = text[m.start():end]
        # stop the last day at the first non-day block (inclusions, exclusions, ...) to keep it focused
        stop = re.search(r"(?m)^\s*(PACKAGE INCLUSIONS|INCLUSIONS|EXCLUSIONS|OPTIONAL|CONFIRM WITH|ROUTE OVERVIEW|TERMS)\b", body)
        secs.append((m.group(0).strip(), int(m.group(2)), body[:stop.start()] if stop else body))
    return header, secs


_LINE_TIME = re.compile(r"^\s*(\d{1,2})(?::(\d{2}))?\s*(AM|PM)?(?:\s*[–-]\s*\d{1,2}(?::\d{2})?\s*(AM|PM)?)?", re.I)


def _time_labels(body: str) -> dict[str, str]:
    """'10:00–11:00 AM (SUGGESTED): ...' -> {'10:00': 'suggested'} from the document text itself."""
    out = {}
    for line in body.splitlines():
        m = _LINE_TIME.match(line)
        up = line.upper()
        kind = "suggested" if "SUGGESTED" in up else "advertised" if "ADVERTISED" in up else "confirmed" if "CONFIRMED" in up else None
        if not m or not kind:
            continue
        h, mm = int(m.group(1)), int(m.group(2) or 0)
        ampm = (m.group(3) or m.group(4) or "").upper()
        if ampm == "PM" and h != 12:
            h += 12
        if ampm == "AM" and h == 12:
            h = 0
        if 0 <= h < 24:
            key = f"{h:02d}:{mm:02d}"
            out[key] = kind if out.get(key) in (None, kind) else "ambiguous"
    return {k: v for k, v in out.items() if v != "ambiguous"}  # two lines at one time with different labels: don't guess


def extract(kind: str, payload: str | list) -> tuple[dict, str]:
    today = date.today().isoformat()
    system = SYSTEM + f"\nTODAY is {today}."
    try:
        if kind == "text":
            header, secs = _sections(payload)
            if secs:
                return _extract_by_day(header, secs, system, today)
        data, provider = json_call(system, payload if kind == "image" else f"Itinerary:\n{payload}", vision=(kind == "image"))
    except LLMUnavailable as e:
        raise ValueError(f"The AI couldn't read this itinerary ({e}). You can still build the trip by hand.") from e
    return data, provider


def _extract_by_day(header: str, secs: list, system: str, today: str) -> tuple[dict, str]:
    """Long itineraries: read the header once, then each day on its own with its exact date, then merge.
    (Asking for everything at once gets cut short and silently drops later days.)"""
    from datetime import datetime, timedelta

    meta, provider = json_call(META + f"\nTODAY is {today}.",
                               f"Header:\n{header[:4000]}\n\nFirst day section:\n{secs[0][2][:1500]}", max_tokens=800)
    try:
        first = datetime.strptime(meta.get("first_date") or "", "%Y-%m-%d").date()
    except ValueError:
        first = None
    first_n = secs[0][1]
    full = header + "".join(body for _, _, body in secs)
    dates = {n: (first + timedelta(days=n - first_n)).isoformat() if first else None for _, n, _ in secs}
    items, start_place, missed = [], None, []
    for heading, n, body in secs:
        when = dates[n]
        plan = ", ".join(f"{h.split('–')[0].strip()} = {dates[k]}" for h, k, _ in secs if dates[k])
        ctx = (f"Trip: {meta.get('title')} in {meta.get('destination')}, {meta.get('region')}. Day dates: {plan}.\n"
               f"YOUR SECTION: '{heading}'" + (f", date {when} ({datetime.strptime(when, '%Y-%m-%d').strftime('%A')})." if when else ".")
               + (f"\nThe traveler starts this day at: {start_place}." if start_place else "")
               + "\nOutput ONLY entries that START in your section. Use the rest of the document only as context "
                 "(e.g. a journey starting here that arrives in a later section gets that arrival as its end; an arrival line "
                 "here that ends a journey from an earlier section is NOT a new item).")
        part = None
        for attempt in range(2):  # an odd reply for one day shouldn't sink the whole import
            try:
                part, provider = json_call(system, f"{ctx}\n\nFULL ITINERARY (context):\n{full[:9000]}\n\nYOUR SECTION:\n{body}",
                                           max_tokens=3500)
            except LLMUnavailable:
                part = None
            if isinstance(part, dict) and any(isinstance(i, dict) and i.get("start") for i in part.get("items") or []):
                break
        if not isinstance(part, dict):
            missed.append(heading)
            continue
        part["items"] = [i for i in (part.get("items") or []) if isinstance(i, dict) and isinstance(i.get("start"), str)]
        if not part["items"]:
            missed.append(heading)
            continue
        labels = _time_labels(body)
        if when:
            nxt = (datetime.strptime(when, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
            part["items"] = [i for i in part.get("items", []) if (i.get("start") or "")[:10] == when
                             or ((i.get("start") or "")[:10] == nxt and (i.get("start") or "")[11:13] < "05")]
        for it in part.get("items", []):
            it.setdefault("notes", None)
            it["day_label"] = heading.split("–")[0].split("-")[0].strip()
            lab = labels.get((it.get("start") or "")[11:16])
            if lab:
                it["time_kind"] = lab  # the document's own label wins over the AI's guess
            items.append(it)
        last = max((i for i in part.get("items", []) if i.get("start")), key=lambda i: i["start"], default=None)
        if last:
            start_place = last.get("location") or last.get("area") or start_place
    seen, merged = set(), []
    for it in sorted([i for i in items if i.get("start")], key=lambda i: i["start"]):
        key = (it["start"], (it.get("title") or "").lower())
        if key in seen:
            continue
        # "Reach Hubballi" at the moment an earlier journey arrives there is that journey's end, not a new item
        short = not it.get("end") or (_minutes(it["start"], it["end"]) or 0) <= 30
        arrival_word = re.match(r"(?i)\s*(reach|arrive|arrival)", it.get("title") or "")
        if it.get("type") == "transport" and (short or arrival_word) and any(
                m.get("type") == "transport" and m.get("end") == it["start"] for m in merged):
            continue
        seen.add(key)
        merged.append(it)
    data = {k: meta.get(k) for k in ("title", "destination", "region", "country_code", "timezone_offset", "travelers")}
    data["items"] = merged
    data["missed_sections"] = missed
    return data, provider


def _same_name(a: str, b: str) -> bool:
    norm = lambda x: re.sub(r"[^a-z0-9 ]", "", x.lower()).replace("mysore", "mysuru").strip()
    a, b = norm(a), norm(b)
    return bool(a and b) and (a in b or b in a)


GENERIC = {"camp", "campsite", "camping site", "campground", "camp ground", "hotel", "resort", "restaurant", "cafe",
           "accommodation", "station", "railway station", "return railway station", "bus stand", "beach", "temple",
           "river", "lunch", "dinner", "breakfast", "market", "town", "city centre", "city center"}

SETTLEMENT = {"city", "town", "village", "hamlet", "suburb", "locality", "neighbourhood", "quarter", "municipality"}

MAX_KM_LOCAL = 250       # a stop this far from the trip's area is almost certainly a namesake elsewhere
MAX_KM_TRANSPORT = 2500  # trains/flights can start far away, but not on another continent


def to_trip(data: dict, source: str) -> dict:
    """Build a stored trip from extracted JSON, locating every place on the map (with sanity checks)."""
    from .engine import normalize_item  # local import: engine imports maps

    trip = store.blank_trip(data.get("title") or "Imported trip", data.get("destination") or "",
                            data.get("timezone_offset") or "+05:30")
    if data.get("travelers"):
        trip["preferences"]["travelers"] = int(data["travelers"])
    country = (data.get("country_code") or "").lower() or None
    region = data.get("region") or ""
    center = None
    if trip["destination"]:
        center = maps.geocode(f"{trip['destination']}, {region}" if region else trip["destination"], country=country) \
            or maps.geocode(trip["destination"], country=country)
        if center and not country:
            country = center.get("country")
    trip["center"] = {"lat": center["lat"], "lng": center["lng"]} if center else None
    located: list[dict] = []

    from datetime import datetime as _dt

    def _t(v):
        try:
            return _dt.strptime(v[:16], "%Y-%m-%dT%H:%M") if v else None
        except ValueError:
            return None

    state = {"time": None}  # time at which we were last at located[-1]

    def plausible(hit: dict, budget_h: float | None) -> bool:
        """Could the traveler really be here? Same country, and within reach of the last place we found, given only
        the TRAVEL time in between (about 90 km/h by road or rail plus slack). A night at camp moves nobody; a
        1-hour transfer can't end up 400 km away; a 16-hour train can. Rules out namesakes elsewhere."""
        if country and hit.get("country") and hit["country"] != country:
            return False
        refs = [p for p in located if p.get("lat") is not None]
        if not refs:
            return not center or maps.km(hit, center) <= MAX_KM_TRANSPORT
        limit = min(MAX_KM_TRANSPORT, 60 + 90 * (budget_h if budget_h is not None else 0.5))
        return maps.km(hit, refs[-1]) <= limit

    TOWN_RADIUS_KM = 25
    towns: dict[str, dict | None] = {}

    big = {x.strip().lower() for x in region.split(",") if x.strip()} | {"india", (country or "").lower()}

    def town_of(area: str | None, budget_h) -> dict | None:
        """Find the town first (the strict geocoder is reliable for towns); it must be reachable in the time available."""
        if not area or area.strip().lower() in big:
            return None  # "Karnataka" or "India" is not a town
        key = area.strip().lower()
        if key in towns:
            return towns[key]
        near = located[-1] if located else center
        hit = None
        # plain name first: adding the trip's state can mislead ("Hyderabad, Karnataka" is a region name in Karnataka)
        for q in dict.fromkeys([area] + ([f"{area}, {region}"] if region and region.split(",")[0].lower() not in key else [])):
            g = maps.geocode(q, near=near, country=country)
            if g and plausible(g, budget_h):
                hit = g
                break
            # a town must be a settlement with that name, not a street or shop called after it
            hit = next((h for h in maps.search(q, near=near, limit=5)
                        if set(h.get("types") or []) & SETTLEMENT and _same_name(h.get("name", ""), area.split(",")[0])
                        and plausible(h, budget_h)), None)
            if hit:
                break
        towns[key] = hit
        return hit

    def locate(name: str | None, area: str | None, budget_h=None, own_town: bool = False) -> dict | None:
        if not name:
            return None
        parts = [x.strip() for x in name.split(",") if x.strip()]
        bare = parts[0]
        # a journey's destination is in the town its own name says, not the area the journey starts in
        named_town = parts[-1] if len(parts) > 1 and parts[-1].lower() not in big else None
        area = None if area and area.strip().lower() in big else area
        # the town written in the place's own name ("Return railway station, Gokarna") beats the AI's area label,
        # which is sometimes the journey's other end
        town_name = (named_town or None) if own_town else (named_town or area)
        town = town_of(town_name, budget_h)
        if town is None and not own_town and area and town_name != area:
            town, town_name = town_of(area, budget_h), area
        if town is None and bare.lower() not in GENERIC:
            t2 = town_of(bare, budget_h)  # the place may itself be a town ("Dandeli", "Murudeshwar")
            if t2 and (len(parts) == 1 or _same_name(t2.get("name", ""), bare)):
                town, town_name = t2, bare

        def accept(loc, approx=False):
            loc = {**loc, "name": name, **({"approximate": True,
                                             "address": f"Approximate: {town_name} (exact spot not found on the map)"} if approx else {})}
            located.append(loc)
            return loc

        if town and town_name and bare.lower() in (town_name.lower(), f"{town_name.lower()} town"):
            return accept(town)  # the stop is the town itself
        anchor = town or (located[-1] if located else center)
        prev = next((p for p in reversed(located) if p.get("lat") is not None), anchor)
        tries = list(dict.fromkeys([f"{bare}, {town_name}" if town_name else name, name, bare]))
        for q in tries:
            cands = [h for h in maps.search(q, near=anchor, limit=5)
                     if not (country and h.get("country") and h["country"] != country)]
            g = maps.geocode(q, near=anchor, country=country)
            if g:
                cands.append(g)
            # Rank, don't take the first: an exact name match first, then the closest.
            if town is not None:
                near_town = [h for h in cands if maps.km(h, town) <= TOWN_RADIUS_KM]
                if near_town:
                    return accept(min(near_town, key=lambda h: (not _same_name(h.get("name", ""), bare), maps.km(h, town))))
            named = [h for h in cands if _same_name(h.get("name", ""), bare) and plausible(h, budget_h)]
            if named:  # the AI may name the wrong town: an exact name match reachable in time also counts
                return accept(min(named, key=lambda h: maps.km(h, prev) if prev else 0))
            if town is None:
                ok = [h for h in cands if plausible(h, budget_h)]
                if ok:
                    return accept(min(ok, key=lambda h: maps.km(h, prev) if prev else 0))
        if town:
            return accept(town, approx=True)  # exact spot unknown: the town centre, clearly marked
        if bare.lower() in GENERIC and prev and prev.get("lat") is not None:
            # "Return railway station" with no known town: near the previous stop, clearly marked as approximate
            town_name = (prev.get("address") or prev.get("name") or "previous stop").replace("Approximate: ", "").split(" (")[0]
            return accept({k: prev[k] for k in ("lat", "lng", "country") if k in prev}, approx=True)
        return {"name": name, "lat": None, "lng": None, "query": name, "source": "unresolved"}

    for raw in sorted([r for r in data.get("items", []) if r.get("start")], key=lambda r: r["start"]):
        transport = raw.get("type") == "transport"
        start_t, end_t = _t(raw.get("start")), _t(raw.get("end"))
        ride_h = ((end_t - start_t).total_seconds() / 3600) if (start_t and end_t and end_t > start_t) else 3.0
        origin = locate(raw.get("origin"), raw.get("area"), 0.5) if transport else None
        # a journey's destination can be as far as the journey is long; other stops must be near the last one
        location = locate(raw.get("location"), raw.get("area"), ride_h if transport else 0.5, own_town=transport)
        notes = raw.get("notes") or ""
        if raw.get("time_kind") == "suggested" and "suggest" not in notes.lower():
            notes = "suggested time" + (f" · {notes}" if notes else "")
        if raw.get("day_label") and raw["day_label"].lower() not in notes.lower():
            notes = f"{raw['day_label']}" + (f" · {notes}" if notes else "")
        item = {
            "type": raw.get("type") if raw.get("type") in ITEM_TYPES else "other",
            "title": raw.get("title") or "Untitled",
            "start": raw["start"], "end": raw.get("end"),
            "location": location, "origin": origin,
            # Only real bookings/scheduled services are fixed; suggested times and own-vehicle transfers can move.
            "fixed": False if raw.get("time_kind") == "suggested" else (
                bool(raw.get("provider") or raw.get("reference")) or raw.get("time_kind") in ("advertised", "confirmed")
                or bool(raw.get("fixed"))),
            # "must" is the traveler's call, set in the app; imports go up to "high"
            "priority": {"must": "high"}.get(raw.get("priority"), raw.get("priority") or "normal"), "indoor": raw.get("indoor"),
            "notes": notes, "source": source,
            "booking": {"provider": raw.get("provider"), "reference": raw.get("reference"), "cost": raw.get("cost"),
                        "status": "confirmed" if (raw.get("reference") or raw.get("provider")) else "none"},
        }
        trip["items"].append(normalize_item(item))
    trip["items"].sort(key=lambda i: i["start"])
    unresolved = [i["title"] for i in trip["items"] if i.get("location") and i["location"].get("lat") is None]
    approx = [i["title"] for i in trip["items"] if (i.get("location") or {}).get("approximate")]
    days = sorted({i["start"][:10] for i in trip["items"]})
    store.log(trip, f"Imported {len(trip['items'])} items over {len(days)} day(s) ({source}).", "import")
    if data.get("missed_sections"):
        store.log(trip, "Couldn't read these parts; please add them by hand: " + ", ".join(data["missed_sections"]), "warning")
    if approx:
        store.log(trip, "Placed at the town centre (exact spot not on the map): " + ", ".join(approx), "warning")
    if unresolved:
        store.log(trip, "Couldn't find these on the map; please fix their locations: " + ", ".join(unresolved), "warning")
    return trip
