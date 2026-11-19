"""Real-world location data from open-source tools (no Google):

  geopy (Nominatim)     geocoding itinerary places; geodesic distances
  Photon (komoot)       search-as-you-type place picker (OSM data, built for autocomplete)
  openrouteservice      nearby POIs (OSM tags incl. opening_hours), travel-time matrix,
                        road route geometry for maps, road alternatives for broken transport legs
  osmnx                 extra opening hours from OpenStreetMap (Overpass) when that server is up
  Open-Meteo            rain forecast

Every result carries its source. Missing data stays "unknown" rather than guessed.
"""
from __future__ import annotations

import math
import re
import ssl
import time
from datetime import datetime, timedelta

import certifi
import httpx

from .config import env, offline

UA = "disruption-copilot-hackathon/2.0"
_ssl = ssl.create_default_context(cafile=certifi.where())

INDOOR = {"museum", "art_gallery", "gallery", "arts_centre", "shopping_mall", "mall", "cafe", "restaurant", "fast_food",
          "spa", "cinema", "theatre", "aquarium", "library", "books", "department_store", "bakery", "bar", "pub",
          "planetarium", "indoor", "ice_cream", "food_court", "community_centre", "place_of_worship", "temple"}
OUTDOOR = {"park", "garden", "zoo", "theme_park", "beach", "viewpoint", "nature_reserve", "lake", "picnic_site",
           "playground", "fountain", "monument", "ruins", "castle", "fort", "marketplace", "attraction"}
NOT_WORTH = {"fountain", "information", "bench", "toilets", "atm", "parking", "bicycle_parking", "waste_basket",
             "post_box", "telephone", "drinking_water", "vending_machine", "clock", "shelter"}

# Interest -> ORS POI category groups + allowed category names.
# Groups: 130 arts & culture, 220 historic, 260 leisure & entertainment, 330 natural, 420 shops, 560 sustenance, 620 tourism
CATEGORIES = {
    "sightseeing": {"groups": [620, 220], "allow": None},
    "culture": {"groups": [130, 620], "allow": {"museum", "gallery", "arts_centre", "theatre", "planetarium", "artwork"}},
    "food": {"groups": [560], "allow": {"restaurant", "cafe", "fast_food", "food_court", "ice_cream", "bakery"}},
    "shopping": {"groups": [420, 360], "allow": {"mall", "marketplace", "department_store", "books", "gift", "clothes", "craft", "art"}},
    "nature": {"groups": [330, 260], "allow": {"park", "garden", "nature_reserve", "zoo", "beach", "viewpoint", "lake", "water_park"}},
    "rest": {"groups": [560, 260], "allow": {"cafe", "spa", "library", "park", "garden"}},
}
INDOOR_CATEGORIES = ["culture", "shopping", "food", "rest"]
OSMNX_TAGS = {"tourism": True, "historic": True, "amenity": ["restaurant", "cafe", "arts_centre", "library", "marketplace"],
              "leisure": ["park", "garden"], "shop": ["mall", "department_store", "books"]}
EST_COST = {"museum": 100, "gallery": 50, "zoo": 150, "theme_park": 800, "planetarium": 100, "restaurant": 500,
            "cafe": 250, "fast_food": 200, "spa": 1500, "cinema": 300, "park": 0, "garden": 20, "viewpoint": 0,
            "marketplace": 0, "attraction": None}

_cache: dict = {}
_down: dict[str, float] = {}


SERVICE_NAMES = {"geo": "nominatim", "search": "photon", "osmnx": "osmnx (opening hours)", "nearby": "openrouteservice POIs",
                 "dir": "openrouteservice routes", "rain": "open-meteo"}


def _cached(key, fn, ttl=3600):
    from . import auth  # the activity monitor counts every outside call made for a request
    name = SERVICE_NAMES.get(key[0], key[0])
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        auth.track("cache", name, 0)
        return hit[1]
    t0 = time.time()
    val = fn()
    auth.track("maps", name, (time.time() - t0) * 1000, ok=val is not None)
    _cache[key] = (time.time(), val)
    return val


def _service_up(name: str) -> bool:
    return time.time() >= _down.get(name, 0)


def _mark_down(name: str, seconds: int = 600):
    _down[name] = time.time() + seconds


def _ors():
    import openrouteservice
    key = env("ORS_API_KEY")
    return openrouteservice.Client(key=key, timeout=15, retry_over_query_limit=False) if key else None


def provider() -> str:
    return "osm"


def status() -> dict:
    return {"places": "OpenStreetMap (Nominatim, openrouteservice POIs, osmnx)",
            "routes": "openrouteservice" if env("ORS_API_KEY") else "estimate",
            "transit": False, "road_alternatives": bool(env("ORS_API_KEY")),
            "overpass": "up" if _service_up("overpass") else "busy (skipped)"}


# ------------------------------------------------------------------ helpers

def km(a: dict, b: dict) -> float:
    from geopy.distance import geodesic
    return geodesic((a["lat"], a["lng"]), (b["lat"], b["lng"])).km


def _indoor(types: list[str]) -> bool | None:
    t = set(types)
    if t & INDOOR:
        return True
    if t & OUTDOOR:
        return False
    return None


_DAYS = {"Mo": 0, "Tu": 1, "We": 2, "Th": 3, "Fr": 4, "Sa": 5, "Su": 6}


def _osm_hours(s: str | None) -> dict | None:
    """Parse common OSM opening_hours ('Mo-Sa 09:00-17:00; Su off', '10:00-18:00', '24/7'). Unknown -> None."""
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    if s == "24/7":
        return {str(d): [[0, 1440]] for d in range(7)}
    hours: dict[int, list] = {d: [] for d in range(7)}
    try:
        for rule in [r.strip() for r in s.split(";") if r.strip()]:
            if "PH" in rule:
                continue
            m = re.match(r"^((?:[A-Z][a-z](?:-[A-Z][a-z])?,?)+)?\s*(.*)$", rule)
            days_part, times_part = m.group(1), m.group(2).strip()
            days = set(range(7))
            if days_part:
                days = set()
                for seg in days_part.split(","):
                    if "-" in seg:
                        a, b = (_DAYS[x] for x in seg.split("-"))
                        days |= set(range(a, b + 1)) if a <= b else set(range(a, 7)) | set(range(0, b + 1))
                    elif seg:
                        days.add(_DAYS[seg])
            if times_part in ("off", "closed"):
                for d in days:
                    hours[d] = []
                continue
            spans = []
            for t in times_part.split(","):
                a, b = t.strip().split("-")
                ah, am = map(int, a.split(":"))
                bh, bm = map(int, b.split(":"))
                end = bh * 60 + bm
                spans.append([ah * 60 + am, end if end > ah * 60 + am else 1440])
            for d in days:
                hours[d] = spans
    except Exception:  # noqa: BLE001
        return None
    return {str(k): v for k, v in hours.items()}


def open_check(place: dict | None, start: datetime, end: datetime) -> tuple[bool | None, str]:
    hours = (place or {}).get("hours")
    if not hours:
        return None, "Opening hours unknown"
    spans = hours.get(str(start.weekday()), [])
    s = start.hour * 60 + start.minute
    e = s + max(1, round((end - start).total_seconds() / 60))
    for o, c in spans:
        if o <= s and e <= c:
            return True, f"Open {o // 60:02d}:{o % 60:02d}–{c // 60:02d}:{c % 60:02d}"
    if not spans:
        return False, "Closed that day"
    txt = ", ".join(f"{o // 60:02d}:{o % 60:02d}–{c // 60:02d}:{c % 60:02d}" for o, c in spans)
    return False, f"Not open for the whole visit (hours {txt})"


# ------------------------------------------------------------------ geocoding (geopy / Nominatim) and place picker (Photon)

def _nominatim():
    from geopy.geocoders import Nominatim
    return Nominatim(user_agent=UA, timeout=10, ssl_context=_ssl)


_last_nominatim = [0.0]


def geocode(query: str, near: dict | None = None, country: str | None = None) -> dict | None:
    """Locate one named place (used when importing itineraries). Nominatim allows 1 request/second.
    `country` (ISO code like "in") restricts results to that country."""
    if offline() or not query.strip():
        return None

    def run():
        if _service_up("nominatim"):
            for attempt in range(2):  # a busy moment shouldn't send us to a looser search
                try:
                    wait = (1.05 if attempt == 0 else 2.5) - (time.time() - _last_nominatim[0])
                    if wait > 0:
                        time.sleep(wait)
                    kw = {"extratags": True, "addressdetails": True}
                    if country:
                        kw["country_codes"] = [country]
                    if near:
                        kw.update(viewbox=[(near["lat"] - 0.6, near["lng"] - 0.6), (near["lat"] + 0.6, near["lng"] + 0.6)], bounded=False)
                    r = _nominatim().geocode(query, **kw)
                    _last_nominatim[0] = time.time()
                    if r:
                        tags = r.raw.get("extratags") or {}
                        types = [r.raw.get("type", ""), r.raw.get("class", "")]
                        # the place's real name, so callers can tell "Kagala Beach" from the "Nirvana Beach" they asked for
                        return {"name": r.raw.get("name") or query.split(",")[0].strip() or r.address.split(",")[0],
                                "address": r.address, "lat": r.latitude,
                                "lng": r.longitude, "place_id": f"osm:{r.raw.get('osm_type', '')}{r.raw.get('osm_id', '')}",
                                "types": types, "indoor": _indoor(types), "hours": _osm_hours(tags.get("opening_hours")),
                                "hours_text": tags.get("opening_hours"), "est_cost": None, "source": "nominatim",
                                "country": (r.raw.get("address") or {}).get("country_code")}
                    return None  # Nominatim answered "not found": don't fall back to a looser search
                except Exception:  # noqa: BLE001
                    _last_nominatim[0] = time.time()
            _mark_down("nominatim", 30)
        hits = [h for h in search(query, near=near, limit=5) if not country or (h.get("country") or country) == country]
        want = re.sub(r"[^a-z0-9]", "", query.split(",")[0].lower())
        named = [h for h in hits if want and want in re.sub(r"[^a-z0-9]", "", (h.get("name") or "").lower())]
        return (named or hits or [None])[0]

    return _cached(("geo", query.lower(), round(near["lat"], 1) if near else None, round(near["lng"], 1) if near else None, country),
                   run, ttl=86400)


def search(query: str, near: dict | None = None, limit: int = 5) -> list[dict]:
    """Search-as-you-type place picker (Photon, OSM data)."""
    if offline() or not query.strip():
        return []

    def run():
        params = {"q": query, "limit": limit}
        if near:
            params.update(lat=near["lat"], lon=near["lng"])
        try:
            r = httpx.get("https://photon.komoot.io/api/", params=params, headers={"User-Agent": UA}, timeout=10)
            r.raise_for_status()
        except Exception:  # noqa: BLE001
            return []
        out = []
        for f in r.json().get("features", []):
            pr = f["properties"]
            lon, lat = f["geometry"]["coordinates"]
            addr = ", ".join(x for x in [pr.get("street"), pr.get("city") or pr.get("county"), pr.get("state"), pr.get("country")] if x)
            types = [pr.get("osm_value", "")]
            out.append({"name": pr.get("name") or addr or query, "address": addr, "lat": lat, "lng": lon,
                        "place_id": f"osm:{pr.get('osm_type', '')}{pr.get('osm_id', '')}", "types": types,
                        "indoor": _indoor(types), "hours": None, "est_cost": None, "source": "photon",
                        "country": (pr.get("countrycode") or "").lower() or None})
        return out

    return _cached(("search", query.lower(), round(near["lat"], 2) if near else None, round(near["lng"], 2) if near else None, limit), run)


# ------------------------------------------------------------------ nearby places (openrouteservice POIs + osmnx hours)

def _osmnx_hours(center: dict, radius_m: int) -> dict[str, str]:
    """name -> opening_hours from OpenStreetMap via osmnx (Overpass). Skipped while Overpass is overloaded."""
    if not _service_up("overpass"):
        return {}

    def run():
        try:
            import osmnx as ox
            ox.settings.requests_timeout = 8
            ox.settings.use_cache = True
            ox.settings.log_console = False
            gdf = ox.features_from_point((center["lat"], center["lng"]), tags=OSMNX_TAGS, dist=radius_m)
            if "opening_hours" not in gdf.columns or "name" not in gdf.columns:
                return {}
            sub = gdf[gdf["opening_hours"].notna() & gdf["name"].notna()]
            return {str(n).strip().lower(): str(h) for n, h in zip(sub["name"], sub["opening_hours"])}
        except Exception:  # noqa: BLE001
            _mark_down("overpass", 600)
            return {}

    return _cached(("osmnx", round(center["lat"], 3), round(center["lng"], 3), radius_m), run)


def nearby(center: dict, categories: list[str], radius_m: int = 2000, limit: int = 20) -> list[dict]:
    """Named, worthwhile places near a point for the given interests (openrouteservice POI API)."""
    if offline() or not center or center.get("lat") is None:
        return []
    radius_m = min(radius_m, 2000)  # ORS POI buffer limit
    groups = sorted({g for c in categories for g in CATEGORIES.get(c, {}).get("groups", [])})
    allow = None
    if all(CATEGORIES.get(c, {}).get("allow") for c in categories):
        allow = set().union(*(CATEGORIES[c]["allow"] for c in categories))

    def run():
        client = _ors()
        out = []
        if client and _service_up("ors_pois"):
            try:
                feats = []
                for i in range(0, len(groups), 5):  # ORS allows at most 5 category groups per request
                    res = client.places(request="pois", geojson={"type": "Point", "coordinates": [center["lng"], center["lat"]]},
                                        buffer=radius_m, filter_category_group_ids=groups[i:i + 5], limit=200)
                    feats += res.get("features", [])
                for f in feats:
                    pr = f["properties"]
                    tags = pr.get("osm_tags") or {}
                    name = tags.get("name") or tags.get("name:en")
                    cats = [c["category_name"] for c in (pr.get("category_ids") or {}).values()]
                    if not name or set(cats) & NOT_WORTH:
                        continue
                    if allow is not None and not set(cats) & allow:
                        continue
                    lon, lat = f["geometry"]["coordinates"]
                    types = cats + [v for k, v in tags.items() if k in ("tourism", "amenity", "leisure", "historic", "shop")]
                    est = next((EST_COST[c] for c in cats if c in EST_COST), None)
                    if tags.get("fee") == "no":
                        est = 0
                    out.append({"name": name, "address": tags.get("addr:street", ""), "lat": lat, "lng": lon,
                                "place_id": f"osm:{pr.get('osm_type', '')}{pr.get('osm_id', '')}", "types": types,
                                "category": cats[0] if cats else None, "indoor": _indoor(types),
                                "hours": _osm_hours(tags.get("opening_hours")), "hours_text": tags.get("opening_hours"),
                                "wheelchair": tags.get("wheelchair"), "website": tags.get("website"),
                                "est_cost": est, "cost_is_estimate": est is not None and tags.get("fee") != "no",
                                "distance_m": round(pr.get("distance", 0)), "source": "openrouteservice"})
            except Exception:  # noqa: BLE001
                _mark_down("ors_pois", 300)
        if not out:
            out = _photon_nearby(center, categories, radius_m, limit)
        # Fill missing opening hours from osmnx where names match.
        missing = [p for p in out if not p.get("hours")]
        if missing:
            extra = _osmnx_hours(center, radius_m)
            for p in missing:
                h = extra.get(p["name"].strip().lower())
                if h:
                    p["hours"], p["hours_text"], p["hours_source"] = _osm_hours(h), h, "osmnx"
        # dedupe by name, prefer known hours, then closer
        seen, uniq = set(), []
        for p in sorted(out, key=lambda p: (p.get("hours") is None, p.get("distance_m") or km(center, p) * 1000)):
            k = p["name"].strip().lower()
            if k not in seen:
                seen.add(k)
                uniq.append(p)
        return uniq[:limit]

    return _cached(("nearby", round(center["lat"], 3), round(center["lng"], 3), tuple(sorted(categories)), radius_m, limit), run)


PHOTON_TAGS = {
    "sightseeing": [("attraction", "tourism:attraction"), ("museum", "tourism:museum"), ("monument", "historic")],
    "culture": [("museum", "tourism:museum"), ("gallery", "tourism:gallery")],
    "food": [("restaurant", "amenity:restaurant"), ("cafe", "amenity:cafe")],
    "shopping": [("mall", "shop:mall"), ("market", "amenity:marketplace")],
    "nature": [("park", "leisure:park"), ("garden", "leisure:garden")],
    "rest": [("cafe", "amenity:cafe"), ("library", "amenity:library")],
}


def _photon_nearby(center: dict, categories: list[str], radius_m: int, limit: int) -> list[dict]:
    dlat = radius_m / 111000
    dlng = radius_m / (111000 * max(0.2, math.cos(math.radians(center["lat"]))))
    bbox = f"{center['lng'] - dlng},{center['lat'] - dlat},{center['lng'] + dlng},{center['lat'] + dlat}"
    out = []
    for cat in categories:
        for word, tag in PHOTON_TAGS.get(cat, []):
            try:
                r = httpx.get("https://photon.komoot.io/api/", headers={"User-Agent": UA}, timeout=8,
                              params={"q": word, "bbox": bbox, "osm_tag": tag, "limit": 8})
                r.raise_for_status()
            except Exception:  # noqa: BLE001
                continue
            for f in r.json().get("features", []):
                pr = f["properties"]
                if not pr.get("name"):
                    continue
                lon, lat = f["geometry"]["coordinates"]
                types = [pr.get("osm_value", "")]
                out.append({"name": pr["name"], "address": pr.get("street", ""), "lat": lat, "lng": lon,
                            "place_id": f"osm:{pr.get('osm_type', '')}{pr.get('osm_id', '')}", "types": types,
                            "category": types[0], "indoor": _indoor(types), "hours": None,
                            "est_cost": EST_COST.get(types[0]), "source": "photon"})
    return out[:limit]


# ------------------------------------------------------------------ travel times and routes (openrouteservice)

def _estimate(a: dict, b: dict) -> dict:
    d = km(a, b)
    if d < 1.2:
        return {"minutes": max(1, math.ceil(d * 1.3 / 4.5 * 60)), "mode": "walk", "km": round(d, 2), "source": "estimate"}
    return {"minutes": max(5, math.ceil(d * 1.4 / 22 * 60) + 5), "mode": "drive", "km": round(d, 2), "source": "estimate"}


def _directions(a: dict, b: dict, profile: str) -> dict | None:
    """One openrouteservice directions call gives duration, distance and road geometry (cached a day)."""
    def run():
        client = _ors()
        if not client or not _service_up("ors"):
            return None
        try:
            d = client.directions([[a["lng"], a["lat"]], [b["lng"], b["lat"]]], profile=profile, format="geojson", instructions=False)
            f = d["features"][0]
            coords = f["geometry"]["coordinates"]
            step = max(1, len(coords) // 150)
            line = [[c[1], c[0]] for c in coords[::step]] + [[coords[-1][1], coords[-1][0]]]
            return {"secs": f["properties"]["summary"].get("duration", 0), "meters": f["properties"]["summary"].get("distance", 0), "line": line}
        except Exception as e:  # noqa: BLE001
            if any(x in str(e) for x in ("403", "429", "Quota", "quota")):
                _mark_down("ors", 600)
            return None

    return _cached(("dir", profile, round(a["lat"], 4), round(a["lng"], 4), round(b["lat"], 4), round(b["lng"], 4)), run, ttl=86400)


def travel(a: dict | None, b: dict | None) -> dict:
    """Door-to-door minutes: walking when close, otherwise by road (+5 min to find a cab)."""
    if not a or not b or a.get("lat") is None or b.get("lat") is None:
        return {"minutes": 0, "mode": "none", "km": 0, "source": "unknown"}
    if km(a, b) < 0.05:
        return {"minutes": 0, "mode": "here", "km": 0, "source": "same place"}
    est = _estimate(a, b)
    if offline() or km(a, b) > 600:
        return est
    walk = est["mode"] == "walk"
    d = _directions(a, b, "foot-walking" if walk else "driving-car")
    if not d:
        return est
    factor, extra = (1.0, 0) if walk else (1.4, 5)  # city traffic allowance on free-flow times; time to find a cab
    return {"minutes": max(1, math.ceil(d["secs"] / 60 * factor) + extra), "mode": est["mode"],
            "km": round(d["meters"] / 1000, 2), "source": "openrouteservice"}


def route_line(a: dict, b: dict) -> list[list[float]] | None:
    """Road geometry [[lat, lng], ...] between two points for drawing on maps."""
    if offline() or not a or not b or a.get("lat") is None or b.get("lat") is None or km(a, b) < 0.05 or km(a, b) > 400:
        return None
    d = _directions(a, b, "foot-walking" if km(a, b) < 1.2 else "driving-car")
    return d["line"] if d else None


# ------------------------------------------------------------------ alternatives for broken transport legs

def transit_options(origin: dict, dest: dict, after: datetime, offset: str, limit: int = 3) -> list[dict]:
    """Open data has no train/bus timetables, so offer the one alternative we can compute: going by road.
    Duration/distance come from openrouteservice; the fare is a clearly-labelled estimate."""
    if offline() or not origin or not dest or origin.get("lat") is None or dest.get("lat") is None:
        return []
    client = _ors()
    if not client:
        return []
    try:
        d = client.directions([[origin["lng"], origin["lat"]], [dest["lng"], dest["lat"]]], profile="driving-car",
                              format="geojson", instructions=False)
        summ = d["features"][0]["properties"]["summary"]
    except Exception:  # noqa: BLE001
        return []
    hours = summ["duration"] / 3600 * 1.25 + 0.25  # traffic + stops allowance
    dist_km = summ["distance"] / 1000
    if hours > 14:
        return []
    depart = after + timedelta(minutes=30)
    arrive = depart + timedelta(hours=hours)
    return [{"depart": depart.strftime("%Y-%m-%dT%H:%M"), "arrive": arrive.strftime("%Y-%m-%dT%H:%M"),
             "from_stop": origin.get("name"), "to_stop": dest.get("name"), "lines": ["Cab / drive by road"],
             "changes": 0, "km": round(dist_km), "est_cost": round(dist_km * 14 / 50) * 50,
             "note": f"{dist_km:.0f} km by road (openrouteservice); fare is an estimate at ~₹14/km", "source": "openrouteservice"}]


# ------------------------------------------------------------------ weather (Open-Meteo)

def rain_forecast(point: dict, day: str) -> dict:
    if offline() or not point:
        return {"available": False}

    def run():
        try:
            r = httpx.get("https://api.open-meteo.com/v1/forecast", timeout=8, params={
                "latitude": point["lat"], "longitude": point["lng"], "hourly": "precipitation_probability",
                "timezone": "auto", "start_date": day, "end_date": day})
            r.raise_for_status()
            probs = r.json()["hourly"]["precipitation_probability"]
            rainy = [h for h, p in enumerate(probs) if p is not None and p >= 60]
            return {"available": True, "max_chance": max([p for p in probs if p is not None], default=0),
                    "rainy_hours": rainy, "source": "Open-Meteo"}
        except Exception:  # noqa: BLE001
            return {"available": False}

    return _cached(("rain", round(point["lat"], 2), round(point["lng"], 2), day), run, ttl=3 * 3600)
