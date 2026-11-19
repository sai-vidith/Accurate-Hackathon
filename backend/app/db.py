"""Optional Postgres storage (for example a free Neon database).

Set DATABASE_URL and trips, accounts, the activity log and the login secret are kept in Postgres. Leave it unset
and they stay in JSON files under backend/data exactly as before, so local development and the tests need nothing.

Each trip and each account is stored whole, as a JSON document (JSONB), the same shape the app already uses: the
timing engine and planner don't change, and moving between files and a database is a copy, not a migration.
"""
from __future__ import annotations

import json
import threading

from .config import env

URL = env("DATABASE_URL")
_pool = None
_lock = threading.Lock()
_writes = [0]

SCHEMA = """
create table if not exists trips (
    id text primary key, owner text, data jsonb not null, updated_at timestamptz not null default now());
create index if not exists trips_owner on trips (owner, updated_at desc);
create table if not exists users (id text primary key, username text unique not null, data jsonb not null);
create table if not exists activity (id bigserial primary key, at timestamptz not null default now(), data jsonb not null);
create table if not exists settings (key text primary key, value text not null);
"""


def enabled() -> bool:
    return bool(URL)


def pool():
    global _pool
    if _pool is None:
        with _lock:
            if _pool is None:
                from psycopg_pool import ConnectionPool
                # Neon and Render close idle connections: check each one before handing it out.
                _pool = ConnectionPool(URL, min_size=1, max_size=5, open=True, check=ConnectionPool.check_connection,
                                       kwargs={"autocommit": True})
                with _pool.connection() as c:
                    c.execute(SCHEMA)
                import atexit
                atexit.register(close)
    return _pool


def close() -> None:
    global _pool
    if _pool is not None:
        _pool.close(timeout=2)
        _pool = None


def q(sql: str, args=(), one=False):
    with pool().connection() as c:
        cur = c.execute(sql, args)
        if cur.description is None:
            return None
        return cur.fetchone() if one else cur.fetchall()


def jsonb(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


# ------------------------------------------------------------------ trips

def save_trip(trip: dict) -> None:
    q("insert into trips (id, owner, data, updated_at) values (%s, %s, %s::jsonb, now()) "
      "on conflict (id) do update set owner = excluded.owner, data = excluded.data, updated_at = now()",
      (trip["id"], trip.get("owner"), jsonb(trip)))


def load_trip(trip_id: str) -> dict | None:
    row = q("select data from trips where id = %s", (trip_id,), one=True)
    return row[0] if row else None


def delete_trip(trip_id: str) -> bool:
    return bool(q("delete from trips where id = %s returning id", (trip_id,), one=True))


def trips(owner: str | None = None, all_owners: bool = True) -> list[dict]:
    """Newest first."""
    if all_owners:
        rows = q("select data from trips order by updated_at desc")
    else:
        rows = q("select data from trips where owner = %s order by updated_at desc", (owner,))
    return [r[0] for r in rows]


# ------------------------------------------------------------------ accounts

def load_users() -> list[dict]:
    return [r[0] for r in q("select data from users order by data->>'created_at', id")]


def save_users(users: list[dict]) -> None:
    """The app saves the whole account list at once; mirror it in one transaction."""
    with pool().connection() as c:
        with c.transaction():
            ids = [u["id"] for u in users]
            c.execute("delete from users where not (id = any(%s))", (ids,))
            for u in users:
                c.execute("insert into users (id, username, data) values (%s, %s, %s::jsonb) "
                          "on conflict (id) do update set username = excluded.username, data = excluded.data",
                          (u["id"], u["username"], jsonb(u)))


# ------------------------------------------------------------------ activity log

def log_activity(entry: dict, keep: int) -> None:
    q("insert into activity (data) values (%s::jsonb)", (jsonb(entry),))
    _writes[0] += 1
    if _writes[0] % 500 == 0:   # trim now and then, not on every request
        q("delete from activity where id < (select coalesce(max(id), 0) - %s from activity)", (keep,))


def read_activity(limit: int) -> list[dict]:
    rows = q("select data from activity order by id desc limit %s", (limit,))
    return [r[0] for r in reversed(rows)]


# ------------------------------------------------------------------ settings

def setting(key: str) -> str | None:
    row = q("select value from settings where key = %s", (key,), one=True)
    return row[0] if row else None


def set_setting_once(key: str, value: str) -> str:
    """Store a value unless one exists; return whichever is stored (safe if two servers start at once)."""
    q("insert into settings (key, value) values (%s, %s) on conflict (key) do nothing", (key, value))
    return setting(key)
