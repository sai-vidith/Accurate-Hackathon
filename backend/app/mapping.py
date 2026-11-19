"""Map data: road routes between stops (openrouteservice) and a shareable folium map."""
from __future__ import annotations

import html

import folium

from . import maps
from .timeutil import hm, parse

COLORS = {"new": "#7c3aed", "moved": "#0284c7", "updated": "#ea580c", "kept": "#0f172a", "done": "#94a3b8",
          "affected": "#e11d48", "at_risk": "#d97706", "shifted": "#0284c7", "default": "#0f172a"}


def stops(trip: dict, plan_id: str | None = None) -> tuple[list[dict], dict | None]:
    """Ordered stops for the itinerary, or for a proposed plan."""
    plan = None
    if plan_id:
        for d in trip["disruptions"]:
            plan = next((p for p in d.get("plans", []) if p["id"] == plan_id), plan)
    if plan:
        rows = [r for r in plan["schedule"] if (r.get("location") or {}).get("lat") is not None]
        return [{"title": r["title"], "time": hm(parse(r["start"])), "lat": r["location"]["lat"], "lng": r["location"]["lng"],
                 "tag": r["tag"]} for r in rows], plan
    items = [i for i in trip["items"] if i.get("status") != "cancelled"]
    out = []
    for i in items:
        if i["type"] == "transport" and (i.get("origin") or {}).get("lat") is not None and not out:
            o = i["origin"]
            out.append({"title": f"Depart: {o['name']}", "time": hm(parse(i["start"])), "lat": o["lat"], "lng": o["lng"], "tag": "kept"})
        loc = i.get("location") or {}
        if loc.get("lat") is not None:
            out.append({"title": i["title"], "time": hm(parse(i["start"])), "lat": loc["lat"], "lng": loc["lng"], "tag": "kept"})
    return out, None


def segments(pts: list[dict]) -> list[dict]:
    """Road geometry for each leg (straight line when no route is available or the leg is very long)."""
    segs = []
    for a, b in zip(pts, pts[1:]):
        line = maps.route_line(a, b)
        segs.append({"from": a["title"], "to": b["title"], "road": line is not None,
                     "points": line or [[a["lat"], a["lng"]], [b["lat"], b["lng"]]]})
    return segs


def folium_map(trip: dict, plan_id: str | None = None) -> str:
    pts, plan = stops(trip, plan_id)
    center = [pts[0]["lat"], pts[0]["lng"]] if pts else ([trip["center"]["lat"], trip["center"]["lng"]] if trip.get("center") else [20.6, 78.9])
    m = folium.Map(location=center, zoom_start=13, tiles="OpenStreetMap", control_scale=True)
    color = "#7c3aed" if plan else "#0f172a"
    for seg in segments(pts):
        folium.PolyLine(seg["points"], color=color, weight=4, opacity=0.75,
                        dash_array=None if seg["road"] else "6 8", tooltip=f"{seg['from']} → {seg['to']}").add_to(m)
    for n, p in enumerate(pts, 1):
        c = COLORS.get(p["tag"], COLORS["default"])
        folium.Marker(
            [p["lat"], p["lng"]],
            tooltip=f"{p['time']} · {html.escape(p['title'])}",
            icon=folium.DivIcon(html=f'<div style="width:28px;height:28px;border-radius:50%;background:{c};color:#fff;'
                                     f'font:600 12px sans-serif;display:grid;place-items:center;border:2px solid #fff;'
                                     f'box-shadow:0 1px 4px rgba(0,0,0,.4)">{n}</div>', icon_size=(28, 28), icon_anchor=(14, 14)),
        ).add_to(m)
    if plan:
        for d in trip["disruptions"]:
            if any(p["id"] == plan_id for p in d.get("plans", [])):
                for c in (d.get("options") or {}).get("candidates", []):
                    folium.CircleMarker([c["lat"], c["lng"]], radius=5, color="#7c3aed", fill=True, fill_opacity=0.5,
                                        tooltip=html.escape(c["name"])).add_to(m)
    if len(pts) > 1:
        m.fit_bounds([[p["lat"], p["lng"]] for p in pts], padding=(30, 30))
    title = f"{trip['title']}" + (f" · plan: {plan['name']}" if plan else "")
    legend = (f'<div style="position:fixed;top:12px;left:50px;z-index:9999;background:#fff;padding:8px 12px;border-radius:10px;'
              f'box-shadow:0 1px 6px rgba(0,0,0,.2);font:13px sans-serif"><b>{html.escape(title)}</b><br>'
              f'<span style="color:#475569">Road routes: openrouteservice · Map data © OpenStreetMap contributors</span></div>')
    m.get_root().html.add_child(folium.Element(legend))
    return m.get_root().render()
