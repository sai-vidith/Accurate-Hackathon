"""Plan a trip from a rough idea ("Kerala in December, family of 5, cool weather, some trekking").

Most people don't have an itinerary yet, only an idea. Two steps:
  1. Research: Groq (gpt-oss) with its built-in browser search looks up what's current: places worth the trip,
     opening days, where to stay, how to get there and rough prices, with the pages it used.
  2. Draft: the AI turns that research into a day-by-day plan in the same format an uploaded itinerary produces,
     so the rest of the app (map, timing checks, recovery plans) works on it unchanged.
Nothing in a draft is booked: every stay and journey becomes a "book this" task, and the timing engine still checks
the plan like any other (AI suggests, code decides). If web search isn't available, the draft uses the AI's general
knowledge and says so.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

from . import llm, store
from .config import env

SEARCH_MODEL = "openai/gpt-oss-120b"   # Groq's browser_search works with the gpt-oss models

RESEARCH = """You are a careful Indian travel researcher. The traveller gave only a rough idea of a trip.
Use web search to find CURRENT, specific, real information. TODAY is {today}.
Work out sensible answers for anything they didn't say (dates, group size, budget) and say what you assumed.
If places they name are far apart (e.g. in different states), say so plainly and suggest how to fit them in or what to drop.
Return ONLY a JSON object:
{{"title": short trip name, "destination": main town/city, "region": "state, country", "country_code": "in",
 "start_date": "YYYY-MM-DD", "days": int, "travelers": int, "group": "solo"|"couple"|"family"|"friends",
 "assumptions": [short sentences, e.g. "No dates given, so this plans 3 days from 20 Dec"],
 "places": [{{"name": exact place name, "town": town, "why": one line, "best_time": e.g. "early morning",
             "hours": opening hours if found, "closed_on": weekday it's closed, if any, "minutes": typical visit length,
             "indoor": true|false, "fits": which part of the request it answers (e.g. "trekking", "cool weather")}}],
 "stays": [{{"name": real hotel or homestay, "town": town, "price": approx price per night in INR as text,
            "why": one line, "url": page where you found it}}],
 "getting_there": [{{"mode": "train"|"flight"|"bus"|"cab", "from": place, "to": place, "option": train name/number,
                    airline or operator, "duration": text, "price": approx INR as text, "url": source page}}],
 "tips": [up to 5 short, specific tips: weather that month, permits, closures, what to book early],
 "sources": [{{"title": page title, "url": url}}]}}
Prefer official and well-known sources. Never invent a booking reference."""

DRAFT = """You turn travel research into a realistic day-by-day itinerary. TODAY is {today}.
Rules: start each day around 08:00-09:00, end by 21:00; allow real travel time between places (hill roads are slow:
about 30 km/h); one main sight per 2-3 hours; include breakfast, lunch and dinner as meals; check-in 14:00, check-out 11:00;
respect closed days and opening hours from the research; keep families' days gentle; put long journeys first or last.
NOTHING is booked: provider and reference are always null, "fixed" is false for every item, and notes say what to book.
Return exactly:
{{"title": str, "destination": str, "region": "state, country", "country_code": "in", "timezone_offset": "+05:30",
 "travelers": int,
 "items": [{{"type": "transport"|"stay"|"activity"|"meal"|"other", "title": short label,
            "start": "YYYY-MM-DDTHH:MM", "end": "YYYY-MM-DDTHH:MM"|null,
            "location": specific place name WITH its town, e.g. "Mattupetty Dam, Munnar",
            "origin": departure place WITH town (transport only, else null), "area": town,
            "provider": null, "reference": null, "cost": approx INR number or null,
            "time_kind": "suggested", "fixed": false, "priority": "must"|"high"|"normal"|"optional",
            "indoor": true|false|null, "notes": what to book or know, e.g. "Book: Hotel X (about 3,500/night)"}}]}}
Use only places from the research. Every item must have a date and time."""


def _research_with_search(idea: str, today: str) -> dict | None:
    """Groq + browser search. Returns None if that isn't available."""
    if "groq" not in llm.configured():
        return None
    body = {"model": SEARCH_MODEL,
            "messages": [{"role": "system", "content": RESEARCH.format(today=today)},
                         {"role": "user", "content": f"The traveller's idea:\n{idea}"}],
            "tools": [{"type": "browser_search"}], "tool_choice": "required",
            "temperature": 0.3, "max_completion_tokens": 6000}
    try:
        msg = llm._post("groq", body, timeout=120)
        data = llm._parse_json(msg.get("content") or "")
    except Exception:  # noqa: BLE001 - search is a bonus, never a reason to fail
        return None
    found = []   # pages the search actually opened, in case the model left its own list short
    for t in msg.get("executed_tools") or []:
        for r in ((t.get("search_results") or {}).get("results") or []):
            if r.get("url"):
                found.append({"title": r.get("title") or r["url"], "url": r["url"]})
    known = {s.get("url") for s in data.get("sources") or []}
    data["sources"] = (data.get("sources") or []) + [s for s in found if s["url"] not in known]
    data["live_search"] = True
    return data


def research(idea: str, today: str) -> tuple[dict, str]:
    data = _research_with_search(idea, today)
    if data is not None:
        return data, "groq + web search"
    data, provider = llm.json_call(RESEARCH.format(today=today) + "\n(No web search is available: use what you know, "
                                   "and keep sources empty rather than guessing URLs.)", f"The traveller's idea:\n{idea}",
                                   temperature=0.3, max_tokens=5000)
    data["live_search"] = False
    data["sources"] = []
    return data, provider


def draft(idea: str) -> tuple[dict, dict, str]:
    """Returns (itinerary in extract() format, research, provider)."""
    today = date.today().isoformat()
    found, provider = research(idea, today)
    if not found.get("start_date"):
        found["start_date"] = (date.today() + timedelta(days=14)).isoformat()
    plan, _ = llm.json_call(DRAFT.format(today=today),
                            f"Traveller's idea:\n{idea}\n\nResearch (JSON):\n{json.dumps(found, ensure_ascii=False)[:14000]}",
                            temperature=0.2, max_tokens=8000)
    plan.setdefault("travelers", found.get("travelers"))
    for it in plan.get("items") or []:       # a draft never claims a booking
        it["provider"], it["reference"], it["fixed"] = None, None, False
        it["time_kind"] = "suggested"
    return plan, found, provider


def attach(trip: dict, idea: str, found: dict, provider: str) -> dict:
    """Keep the research with the trip and turn every stay and journey into a 'book this' task."""
    trip["kind"] = "manual"
    trip["plan_draft"] = {
        "idea": idea, "made_with": provider, "live_search": bool(found.get("live_search")),
        "assumptions": found.get("assumptions") or [], "stays": found.get("stays") or [],
        "getting_there": found.get("getting_there") or [], "tips": found.get("tips") or [],
        "sources": [s for s in found.get("sources") or [] if s.get("url")][:12],
    }
    if found.get("group"):
        trip["preferences"]["group"] = found["group"]
    from datetime import datetime
    now = datetime.now().isoformat(timespec="seconds")
    for it in trip["items"]:
        if it["type"] not in ("stay", "transport"):
            continue
        it["booking"]["status"] = "none"
        trip["actions"].append({
            "id": store.new_id("act"), "disruption_id": None, "item_id": it["id"], "kind": "book",
            "title": f"Book {it['title']}", "detail": it.get("notes") or "Suggested in your draft plan. Book it, then mark it confirmed with the reference.",
            "provider": None, "status": "needs_attention", "reference": None, "created_at": now,
            "history": [{"status": "needs_attention", "at": now}]})
    store.log(trip, "Drafted from your idea" + (" using live web search" if found.get("live_search") else
                                                 " (web search wasn't available, so this uses the AI's general knowledge)") + ".", "import")
    return trip
