"""Conversational assistant. It can read the trip, report changes, search places and add items.
It cannot approve plans or mark bookings confirmed: those stay with the traveler in the UI."""
from __future__ import annotations

import json

from . import engine, extract, maps, planner, store
from .llm import LLMUnavailable, chat
from .timeutil import parse

SYSTEM = """You are Disruption Copilot, a calm, practical travel assistant inside a trip-planning app.
Use the tools to read the trip and act. Rules:
- Facts (times, prices, opening hours, travel times, availability) come ONLY from tool results. Never invent them.
- When the traveler says something changed (delay, cancellation, rain, closure, being late, a new commitment), call report_change
  with their words. Then summarise the 2-3 plans briefly and tell them to compare and press Approve in the Recovery panel.
- You cannot approve plans or confirm bookings. Booking changes are done by the traveler; the app tracks them.
- To build or extend a trip from a description, call add_items_from_text. For one item, call add_item.
- Keep answers short (under 120 words), friendly, and use 24-hour times.
- Plain text only: short sentences or "- " bullet lines. No tables, no headings, no bold."""

TOOLS = [
    {"type": "function", "function": {"name": "get_trip", "description": "The current itinerary, open disruption with its plans, and open booking tasks.",
                                      "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "report_change", "description": "Report something that changed (delay, cancellation, rain, closure, personal change). Analyses impact and prepares 2-3 validated recovery plans.",
                                      "parameters": {"type": "object", "properties": {"message": {"type": "string"},
                                                                                       "as_of": {"type": "string", "description": "YYYY-MM-DDTHH:MM, only if the traveler said when"}},
                                                     "required": ["message"]}}},
    {"type": "function", "function": {"name": "find_places", "description": "Search real places: by text query, or nearby a trip item by category.",
                                      "parameters": {"type": "object", "properties": {
                                          "query": {"type": "string"}, "near_item_id": {"type": "string"},
                                          "category": {"type": "string", "enum": list(maps.CATEGORIES)},
                                          "indoor_only": {"type": "boolean"}}}}},
    {"type": "function", "function": {"name": "add_item", "description": "Add one item to the itinerary.",
                                      "parameters": {"type": "object", "properties": {
                                          "type": {"type": "string", "enum": ["transport", "stay", "activity", "meal", "other"]},
                                          "title": {"type": "string"}, "start": {"type": "string"}, "end": {"type": "string"},
                                          "location": {"type": "string", "description": "place name and city"},
                                          "origin": {"type": "string", "description": "departure place (transport only)"},
                                          "fixed": {"type": "boolean"}, "priority": {"type": "string", "enum": ["must", "high", "normal", "optional"]}},
                                                     "required": ["type", "title", "start"]}}},
    {"type": "function", "function": {"name": "add_items_from_text", "description": "Add several items described in free text (e.g. a pasted itinerary or 'arrive by train 10am, hotel, palace at 2').",
                                      "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}},
    {"type": "function", "function": {"name": "set_preferences", "description": "Update traveler preferences.",
                                      "parameters": {"type": "object", "properties": {
                                          "interests": {"type": "array", "items": {"type": "string", "enum": list(planner.INTEREST_TO_CATEGORY)}},
                                          "extra_budget": {"type": "number"}, "pace": {"type": "string", "enum": ["relaxed", "moderate", "packed"]},
                                          "group": {"type": "string", "enum": ["solo", "couple", "friends", "family"]},
                                          "travelers": {"type": "integer"}, "accessibility": {"type": "boolean"}}}}},
]


def _open_disruption(trip):
    return next((d for d in reversed(trip["disruptions"]) if d["status"] in ("analyzed", "planned", "no_plan")), None)


def _trip_summary(trip):
    d = _open_disruption(trip)
    return {"title": trip["title"], "destination": trip["destination"], "preferences": trip["preferences"],
            "items": [{**c, "booking": next(i["booking"]["status"] for i in trip["items"] if i["id"] == c["id"])}
                      for c in planner.compact_items(trip)],
            "open_change": {"summary": d["summary"], "as_of": d["as_of"],
                            "impact": {k: v["status"] for k, v in d["impact"]["results"].items()},
                            "plans": [{"id": p["id"], "name": p["name"], "summary": p["summary"], "extra_cost": p["extra_cost"],
                                       "removed": [r["title"] for r in p["removed"]], "tradeoffs": p["tradeoffs"]} for p in d["plans"]]} if d else None,
            "open_tasks": [{"title": a["title"], "status": a["status"]} for a in trip["actions"] if a["status"] in ("needs_attention", "pending")]}


def _run(trip: dict, name: str, args: dict):
    if name == "get_trip":
        return _trip_summary(trip)
    if name == "report_change":
        d = planner.analyze(trip, args["message"], args.get("as_of"))
        if not d.get("questions") or d["changes"] or d.get("rain") or d.get("busy"):
            planner.make_plans(trip, d)
        return {"understood": d["summary"], "as_of": d["as_of"], "questions": d["questions"],
                "impact": {k: f"{v['status']}: {v['reason']}" for k, v in d["impact"]["results"].items()},
                "plans": [{"name": p["name"], "summary": p["summary"], "extra_cost": p["extra_cost"], "day_ends": p["day_ends"],
                           "removed": [r["title"] for r in p["removed"]]} for p in d["plans"]],
                "note": "Plans are shown in the Recovery panel; the traveler must approve one there."}
    if name == "find_places":
        center = None
        if args.get("near_item_id"):
            it = next((i for i in trip["items"] if i["id"] == args["near_item_id"]), None)
            center = (it or {}).get("location")
        center = center if center and center.get("lat") is not None else trip.get("center")
        if args.get("query"):
            res = maps.search(args["query"], near=center, limit=6)
        elif center:
            cats = [args.get("category") or "sightseeing"]
            res = maps.nearby(center, cats, limit=8)
        else:
            res = []
        if args.get("indoor_only"):
            res = [r for r in res if r.get("indoor")]
        return [{"name": r["name"], "address": r.get("address"), "indoor": r.get("indoor"), "rating": r.get("rating"),
                 "hours_known": bool(r.get("hours")), "source": r.get("source")} for r in res[:8]]
    if name == "add_item":
        g1 = maps.geocode(args["location"], near=trip.get("center")) if args.get("location") else None
        g2 = maps.geocode(args["origin"], near=trip.get("center")) if args.get("origin") else None
        loc, org = ([g1] if g1 else []), ([g2] if g2 else [])
        it = engine.normalize_item({"type": args["type"], "title": args["title"], "start": args["start"], "end": args.get("end"),
                                    "location": loc[0] if loc else ({"name": args["location"], "lat": None, "lng": None} if args.get("location") else None),
                                    "origin": org[0] if org else None, "fixed": args.get("fixed"),
                                    "priority": args.get("priority") or "normal", "source": "assistant"})
        parse(it["start"])  # validates format
        trip["items"].append(it)
        trip["items"].sort(key=lambda i: i["start"])
        store.log(trip, f"Assistant added '{it['title']}'.", "edit")
        return {"added": it["title"], "start": it["start"], "located": bool(loc)}
    if name == "add_items_from_text":
        data, provider = extract.extract("text", args["text"])
        new = extract.to_trip(data, "assistant")
        if not trip.get("center") and new.get("center"):
            trip["center"] = new["center"]
        if not trip.get("destination"):
            trip["destination"] = new.get("destination", "")
        trip["items"].extend(new["items"])
        trip["items"].sort(key=lambda i: i["start"])
        store.log(trip, f"Assistant added {len(new['items'])} items from a description.", "edit")
        return {"added": [i["title"] for i in new["items"]]}
    if name == "set_preferences":
        trip["preferences"].update({k: v for k, v in args.items() if v is not None})
        return {"preferences": trip["preferences"]}
    return {"error": f"Unknown tool {name}"}


def reply(trip: dict, history: list[dict], message: str) -> dict:
    msgs = [{"role": "system", "content": SYSTEM}] + [m for m in history[-10:] if m.get("role") in ("user", "assistant")] + \
        [{"role": "user", "content": message}]
    used = []
    try:
        for _ in range(6):
            msg, provider = chat(msgs, TOOLS)
            calls = msg.get("tool_calls") or []
            if not calls:
                return {"reply": (msg.get("content") or "").strip() or "Done.", "provider": provider, "tools": used}
            msgs.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
            for c in calls:
                try:
                    args = json.loads(c["function"].get("arguments") or "{}")
                    result = _run(trip, c["function"]["name"], args)
                except Exception as e:  # noqa: BLE001 - report tool errors back to the model
                    result = {"error": str(e)}
                used.append(c["function"]["name"])
                msgs.append({"role": "tool", "tool_call_id": c["id"], "name": c["function"]["name"],
                             "content": json.dumps(result, default=str)[:12000]})
        return {"reply": "I did several steps; please check the panels for the result.", "provider": provider, "tools": used}
    except LLMUnavailable:
        return {"reply": "The AI assistant is unavailable right now. You can still add items and report changes with the forms.",
                "provider": None, "tools": used}
