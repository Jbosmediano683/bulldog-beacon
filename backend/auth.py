"""Mock Yale NetID sign-in.

The real thing would be Yale CAS (secure.its.yale.edu/cas), which needs an app
registration with Yale ITS. This module copies the shape of that flow so CAS can
replace it later: a NetID identifies the person, and the app keeps its own
session cookie. Passwords are PBKDF2-SHA256 hashed; session tokens are stored
only as SHA-256 hashes.
"""

import hashlib
import hmac
import re
import secrets
import sqlite3
from datetime import timedelta
from typing import Any

from db import iso, now_iso, now_utc, one

NETID_RE = re.compile(r"^[a-z]{2,4}[0-9]{1,6}$")  # Yale NetIDs look like initials + digits
ITERATIONS = 310_000
SESSION_DAYS = 7
COOKIE = "beacon_session"


def valid_netid(netid: str) -> bool:
    return bool(NETID_RE.match(netid))


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), ITERATIONS).hex()
    return f"pbkdf2_sha256${ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt, digest = stored.split("$")
    except ValueError:
        return False
    check = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iters)).hex()
    return hmac.compare_digest(check, digest)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(conn: sqlite3.Connection, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    conn.execute(
        "INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?,?,?,?)",
        (_token_hash(token), user_id, now_iso(), iso(now_utc() + timedelta(days=SESSION_DAYS))),
    )
    conn.commit()
    return token


def end_session(conn: sqlite3.Connection, token: str) -> None:
    conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))
    conn.commit()


def user_for_token(conn: sqlite3.Connection, token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    return one(
        conn,
        "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id "
        "WHERE s.token_hash = ? AND s.expires_at > ?",
        (_token_hash(token), now_iso()),
    )


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    """The fields the browser may see (never the password hash)."""
    import json
    return {
        "id": user["id"], "netid": user["netid"], "name": user["name"],
        "affiliation": user["affiliation"], "unit": user["unit"], "role": user["role"],
        "contacts": json.loads(user["contacts_json"] or "[]"),
        "medical_note": user["medical_note"], "demo": bool(user["demo"]),
    }
