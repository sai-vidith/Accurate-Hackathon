"""The Postgres store behaves like the file store. Runs only when TEST_DATABASE_URL points at a throwaway database."""
import os

import pytest

URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="set TEST_DATABASE_URL to run the Postgres tests")


@pytest.fixture()
def pg(monkeypatch):
    from app import db
    monkeypatch.setattr(db, "URL", URL)
    monkeypatch.setattr(db, "_pool", None)
    db.q("drop table if exists trips, users, activity, settings")
    db._pool = None
    db.pool()
    yield db
    db.close()


def test_trips_users_activity_and_secret_live_in_postgres(pg):
    from app import activity, auth, store
    u = auth.create_user("asha", "secret12")
    assert auth.authenticate("asha", "secret12")["username"] == "asha"
    assert [x["username"] for x in auth.list_users()] == ["asha"]
    auth.REQUEST.set({"user": auth.public_user(u)})
    t = store.blank_trip("Coorg weekend", "Madikeri")
    store.save(t)
    t["title"] = "Coorg long weekend"
    store.save(t)                                   # an update, not a second row
    assert store.load(t["id"])["title"] == "Coorg long weekend"
    assert [s["title"] for s in store.list_trips(u["id"])] == ["Coorg long weekend"]
    assert store.list_trips("someone_else") == []
    activity.record({"at": "2026-11-19T10:00:00", "path": "/api/trips", "status": 200})
    assert activity.read(10)[-1]["path"] == "/api/trips"
    s1, s2 = auth._secret(), auth._secret()
    assert s1 == s2 and len(s1) == 64               # one shared login secret
    assert store.delete(t["id"]) and store.load(t["id"]) is None
