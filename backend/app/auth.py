"""Accounts and JWT login.

Users live in backend/data/users.json. Passwords are stored as salted PBKDF2-SHA256 hashes (never in plain text).
A login returns a signed JWT (HS256) that the browser sends as `Authorization: Bearer <token>`.

Roles: "user" sees only their own trips; "admin" can also open the activity monitor.
The admin account comes from ADMIN_USERNAME / ADMIN_PASSWORD in .env; without those, the first account created
becomes the admin.
"""
from __future__ import annotations

import contextvars
import hashlib
import hmac
import json
import re
import secrets
import threading
import time
import uuid
from datetime import datetime

import jwt

from .config import DATA_DIR, env

USERS_FILE = DATA_DIR / "users.json"
SECRET_FILE = DATA_DIR / ".jwt_secret"
TOKEN_HOURS = 24
_lock = threading.Lock()

# The request being handled: who is calling, plus what happened while handling it (filled in by llm/maps).
# One dict per request; the middleware creates it and reads it back when the request finishes.
REQUEST: contextvars.ContextVar[dict | None] = contextvars.ContextVar("request_ctx", default=None)


class AuthError(Exception):
    pass


def _secret() -> str:
    s = env("JWT_SECRET")
    if s:
        return s
    from . import db
    if db.enabled():  # several servers must share one secret, so it lives in the database
        return db.set_setting_once("jwt_secret", secrets.token_hex(32))
    if not SECRET_FILE.exists():  # generated once per install, kept out of git
        SECRET_FILE.write_text(secrets.token_hex(32))
    return SECRET_FILE.read_text().strip()


# ------------------------------------------------------------------ passwords

def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000).hex()
    return f"pbkdf2_sha256${salt}${digest}"


def check_password(password: str, stored: str) -> bool:
    try:
        _, salt, _digest = stored.split("$")
    except ValueError:
        return False
    return hmac.compare_digest(hash_password(password, salt), stored)


# ------------------------------------------------------------------ user store

def _load() -> list[dict]:
    from . import db
    if db.enabled():
        return db.load_users()
    return json.loads(USERS_FILE.read_text()) if USERS_FILE.exists() else []


def _save(users: list[dict]) -> None:
    from . import db
    if db.enabled():
        db.save_users(users)
    else:
        USERS_FILE.write_text(json.dumps(users, indent=2))


def public_user(u: dict) -> dict:
    return {k: u.get(k) for k in ("id", "username", "role", "created_at", "last_login")}


def list_users() -> list[dict]:
    return [public_user(u) for u in _load()]


def get_user(user_id: str) -> dict | None:
    return next((u for u in _load() if u["id"] == user_id), None)


USERNAME_RE = re.compile(r"^[A-Za-z0-9._@-]{3,40}$")


def create_user(username: str, password: str, role: str | None = None) -> dict:
    username = (username or "").strip()
    if not USERNAME_RE.match(username):
        raise AuthError("Username must be 3–40 characters: letters, numbers, . _ @ -")
    if len(password or "") < 6:
        raise AuthError("Password must be at least 6 characters.")
    with _lock:
        users = _load()
        if any(u["username"].lower() == username.lower() for u in users):
            raise AuthError("That username is already taken.")
        if role is None:
            role = "admin" if not any(u["role"] == "admin" for u in users) and not env("ADMIN_USERNAME") else "user"
        u = {"id": f"usr_{uuid.uuid4().hex[:8]}", "username": username, "role": role,
             "password": hash_password(password), "created_at": datetime.now().isoformat(timespec="seconds"),
             "last_login": None}
        users.append(u)
        _save(users)
    if role == "admin":
        adopt_unowned_trips(u["id"])
    return u


def authenticate(username: str, password: str) -> dict:
    with _lock:
        users = _load()
        u = next((x for x in users if x["username"].lower() == (username or "").strip().lower()), None)
        if not u or not check_password(password or "", u["password"]):
            raise AuthError("Wrong username or password.")
        u["last_login"] = datetime.now().isoformat(timespec="seconds")
        _save(users)
    return u


def ensure_admin() -> None:
    """Create (or reset the password of) the admin named in .env, and hand it any trips made before logins existed."""
    name, pw = env("ADMIN_USERNAME"), env("ADMIN_PASSWORD")
    if not (name and pw):
        admin = next((u for u in _load() if u["role"] == "admin"), None)
        if admin:
            adopt_unowned_trips(admin["id"])
        return
    with _lock:
        users = _load()
        u = next((x for x in users if x["username"].lower() == name.lower()), None)
        if u is None:
            u = {"id": f"usr_{uuid.uuid4().hex[:8]}", "username": name, "role": "admin", "password": hash_password(pw),
                 "created_at": datetime.now().isoformat(timespec="seconds"), "last_login": None}
            users.append(u)
        else:
            u["role"] = "admin"
            if not check_password(pw, u["password"]):
                u["password"] = hash_password(pw)
        _save(users)
    adopt_unowned_trips(u["id"])


def adopt_unowned_trips(user_id: str) -> int:
    """Trips created before accounts existed belong to the admin, so nothing disappears."""
    from . import store
    n = 0
    for t in store.all_trips():
        if not t.get("owner"):
            t["owner"] = user_id
            store.save(t)
            n += 1
    return n


# ------------------------------------------------------------------ tokens

def issue_token(u: dict) -> str:
    now = int(time.time())
    return jwt.encode({"sub": u["id"], "name": u["username"], "role": u["role"], "iat": now,
                       "exp": now + TOKEN_HOURS * 3600}, _secret(), algorithm="HS256")


def decode_token(token: str) -> dict:
    """Returns the user for a valid token, else raises AuthError (expired, tampered, or the user was removed)."""
    try:
        claims = jwt.decode(token, _secret(), algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise AuthError("Your session expired. Please log in again.")
    except jwt.PyJWTError:
        raise AuthError("Invalid login token.")
    u = get_user(claims.get("sub", ""))
    if not u:
        raise AuthError("This account no longer exists.")
    return public_user(u)


def current_user() -> dict | None:
    ctx = REQUEST.get()
    return ctx.get("user") if ctx else None


def note(**kw) -> None:
    """Attach details to the activity record of the current request (e.g. how many items an import produced)."""
    ctx = REQUEST.get()
    if ctx is not None:
        ctx.setdefault("notes", {}).update(kw)


def track(kind: str, name: str, ms: float, ok: bool = True) -> None:
    """Count an outside call (AI provider, map service) made while handling the current request."""
    ctx = REQUEST.get()
    if ctx is None:
        return
    calls = ctx.setdefault("calls", {})
    c = calls.setdefault(f"{kind}:{name}", {"n": 0, "ms": 0, "errors": 0})
    c["n"] += 1
    c["ms"] += round(ms)
    c["errors"] += 0 if ok else 1
