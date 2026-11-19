"""Login (JWT), per-user trips, and the admin activity monitor. Runs on temporary data folders."""
import time

import jwt
import pytest
from fastapi.testclient import TestClient

from app import activity, auth, main, store


@pytest.fixture()
def client(tmp_path, monkeypatch):
    trips = tmp_path / "trips"
    trips.mkdir()
    monkeypatch.setattr(store, "TRIPS_DIR", trips)
    monkeypatch.setattr(auth, "USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(auth, "SECRET_FILE", tmp_path / ".jwt_secret")
    monkeypatch.setattr(activity, "LOG_FILE", tmp_path / "activity.jsonl")
    for k in ("ADMIN_USERNAME", "ADMIN_PASSWORD", "JWT_SECRET"):
        monkeypatch.delenv(k, raising=False)
    # a trip made before logins existed
    old = store.blank_trip("Old trip", "Mysuru")
    store.save(old)
    with TestClient(main.app) as c:
        yield c


def signup(c, name, pw="secret123"):
    r = c.post("/api/auth/register", json={"username": name, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}, r.json()["user"]


def test_everything_needs_a_login(client):
    assert client.get("/api/trips").status_code == 401
    assert client.get("/api/status").status_code == 200  # the login page may check the backend
    r = client.get("/api/trips", headers={"Authorization": "Bearer nonsense"})
    assert r.status_code == 401 and "Invalid" in r.json()["detail"]


def test_first_account_is_admin_and_gets_older_trips(client):
    h, u = signup(client, "asha")
    assert u["role"] == "admin"
    assert [t["title"] for t in client.get("/api/trips", headers=h).json()["trips"]] == ["Old trip"]
    _, u2 = signup(client, "ravi")
    assert u2["role"] == "user"


def test_each_user_sees_only_their_own_trips(client):
    ha, _ = signup(client, "asha")
    hr, _ = signup(client, "ravi")
    t = client.post("/api/trips", json={"title": "Ravi's Goa trip", "destination": ""}, headers=hr).json()
    assert [x["title"] for x in client.get("/api/trips", headers=hr).json()["trips"]] == ["Ravi's Goa trip"]
    assert "Ravi's Goa trip" not in [x["title"] for x in client.get("/api/trips", headers=ha).json()["trips"]]
    # another user can't open, change or delete it
    hs, _ = signup(client, "sam")
    assert client.get(f"/api/trips/{t['id']}", headers=hs).status_code == 404
    assert client.delete(f"/api/trips/{t['id']}", headers=hs).status_code == 404
    assert client.get(f"/api/trips/{t['id']}", headers=hr).status_code == 200


def test_login_wrong_password_and_tokens(client):
    signup(client, "asha", "rightpass")
    assert client.post("/api/auth/login", json={"username": "asha", "password": "nope"}).status_code == 401
    r = client.post("/api/auth/login", json={"username": "ASHA", "password": "rightpass"})
    assert r.status_code == 200
    token = r.json()["token"]
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()["user"]["username"] == "asha"
    # expired and tampered tokens are refused
    expired = jwt.encode({"sub": r.json()["user"]["id"], "exp": int(time.time()) - 5}, auth._secret(), algorithm="HS256")
    assert "expired" in client.get("/api/trips", headers={"Authorization": f"Bearer {expired}"}).json()["detail"]
    forged = jwt.encode({"sub": r.json()["user"]["id"], "exp": int(time.time()) + 60}, "wrong-key", algorithm="HS256")
    assert client.get("/api/trips", headers={"Authorization": f"Bearer {forged}"}).status_code == 401
    # passwords are never stored in plain text
    assert "rightpass" not in auth.USERS_FILE.read_text()


def test_duplicate_and_weak_signups_rejected(client):
    signup(client, "asha")
    assert client.post("/api/auth/register", json={"username": "Asha", "password": "secret123"}).status_code == 400
    assert client.post("/api/auth/register", json={"username": "bo", "password": "secret123"}).status_code == 400
    assert client.post("/api/auth/register", json={"username": "bob", "password": "123"}).status_code == 400


def test_admin_monitor(client):
    ha, _ = signup(client, "asha")
    hr, _ = signup(client, "ravi")
    client.get("/api/trips", headers=hr)
    client.get("/api/trips/trip_deadbeef", headers=hr)  # a 404 the admin should see
    client.post("/api/auth/login", json={"username": "ravi", "password": "bad"})
    assert client.get("/api/admin/activity", headers=hr).status_code == 403  # not for normal users
    rows = client.get("/api/admin/activity", headers=ha).json()["rows"]
    mine = [r for r in rows if r["user"] == "ravi"]
    assert any(r["route"] == "/api/trips/:id" and r["status"] == 404 and r["error"] == "Trip not found." for r in mine)
    assert any(r["route"] == "/api/auth/login" and r["status"] == 401 for r in mine)  # failed login is attributed
    assert all("ms" in r and "area" in r for r in rows)
    errs = client.get("/api/admin/activity?outcome=client_error&user=ravi", headers=ha).json()["rows"]
    assert errs and all(400 <= r["status"] < 500 for r in errs)
    st = client.get("/api/admin/stats", headers=ha).json()
    assert st["requests"] >= 5 and st["failed_logins"] == 1 and st["endpoints"]
    users = {u["username"]: u for u in client.get("/api/admin/users", headers=ha).json()["users"]}
    assert users["ravi"]["requests"] >= 3 and users["ravi"]["errors"] >= 2 and "password" not in users["ravi"]


def test_outside_calls_are_counted(client):
    ha, _ = signup(client, "asha")
    ctx = {"user": None}
    tok = auth.REQUEST.set(ctx)
    auth.track("ai", "groq", 820.4)
    auth.track("ai", "groq", 100, ok=False)
    auth.REQUEST.reset(tok)
    assert ctx["calls"]["ai:groq"] == {"n": 2, "ms": 920, "errors": 1}


def test_map_link_works_with_token_in_url(client):
    h, _ = signup(client, "asha")
    t = client.post("/api/trips", json={"title": "x", "destination": ""}, headers=h).json()
    token = h["Authorization"][7:]
    assert client.get(f"/api/trips/{t['id']}/map.html").status_code == 401
    assert client.get(f"/api/trips/{t['id']}/map.html?token={token}").status_code == 200
