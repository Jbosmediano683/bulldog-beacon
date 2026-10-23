"""SQLite storage for Bulldog Beacon. One file, created and seeded on first run."""

import json
import math
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    netid TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    affiliation TEXT NOT NULL,            -- student / staff / faculty
    unit TEXT,                            -- school or department
    role TEXT NOT NULL DEFAULT 'member',  -- member / dispatcher
    password_hash TEXT NOT NULL,
    contacts_json TEXT NOT NULL DEFAULT '[]',
    medical_note TEXT NOT NULL DEFAULT '', -- opt-in, shared with responders only during an SOS
    demo INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS places (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    aliases_json TEXT NOT NULL,
    address TEXT NOT NULL,
    lat REAL NOT NULL,
    lng REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS resources (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,   -- emergency / escort / ride / mental_health / sexual_misconduct / medical / app
    phone TEXT,               -- digits as dialed, e.g. 2034324400
    phone_display TEXT,
    hours TEXT NOT NULL,
    who TEXT NOT NULL,
    description TEXT NOT NULL,
    source_url TEXT NOT NULL,
    verified_on TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS incidents (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    advice TEXT NOT NULL,
    category TEXT NOT NULL,
    severity TEXT NOT NULL,   -- info / caution / warning / urgent
    place_id INTEGER REFERENCES places(id),
    lat REAL NOT NULL,
    lng REAL NOT NULL,
    report_count INTEGER NOT NULL DEFAULT 1,
    first_reported TEXT NOT NULL,
    last_reported TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',  -- active / resolved
    demo INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    category TEXT NOT NULL,
    raw_text TEXT NOT NULL,            -- what the author typed (private: author + audit only)
    text TEXT NOT NULL DEFAULT '',     -- what the community sees
    place_id INTEGER REFERENCES places(id),
    lat REAL NOT NULL,
    lng REAL NOT NULL,
    status TEXT NOT NULL,              -- pending / published / revised / blocked / redirect_911
    moderation_json TEXT NOT NULL DEFAULT '{}',
    incident_id INTEGER REFERENCES incidents(id),
    demo INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS walks (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    origin_place_id INTEGER REFERENCES places(id),
    dest_place_id INTEGER REFERENCES places(id),
    origin_lat REAL,                   -- set when the walk starts from the phone's current location
    origin_lng REAL,
    origin_label TEXT,
    started_at TEXT NOT NULL,
    eta TEXT NOT NULL,
    status TEXT NOT NULL,              -- active / arrived / overdue / escalated / cancelled
    contacts_json TEXT NOT NULL DEFAULT '[]',
    events_json TEXT NOT NULL DEFAULT '[]',
    ended_at TEXT
);
CREATE TABLE IF NOT EXISTS sos_events (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    lat REAL NOT NULL,
    lng REAL NOT NULL,
    place_label TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open',  -- open / acknowledged / resolved / cancelled
    brief_json TEXT,                      -- Responder Brief agent output (may stay NULL)
    brief_status TEXT NOT NULL DEFAULT 'pending',  -- pending / ready / failed / skipped
    contacts_notified_json TEXT NOT NULL DEFAULT '[]',
    timeline_json TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS escort_requests (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    from_place_id INTEGER REFERENCES places(id),
    to_place_id INTEGER REFERENCES places(id),
    created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'requested'
);
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    role TEXT NOT NULL,          -- user / assistant
    content TEXT NOT NULL,
    meta_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ai_runs (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    user_id INTEGER,
    agent TEXT NOT NULL,          -- moderator / corroborator / concierge / responder
    ref TEXT NOT NULL DEFAULT '', -- e.g. post:12, sos:3, chat
    model TEXT NOT NULL,
    status TEXT NOT NULL,         -- ok / error / budget_blocked / timeout
    requests INTEGER NOT NULL DEFAULT 0,
    tool_calls INTEGER NOT NULL DEFAULT 0,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    cached_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    reasoning_tokens INTEGER NOT NULL DEFAULT 0,
    gateway_cache_hits INTEGER NOT NULL DEFAULT 0,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    trace_json TEXT NOT NULL DEFAULT '[]',  -- tool calls and results, for the "behind the scenes" panel
    error TEXT
);
CREATE TABLE IF NOT EXISTS safety_events (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    user_id INTEGER,
    kind TEXT NOT NULL,        -- injection_blocked / profiling_rewritten / pii_removed / rate_limited / ...
    layer TEXT NOT NULL,       -- rule (code) / agent (model) / guard (server check on model output)
    detail TEXT NOT NULL,
    ref TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS post_reactions (
    post_id INTEGER NOT NULL REFERENCES posts(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    kind TEXT NOT NULL,                 -- like / confirm ("I saw this too")
    created_at TEXT NOT NULL,
    PRIMARY KEY (post_id, user_id, kind)
);
CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY,
    post_id INTEGER NOT NULL REFERENCES posts(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    raw_text TEXT NOT NULL,             -- what the commenter typed (private: author + audit only)
    text TEXT NOT NULL DEFAULT '',      -- what everyone sees
    status TEXT NOT NULL,               -- pending / published / revised / blocked / redirect_911 / held
    moderation_json TEXT NOT NULL DEFAULT '{}',
    demo INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_comments_post ON comments(post_id, created_at);
CREATE INDEX IF NOT EXISTS ix_posts_time ON posts(created_at);
CREATE INDEX IF NOT EXISTS ix_incidents_time ON incidents(last_reported);
CREATE INDEX IF NOT EXISTS ix_ai_runs_user ON ai_runs(user_id, created_at);
CREATE INDEX IF NOT EXISTS ix_chat_user ON chat_messages(user_id, id);
"""


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    # Databases created before walks could start from the current location get the new columns.
    cols = {r[1] for r in conn.execute("PRAGMA table_info(walks)")}
    for col, kind in (("origin_lat", "REAL"), ("origin_lng", "REAL"), ("origin_label", "TEXT")):
        if col not in cols:
            conn.execute(f"ALTER TABLE walks ADD COLUMN {col} {kind}")
    conn.commit()


# ------------------------------------------------------------------ helpers

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def now_iso() -> str:
    return iso(now_utc())


def ago_iso(**kwargs: float) -> str:
    return iso(now_utc() - timedelta(**kwargs))


def rows(cur: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in cur]


def one(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> dict[str, Any] | None:
    r = conn.execute(sql, params).fetchone()
    return dict(r) if r else None


def loads(text: str | None, default: Any = None) -> Any:
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def meters_between(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in meters (haversine)."""
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearest_place(conn: sqlite3.Connection, lat: float, lng: float) -> tuple[dict[str, Any], float]:
    best, best_d = None, float("inf")
    for p in rows(conn.execute("SELECT * FROM places")):
        d = meters_between(lat, lng, p["lat"], p["lng"])
        if d < best_d:
            best, best_d = p, d
    assert best is not None
    return best, best_d


def log_safety(conn: sqlite3.Connection, kind: str, layer: str, detail: str,
               user_id: int | None = None, ref: str = "") -> None:
    conn.execute(
        "INSERT INTO safety_events (created_at, user_id, kind, layer, detail, ref) VALUES (?,?,?,?,?,?)",
        (now_iso(), user_id, kind, layer, detail[:1000], ref),
    )
    conn.commit()
