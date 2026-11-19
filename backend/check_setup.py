"""Check that your keys, the AI (with web search) and the maps work, before a demo.

    python check_setup.py

It places well-known landmarks with the same map lookup the app uses for uploaded itineraries, and compares each
pin with coordinates checked by hand (Google Maps / Wikipedia, November 2026). A pin within 2 km passes.
"""
import os
import sys
import time
from pathlib import Path

os.environ.pop("COPILOT_OFFLINE", None)
sys.path.insert(0, str(Path(__file__).parent))
from app import llm, maps  # noqa: E402
from app.config import env  # noqa: E402

GREEN, RED, AMBER, END = ("\033[32m", "\033[31m", "\033[33m", "\033[0m") if sys.stdout.isatty() else ("", "", "", "")
fails = 0


def show(ok, label, detail=""):
    global fails
    mark = f"{GREEN}PASS{END}" if ok else (f"{AMBER}SKIP{END}" if ok is None else f"{RED}FAIL{END}")
    fails += ok is False
    print(f"  {mark}  {label}" + (f"  ({detail})" if detail else ""))


print("\nKeys in .env")
for k in ("GROQ_API_KEY", "GEMINI_API_KEY", "ORS_API_KEY"):
    show(bool(env(k)) or None, k, "set" if env(k) else "not set (optional)" if k != "GROQ_API_KEY" else "not set")

print("\nAI")
for p in ("groq", "gemini"):
    if not env(llm.PROVIDERS[p]["key"]):
        show(None, p, "no key")
        continue
    try:
        t = time.time()
        msg = llm._post(p, {"messages": [{"role": "user", "content": "Reply with the single word: ready"}], "max_tokens": 200})
        show(bool((msg.get("content") or "").strip()), f"{p} answers", f"{time.time() - t:.1f}s")
    except Exception as e:  # noqa: BLE001
        show(False, f"{p} answers", str(e)[:120])
if env("GROQ_API_KEY"):
    try:
        t = time.time()
        msg = llm._post("groq", {"model": "openai/gpt-oss-120b", "tools": [{"type": "browser_search"}], "tool_choice": "required",
                                 "messages": [{"role": "user", "content": "Search the web: what are the visiting hours of Mysore Palace? One line."}],
                                 "max_completion_tokens": 1500}, timeout=120)
        used = bool(msg.get("executed_tools"))
        show(used and bool(msg.get("content")), "groq web search (used by Plan from an idea)",
             f"{time.time() - t:.1f}s: {(msg.get('content') or '').strip()[:80]}")
    except Exception as e:  # noqa: BLE001
        show(False, "groq web search", f"{str(e)[:120]}. Plan from an idea will still work, without live search")

print("\nMaps: placing landmarks the way an uploaded itinerary does")
CHECKS = [("Mysore Palace, Mysuru", 12.3039, 76.6544), ("Hubballi Junction railway station, Hubballi", 15.3496, 75.1505),
          ("Vibhuti Falls, Yana", 14.5981, 74.5512), ("Om Beach, Gokarna", 14.5196, 74.3238),
          ("Murudeshwar Temple, Murudeshwar", 14.0941, 74.4848), ("Virupaksha Temple, Hampi", 15.3352, 76.4587),
          ("Basilica of Bom Jesus, Old Goa", 15.5009, 73.9116)]
for q, lat, lng in CHECKS:
    try:
        g = maps.geocode(q, country="in")
    except Exception as e:  # noqa: BLE001
        g, err = None, str(e)[:80]
    if not g:
        show(False, q, "not found (is the internet on? OpenStreetMap allows about one lookup per second)")
        continue
    off = maps.km(g, {"lat": lat, "lng": lng})
    show(off <= 2, q, f"{off:.1f} km from the checked position, via {g.get('source')}")

print("\nMaps: travel time and road route")
a, b = {"lat": 12.3163, "lng": 76.6454}, {"lat": 12.3039, "lng": 76.6544}   # Mysuru Junction -> Mysore Palace
tr = maps.travel(a, b)
show(tr.get("source") not in (None, "estimate") or None, "travel time", f"{tr.get('minutes')} min via {tr.get('source')}"
     + ("" if env("ORS_API_KEY") else "; add ORS_API_KEY for real road times"))
line = maps.route_line(a, b)
show(bool(line) or None, "road route for the map", f"{len(line)} points" if line else "straight lines will be drawn instead")

print("\n" + (f"{GREEN}All good.{END}" if not fails else f"{RED}{fails} check(s) failed.{END} See the notes above.") + "\n")
sys.exit(1 if fails else 0)
