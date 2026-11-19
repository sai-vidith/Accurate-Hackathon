"""Plan from an idea: research (Groq web search) -> draft -> a normal trip with 'book this' tasks.
The AI is replaced by recorded replies, so this runs offline."""
import json

from app import extract, ideas, llm

RESEARCH = {"title": "Kerala hills with the family", "destination": "Munnar", "region": "Kerala, India", "country_code": "in",
            "start_date": "2026-12-20", "days": 2, "travelers": 4, "group": "family",
            "assumptions": ["Coorg is in Karnataka, about 10 hours away, so this plan stays in Kerala"],
            "places": [{"name": "Eravikulam National Park", "town": "Munnar"}],
            "stays": [{"name": "Misty Hills Homestay", "town": "Munnar", "price": "about 3,500 a night", "url": "https://example.org/stay"}],
            "getting_there": [{"mode": "cab", "from": "Thiruvananthapuram", "to": "Munnar", "duration": "7 h"}],
            "tips": ["Eravikulam is closed in February and March for calving."], "sources": [{"title": "Kerala Tourism", "url": "https://www.keralatourism.org"}]}
PLAN = {"title": "Kerala hills with the family", "destination": "Munnar", "region": "Kerala, India", "country_code": "in",
        "timezone_offset": "+05:30", "travelers": 4, "items": [
            {"type": "transport", "title": "Cab Thiruvananthapuram to Munnar", "start": "2026-12-20T07:00", "end": "2026-12-20T14:00",
             "location": "Munnar", "origin": "Thiruvananthapuram", "area": "Munnar", "provider": "KTDC", "reference": "X1", "fixed": True},
            {"type": "stay", "title": "Check in at Misty Hills Homestay", "start": "2026-12-20T14:30", "end": None,
             "location": "Misty Hills Homestay, Munnar", "area": "Munnar", "notes": "Book: about 3,500 a night"},
            {"type": "activity", "title": "Eravikulam National Park", "start": "2026-12-21T08:30", "end": "2026-12-21T11:30",
             "location": "Eravikulam National Park, Munnar", "area": "Munnar", "priority": "must"}]}


def fake_post(provider, body, timeout=60):
    assert body["model"] == "openai/gpt-oss-120b" and body["tools"] == [{"type": "browser_search"}]
    return {"content": json.dumps(RESEARCH), "executed_tools": [
        {"search_results": {"results": [{"title": "Munnar travel guide", "url": "https://example.org/munnar"}]}}]}


def test_vague_idea_becomes_a_checked_trip_with_booking_tasks(monkeypatch):
    monkeypatch.setattr(llm, "configured", lambda vision=False: ["groq"])
    monkeypatch.setattr(llm, "_post", fake_post)
    monkeypatch.setattr(llm, "json_call", lambda *a, **k: (json.loads(json.dumps(PLAN)), "groq"))
    plan, found, provider = ideas.draft("kerala, cool weather, trekking, family of 4, december")
    assert provider == "groq + web search" and found["live_search"]
    assert {s["url"] for s in found["sources"]} == {"https://www.keralatourism.org", "https://example.org/munnar"}
    assert all(i["provider"] is None and i["reference"] is None and i["fixed"] is False for i in plan["items"])  # nothing claimed as booked
    trip = ideas.attach(extract.to_trip(plan, "test"), "kerala idea", found, provider)
    assert len(trip["items"]) == 3 and all(i["booking"]["status"] == "none" for i in trip["items"])
    booking = [a for a in trip["actions"] if a["kind"] == "book"]
    assert len(booking) == 2                       # the cab and the homestay, not the park
    assert trip["plan_draft"]["assumptions"] and trip["plan_draft"]["live_search"] is True


def test_without_web_search_it_says_so(monkeypatch):
    monkeypatch.setattr(llm, "configured", lambda vision=False: ["gemini"])
    calls = []
    monkeypatch.setattr(llm, "json_call", lambda system, user, **k: (calls.append(system) or
                        (json.loads(json.dumps(RESEARCH)) if len(calls) == 1 else json.loads(json.dumps(PLAN))), "gemini"))
    plan, found, provider = ideas.draft("goa with friends")
    assert provider == "gemini" and found["live_search"] is False and found["sources"] == []
    assert "No web search is available" in calls[0]
