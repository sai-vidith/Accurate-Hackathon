from __future__ import annotations

from datetime import datetime, timedelta

import re
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import activity, assistant, auth, engine, extract, ideas, llm, mapping, maps, planner, store
from .config import env
from .timeutil import fmt, parse

@asynccontextmanager
async def lifespan(_app):
    auth.ensure_admin()  # admin from .env; trips made before logins existed go to the admin
    yield
    from . import db
    db.close()


app = FastAPI(title="Disruption Copilot API", version="2.0.0", lifespan=lifespan)
# In production the backend serves the website itself (same origin), so CORS only matters for local development
# or a frontend hosted elsewhere: list extra origins in ALLOWED_ORIGINS, comma-separated.
# Entries with a * become a pattern, e.g. "https://*--my-site.netlify.app" also allows Netlify deploy previews.
_extra = [o.strip().rstrip("/") for o in env("ALLOWED_ORIGINS").split(",") if o.strip()]
_origins = ["http://localhost:5173", "http://127.0.0.1:5173"] + [o for o in _extra if "*" not in o]
_pattern = "|".join(re.escape(o).replace(r"\*", "[A-Za-z0-9-]+") for o in _extra if "*" in o) or None
app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_origin_regex=_pattern, allow_methods=["*"], allow_headers=["*"])


# ------------------------------------------------------------------ login + activity log (every /api request)

PUBLIC_PATHS = {"/api/auth/login", "/api/auth/register", "/api/status", "/api/health"}


@app.middleware("http")
async def auth_and_activity(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/api") or request.method == "OPTIONS":
        return await call_next(request)
    t0 = time.perf_counter()
    ctx: dict = {"user": None}
    header = request.headers.get("authorization", "")
    # the full-screen map opens in a new tab, which can't send headers: it carries the token in the URL
    token = header[7:] if header.lower().startswith("bearer ") else request.query_params.get("token")
    auth_error = None
    if token:
        try:
            ctx["user"] = auth.decode_token(token)
        except auth.AuthError as e:
            auth_error = str(e)
    reset = auth.REQUEST.set(ctx)
    error_detail = None
    try:
        if path not in PUBLIC_PATHS and ctx["user"] is None:
            response = JSONResponse({"detail": auth_error or "Please log in."}, status_code=401)
        elif path.startswith("/api/admin") and ctx["user"]["role"] != "admin":
            response = JSONResponse({"detail": "Admins only."}, status_code=403)
        else:
            try:
                response = await call_next(request)
            except Exception as e:  # noqa: BLE001  — logged, then a clean 500
                error_detail = f"{type(e).__name__}: {str(e)[:200]}"
                response = JSONResponse({"detail": "Server error. It has been logged for the admin."}, status_code=500)
        if response.status_code >= 400 and error_detail is None:
            if hasattr(response, "body_iterator"):
                body = b"".join([chunk async for chunk in response.body_iterator])
            else:
                body = response.body
            try:
                import json as _json
                error_detail = str(_json.loads(body).get("detail"))[:300]
            except Exception:  # noqa: BLE001
                error_detail = body[:200].decode(errors="replace")
            response = Response(body, status_code=response.status_code, headers=dict(response.headers),
                                media_type=response.media_type)
    finally:
        auth.REQUEST.reset(reset)
    user = ctx.get("user") or {}
    if path.startswith("/api/admin") and request.method == "GET" and response.status_code < 400:
        return response  # the monitor's own refreshes would drown out real activity
    activity.record({
        "at": datetime.now().isoformat(timespec="seconds"),
        "user": user.get("username") or ctx.get("login_as"), "role": user.get("role"),
        "method": request.method, "path": path, "route": activity.route_of(path), "area": activity.area_of(path),
        "status": response.status_code, "ms": round((time.perf_counter() - t0) * 1000),
        "trip": next((p for p in path.split("/") if p.startswith("trip_")), None),
        "calls": ctx.get("calls") or {}, "notes": ctx.get("notes") or {}, "error": error_detail,
        "ip": request.client.host if request.client else None,
    })
    return response


class Credentials(BaseModel):
    username: str
    password: str


@app.post("/api/auth/register")
def register(body: Credentials):
    auth.REQUEST.get()["login_as"] = body.username.strip()[:40]
    try:
        u = auth.create_user(body.username, body.password)
    except auth.AuthError as e:
        raise HTTPException(400, str(e))
    auth.note(event="account created", role=u["role"])
    return {"token": auth.issue_token(u), "user": auth.public_user(u)}


@app.post("/api/auth/login")
def login(body: Credentials):
    auth.REQUEST.get()["login_as"] = body.username.strip()[:40]
    try:
        u = auth.authenticate(body.username, body.password)
    except auth.AuthError as e:
        raise HTTPException(401, str(e))
    return {"token": auth.issue_token(u), "user": auth.public_user(u)}


@app.get("/api/auth/me")
def me():
    return {"user": auth.current_user()}


# ------------------------------------------------------------------ admin: activity monitor

@app.get("/api/admin/activity")
def admin_activity(user: str | None = None, outcome: str | None = None, area: str | None = None,
                   q: str | None = None, limit: int = 200):
    return {"rows": activity.query(user, outcome, area, q, min(limit, 1000))}


@app.get("/api/admin/stats")
def admin_stats(hours: int = 24):
    return activity.stats(max(1, min(hours, 24 * 30)))


@app.get("/api/admin/users")
def admin_users():
    trips = store.list_trips()
    rows = activity.read()
    out = []
    for u in auth.list_users():
        mine = [r for r in rows if r.get("user") == u["username"]]
        out.append({**u, "trips": sum(1 for t in trips if t.get("owner") == u["id"]),
                    "requests": len(mine), "errors": sum(1 for r in mine if r["status"] >= 400),
                    "last_seen": mine[-1]["at"] if mine else None})
    return {"users": out}


# ------------------------------------------------------------------ helpers

def get_trip(trip_id: str) -> dict:
    """A trip the caller may use: their own (admins may open any, e.g. to follow up on an error)."""
    t = store.load(trip_id)
    me = auth.current_user()
    if not t or (me and t.get("owner") != me["id"] and me["role"] != "admin"):
        raise HTTPException(404, "Trip not found.")
    return t


def public(trip: dict) -> dict:
    """Trip + a live feasibility view, without internal plan data."""
    t = {**trip, "disruptions": []}
    for d in trip["disruptions"]:
        t["disruptions"].append({**d, "plans": [{k: v for k, v in p.items() if k != "_items"} for p in d.get("plans", [])],
                                 "excluded": [{k: v for k, v in p.items() if k != "_items"} for p in d.get("excluded", [])]})
    items = [i for i in trip["items"] if i.get("status") != "cancelled"]
    now = datetime.now().replace(second=0, microsecond=0)
    starts = sorted(parse(i["start"]) for i in items)
    done = [parse(i.get("completed_at") or i.get("end") or i["start"]) for i in items if i.get("completed")]
    if done:  # your ticked progress is "now" on the trip
        as_of = max(done)
    else:
        as_of = now if starts and starts[0] <= now <= starts[-1] + timedelta(hours=12) else (starts[0] - timedelta(minutes=1) if starts else now)
    sim = engine.simulate(items, as_of)
    fixed = {i["id"] for i in items if i["fixed"]}
    for iid, r in sim["results"].items():  # no change reported: these are planning notes, not delays
        if r["status"] == "affected" and iid in fixed:
            r["status"], r["reason"] = "conflict", "Plan conflict: " + r["reason"]
        elif r["status"] in ("shifted", "affected"):
            r["status"], r["reason"] = "tight", "Tight: your plan leaves little time to get here. " + r["reason"]
    t["view"] = {"as_of": fmt(as_of), "results": sim["results"], "position": sim["position"]}
    return t


def item_from_body(body: "ItemIn", existing: dict | None = None) -> dict:
    data = {**(existing or {}), **{k: v for k, v in body.model_dump().items() if v is not None}}
    for k in ("location", "origin"):
        if getattr(body, k) == {}:
            data[k] = None
    if data.get("end") == "":
        data["end"] = None
    parse(data["start"])
    if data.get("end"):
        parse(data["end"])
    return engine.normalize_item(data)


# ------------------------------------------------------------------ models

class TripIn(BaseModel):
    title: str = "My trip"
    destination: str = ""
    timezone_offset: str = "+05:30"


class TripPatch(BaseModel):
    kind: str | None = None
    title: str | None = None
    destination: str | None = None
    preferences: dict | None = None


class ItemIn(BaseModel):
    type: str | None = None
    title: str | None = None
    start: str | None = None
    end: str | None = None
    location: dict | None = None
    origin: dict | None = None
    fixed: bool | None = None
    priority: str | None = None
    indoor: bool | None = None
    notes: str | None = None
    booking: dict | None = None
    latest_start: str | None = None


class DoneIn(BaseModel):
    done: bool
    at: str | None = None


class DelayIn(BaseModel):
    item_id: str
    minutes: int
    mode: str = "auto"
    as_of: str | None = None


class DelaySize(BaseModel):
    minutes: int


class TextIn(BaseModel):
    text: str


class ChangeIn(BaseModel):
    message: str
    as_of: str | None = None


class ChangeEdit(BaseModel):
    as_of: str | None = None
    changes: list[dict] | None = None
    rain: dict | None = None
    clear_rain: bool = False


class ActionIn(BaseModel):
    status: str
    reference: str | None = None


class ChatIn(BaseModel):
    message: str
    history: list[dict] = []


# ------------------------------------------------------------------ status & places

@app.get("/api/status")
def status():
    return {"ai": llm.status(), "maps": maps.status()}


@app.get("/api/places/search")
def places_search(q: str, lat: float | None = None, lng: float | None = None):
    near = {"lat": lat, "lng": lng} if lat is not None and lng is not None else None
    return {"results": maps.search(q, near=near, limit=6), "source": maps.provider()}


# ------------------------------------------------------------------ trips

@app.get("/api/trips")
def trips():
    return {"trips": store.list_trips(owner=auth.current_user()["id"])}


@app.post("/api/trips")
def create_trip(body: TripIn):
    t = store.blank_trip(body.title, body.destination, body.timezone_offset)
    if body.destination:
        g = maps.geocode(body.destination)
        t["center"] = {"lat": g["lat"], "lng": g["lng"]} if g else None
    store.log(t, "Trip created.", "edit")
    return public(store.save(t))


@app.post("/api/trips/import")
async def import_file(file: UploadFile = File(...)):
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(413, "File too large (max 15 MB).")
    try:
        kind, payload = extract.file_to_input(file.filename or "upload", data, file.content_type or "")
        parsed, provider = extract.extract(kind, payload)
        trip = extract.to_trip(parsed, f"upload: {file.filename} via {provider}")
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:  # never a bare 500 for the traveler
        raise HTTPException(422, f"Something went wrong reading this file ({type(e).__name__}). Please try again; "
                                 "if it keeps failing, build the trip by hand or paste the text into 'Describe it'.")
    if not trip["items"]:
        raise HTTPException(422, "I couldn't find any dated items in that file. Try another file or build the trip by hand.")
    auth.note(file=file.filename, items=len(trip["items"]), via=provider,
              unplaced=sum(1 for i in trip["items"] if (i.get("location") or {}).get("lat") is None))
    return public(store.save(trip))


@app.post("/api/trips/import-text")
def import_text(body: TextIn):
    try:
        parsed, provider = extract.extract("text", body.text)
        trip = extract.to_trip(parsed, f"description via {provider}")
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:  # never a bare 500 for the traveler
        raise HTTPException(422, f"Something went wrong reading this text ({type(e).__name__}). Please try again.")
    if not trip["items"]:
        raise HTTPException(422, "I couldn't find any dated items. This box reads a plan you already have (dates, times, places). No plan yet? Use \"Plan from an idea\" instead.")
    return public(store.save(trip))


IDEA_LIMIT_PER_HOUR = int(env("IDEA_LIMIT_PER_HOUR", "10") or 10)
_idea_calls: dict[str, list[float]] = {}


@app.post("/api/trips/plan-idea")
def plan_from_idea(body: TextIn):
    """No itinerary yet, just an idea: research it (Groq + web search), draft a day-by-day plan, check it like any trip."""
    me = auth.current_user()["id"]
    recent = [t for t in _idea_calls.get(me, []) if t > time.time() - 3600]
    if len(recent) >= IDEA_LIMIT_PER_HOUR:   # each draft is several AI calls with web search: keep a public demo affordable
        raise HTTPException(429, f"You've drafted {IDEA_LIMIT_PER_HOUR} plans in the last hour. Please try again a little later.")
    _idea_calls[me] = recent + [time.time()]
    if len(body.text.strip()) < 8:
        raise HTTPException(422, "Tell me a little more: where you'd like to go, roughly when, and who's coming.")
    try:
        plan, found, provider = ideas.draft(body.text)
        trip = extract.to_trip(plan, f"plan drafted from your idea via {provider}")
    except (ValueError, llm.LLMUnavailable) as e:
        raise HTTPException(422, f"I couldn't draft a plan right now ({e}).")
    except Exception as e:  # never a bare 500 for the traveler
        raise HTTPException(422, f"Something went wrong drafting your plan ({type(e).__name__}). Please try again.")
    if not trip["items"]:
        raise HTTPException(422, "I couldn't draft a plan from that. Try naming a place and roughly when, e.g. 'Coorg, 3 days in December, family of 4'.")
    ideas.attach(trip, body.text, found, provider)
    auth.note(items=len(trip["items"]), live_search=trip["plan_draft"]["live_search"])
    return public(store.save(trip))


@app.get("/api/trips/{trip_id}")
def read_trip(trip_id: str):
    return public(get_trip(trip_id))


@app.patch("/api/trips/{trip_id}")
def patch_trip(trip_id: str, body: TripPatch):
    t = get_trip(trip_id)
    if body.kind is not None:
        if body.kind not in ("manual", "test"):
            raise HTTPException(400, "kind must be manual or test.")
        t["kind"] = body.kind
    if body.title is not None:
        t["title"] = body.title
    if body.destination is not None and body.destination != t.get("destination"):
        t["destination"] = body.destination
        g = maps.geocode(body.destination)
        t["center"] = {"lat": g["lat"], "lng": g["lng"]} if g else t.get("center")
    if body.preferences:
        t["preferences"].update(body.preferences)
    return public(store.save(t))


@app.delete("/api/trips/{trip_id}")
def delete_trip(trip_id: str):
    get_trip(trip_id)  # only your own
    return {"deleted": store.delete(trip_id)}


# ------------------------------------------------------------------ items

@app.post("/api/trips/{trip_id}/items")
def add_item(trip_id: str, body: ItemIn):
    t = get_trip(trip_id)
    if not body.title or not body.start:
        raise HTTPException(400, "An item needs a title and a start time.")
    try:
        it = item_from_body(body)
    except ValueError:
        raise HTTPException(400, "Times must look like 2026-11-20T10:00.")
    it["source"] = "user"
    t["items"].append(it)
    t["items"].sort(key=lambda i: i["start"])
    if not t.get("center") and (it.get("location") or {}).get("lat") is not None:
        t["center"] = {"lat": it["location"]["lat"], "lng": it["location"]["lng"]}
    store.log(t, f"Added '{it['title']}'.", "edit")
    return public(store.save(t))


@app.put("/api/trips/{trip_id}/items/{item_id}")
def edit_item(trip_id: str, item_id: str, body: ItemIn):
    t = get_trip(trip_id)
    idx = next((n for n, i in enumerate(t["items"]) if i["id"] == item_id), None)
    if idx is None:
        raise HTTPException(404, "Item not found.")
    try:
        t["items"][idx] = item_from_body(body, t["items"][idx])
    except ValueError:
        raise HTTPException(400, "Times must look like 2026-11-20T10:00.")
    t["items"].sort(key=lambda i: i["start"])
    store.log(t, f"Edited '{t['items'][idx]['title']}'.", "edit")
    return public(store.save(t))


@app.post("/api/trips/{trip_id}/items/{item_id}/done")
def mark_done(trip_id: str, item_id: str, body: DoneIn):
    """Tick a stop done (earlier stops count as done too) or untick it (later stops are unticked too)."""
    t = get_trip(trip_id)
    try:
        planner.set_done(t, item_id, body.done, body.at)
    except ValueError as e:
        raise HTTPException(400, str(e) if "found" in str(e) else "Finish time must look like 2026-11-20T13:05.")
    return public(store.save(t))


@app.delete("/api/trips/{trip_id}/items/{item_id}")
def delete_item(trip_id: str, item_id: str):
    t = get_trip(trip_id)
    t["items"] = [i for i in t["items"] if i["id"] != item_id]
    return public(store.save(t))


# ------------------------------------------------------------------ maps

@app.get("/api/trips/{trip_id}/routes")
def routes(trip_id: str, plan: str | None = None):
    """Road geometry between consecutive stops (openrouteservice directions)."""
    pts, _ = mapping.stops(get_trip(trip_id), plan)
    return {"segments": mapping.segments(pts)}


@app.get("/api/trips/{trip_id}/map.html", response_class=HTMLResponse)
def folium_map(trip_id: str, plan: str | None = None):
    """Full-screen, shareable map rendered with folium."""
    return HTMLResponse(mapping.folium_map(get_trip(trip_id), plan))


# ------------------------------------------------------------------ weather

@app.get("/api/trips/{trip_id}/weather")
def weather(trip_id: str):
    t = get_trip(trip_id)
    days = sorted({i["start"][:10] for i in t["items"] if i.get("status") != "cancelled"})
    out = []
    for day in days[:7]:
        pts = [i["location"] for i in t["items"] if i["start"].startswith(day) and (i.get("location") or {}).get("lat") is not None]
        f = maps.rain_forecast(pts[0] if pts else t.get("center"), day)
        outdoor = [i["title"] for i in t["items"] if i["start"].startswith(day) and i.get("status") != "cancelled" and engine.is_outdoor(i)
                   and f.get("available") and int(i["start"][11:13]) in f.get("rainy_hours", [])]
        out.append({"day": day, **f, "outdoor_at_risk": outdoor})
    return {"days": out}


# ------------------------------------------------------------------ disruptions

@app.post("/api/trips/{trip_id}/changes")
def report_change(trip_id: str, body: ChangeIn):
    t = get_trip(trip_id)
    if not body.message.strip():
        raise HTTPException(400, "Tell me what changed.")
    planner.analyze(t, body.message, body.as_of)
    return public(store.save(t))


@app.post("/api/trips/{trip_id}/changes/delay")
def report_delay(trip_id: str, body: DelayIn):
    """A delay at one specific item: it starts late, runs over, or (transport) arrives late."""
    t = get_trip(trip_id)
    try:
        planner.report_delay(t, body.item_id, body.minutes, body.mode, body.as_of)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return public(store.save(t))


@app.put("/api/trips/{trip_id}/changes/{dis_id}/delay")
def resize_delay(trip_id: str, dis_id: str, body: DelaySize):
    """Make a reported delay longer or shorter; everything is recalculated from the original times."""
    t = get_trip(trip_id)
    d = next((x for x in t["disruptions"] if x["id"] == dis_id), None)
    if not d or d["status"] in ("resolved", "dismissed"):
        raise HTTPException(404, "No open change to adjust.")
    try:
        planner.update_delay(t, d, body.minutes)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return public(store.save(t))


@app.put("/api/trips/{trip_id}/changes/{dis_id}")
def edit_change(trip_id: str, dis_id: str, body: ChangeEdit):
    t = get_trip(trip_id)
    d = next((x for x in t["disruptions"] if x["id"] == dis_id), None)
    if not d:
        raise HTTPException(404, "Change not found.")
    if body.as_of:
        parse(body.as_of)
        d["as_of"] = body.as_of
    if body.changes is not None:
        d["changes"] = body.changes
    if body.rain is not None:
        d["rain"] = body.rain
    if body.clear_rain:
        d["rain"] = None
    planner.recompute_impact(t, d)
    return public(store.save(t))


@app.post("/api/trips/{trip_id}/changes/{dis_id}/plans")
def plans(trip_id: str, dis_id: str):
    t = get_trip(trip_id)
    d = next((x for x in t["disruptions"] if x["id"] == dis_id), None)
    if not d:
        raise HTTPException(404, "Change not found.")
    planner.make_plans(t, d)
    auth.note(plans_offered=len(d.get("plans") or []), change=d.get("kind") or d.get("type"))
    return public(store.save(t))


@app.post("/api/trips/{trip_id}/changes/{dis_id}/plans/{plan_id}/approve")
def approve(trip_id: str, dis_id: str, plan_id: str):
    t = get_trip(trip_id)
    d = next((x for x in t["disruptions"] if x["id"] == dis_id), None)
    if not d or d["status"] != "planned":
        raise HTTPException(409, "There is no plan waiting for approval.")
    try:
        planner.approve(t, d, plan_id)
        auth.note(event="plan approved", plan=plan_id)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return public(store.save(t))


@app.post("/api/trips/{trip_id}/changes/{dis_id}/dismiss")
def dismiss(trip_id: str, dis_id: str):
    t = get_trip(trip_id)
    d = next((x for x in t["disruptions"] if x["id"] == dis_id), None)
    if d:
        d["status"] = "dismissed"
    return public(store.save(t))


# ------------------------------------------------------------------ booking tasks

@app.post("/api/trips/{trip_id}/actions/{action_id}")
def update_action(trip_id: str, action_id: str, body: ActionIn):
    t = get_trip(trip_id)
    try:
        planner.update_action(t, action_id, body.status, body.reference)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return public(store.save(t))


@app.post("/api/trips/{trip_id}/actions/{action_id}/replan")
def replan_after_failure(trip_id: str, action_id: str):
    """A booking couldn't be done: treat that item as cancelled and plan again, keeping everything else."""
    t = get_trip(trip_id)
    a = next((x for x in t["actions"] if x["id"] == action_id), None)
    if not a or not a.get("item_id"):
        raise HTTPException(404, "Task not found.")
    it = next((i for i in t["items"] if i["id"] == a["item_id"]), None)
    d = planner.structured(t, f"Couldn't complete: {a['title']}",
                           [{"item_id": it["id"], "kind": "cancel", "note": "Booking not possible"}] if it else [])
    planner.make_plans(t, d)
    auth.note(plans_offered=len(d.get("plans") or []), change=d.get("kind") or d.get("type"))
    return public(store.save(t))


# ------------------------------------------------------------------ assistant

@app.post("/api/trips/{trip_id}/chat")
def chat(trip_id: str, body: ChatIn):
    t = get_trip(trip_id)
    out = assistant.reply(t, body.history, body.message[:2000])
    auth.note(tools=out.get("tools"), provider=out.get("provider"))
    store.save(t)
    return {**out, "trip": public(t)}


# ------------------------------------------------------------------ health check and the website (production)

@app.get("/api/health")
def health():
    return {"ok": True, "ai": llm.configured(), "maps": maps.provider()}


def _site_dir():
    from pathlib import Path
    d = Path(env("FRONTEND_DIST") or Path(__file__).resolve().parents[2] / "frontend" / "dist")
    return d if (d / "index.html").exists() else None


_SITE = _site_dir()
if _SITE:  # a production build exists: serve it, and send every non-API path to the single-page app
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    app.mount("/assets", StaticFiles(directory=_SITE / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def site(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Not found.")
        f = (_SITE / path).resolve()
        if path and f.is_file() and _SITE.resolve() in f.parents:
            return FileResponse(f)
        return FileResponse(_SITE / "index.html", headers={"Cache-Control": "no-cache"})
