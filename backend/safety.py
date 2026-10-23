"""Code-level safety rules. These run before and after every model call, cost no
tokens, and can't be talked out of their job by a clever prompt.

Layers (matching safety_events.layer):
- rule:  checks on user input before any model sees it
- agent: what the model itself decides (moderation decisions)
- guard: checks on model output before the user sees it
"""

import re
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta

from config import (GLOBAL_DAILY_TOKEN_CAP, POSTS_PER_HOUR, TZ, USER_AI_CALLS_PER_MINUTE,
                    USER_DAILY_TOKEN_CAP)
from db import iso, log_safety, now_utc

# ------------------------------------------------------------ personal info

_PHONE = re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")


def _digits(text: str) -> str:
    d = re.sub(r"\D", "", text)
    return d[1:] if len(d) == 11 and d.startswith("1") else d


def redact_personal_info(text: str, allowed_phones: frozenset[str] = frozenset()) -> tuple[str, list[str]]:
    """Remove phone numbers, emails, SSNs and card numbers from a community post.
    Verified public numbers (Yale PD, escort...) in `allowed_phones` are kept."""
    found = []
    for label, pattern, repl in [("card number", _CARD, "[card number removed]"),
                                 ("SSN", _SSN, "[ID number removed]"),
                                 ("email", _EMAIL, "[email removed]")]:
        if pattern.search(text):
            found.append(label)
            text = pattern.sub(repl, text)

    def phone(m: re.Match) -> str:
        if _digits(m.group(0)) in allowed_phones:
            return m.group(0)
        found.append("phone number")
        return "[phone number removed]"

    text = _PHONE.sub(phone, text)
    return text, sorted(set(found))


# ---------------------------------------------------------- prompt injection

_INJECTION = re.compile(
    r"(ignore|disregard|forget|override)\s+(all\s+|any\s+|the\s+|your\s+)?(previous|prior|above|earlier|system)?\s*"
    r"(instructions|rules|prompts?|guidelines|messages)"
    r"|\b(system prompt|developer message|you are now|new instructions|jailbreak|DAN mode)\b"
    r"|</?\s*(system|assistant|instructions|untrusted_post|community_report)\s*>"
    r"|\b(as an ai|ai assistant|beacon ai|moderator)\s*[:,]\s*(you must|always|never|approve|publish)",
    re.IGNORECASE,
)


def looks_like_injection(text: str) -> str | None:
    m = _INJECTION.search(text)
    return m.group(0) if m else None


def fence(text: str) -> str:
    """Neutralise anything that looks like our own data delimiters before wrapping
    untrusted text in them, so a post can't 'close the tag' and escape."""
    return re.sub(r"<\s*/?\s*(untrusted_post|community_report|system|instructions)[^>]*>", "[tag removed]", text,
                  flags=re.IGNORECASE)


# ------------------------------------------------------------- crisis words

_CRISIS = re.compile(
    r"\b(kill myself|end my life|want to die|suicid\w*|self[- ]harm|hurt myself|cutting myself|"
    r"no reason to live|don'?t want to (be here|live)|overdos\w*)\b",
    re.IGNORECASE,
)
_IMMEDIATE = re.compile(
    r"\b(being (followed|attacked|robbed)|someone is (following|attacking|breaking in)|has a (gun|knife)|"
    r"(gun|knife) (on|at) me|i'?m (bleeding|hurt|in danger|trapped)|help me now|shots? fired|"
    r"someone (got|was|is) (shot|stabbed)|break(ing)? in(to)? my)\b",
    re.IGNORECASE,
)


def crisis_language(text: str) -> bool:
    return bool(_CRISIS.search(text))


def immediate_danger_language(text: str) -> bool:
    return bool(_IMMEDIATE.search(text))


# --------------------------------------------------- phone numbers in output

def vet_phone_numbers(conn: sqlite3.Connection, text: str) -> tuple[str, list[str]]:
    """Guard: every phone number the model writes must be one of our verified
    resources (or a demo 555 number). Anything else is replaced, because a wrong
    emergency number is worse than none."""
    known = {r[0] for r in conn.execute("SELECT phone FROM resources WHERE phone IS NOT NULL")}
    removed = []

    def check(m: re.Match) -> str:
        digits = _digits(m.group(0))
        if digits in known or digits[3:6] == "555":
            return m.group(0)
        removed.append(m.group(0))
        return "[unverified number removed - see Resources]"

    return _PHONE.sub(check, text), removed


# ------------------------------------------------------ rate and budget caps

class LimitExceeded(Exception):
    """Raised before a model call when a user or the whole app is over its limit."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


def _start_of_today_utc() -> str:
    local_midnight = now_utc().astimezone(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    return iso(local_midnight)


def tokens_today(conn: sqlite3.Connection, user_id: int | None = None) -> int:
    sql = "SELECT COALESCE(SUM(input_tokens + output_tokens), 0) FROM ai_runs WHERE created_at >= ?"
    params: tuple = (_start_of_today_utc(),)
    if user_id is not None:
        sql += " AND user_id = ?"
        params += (user_id,)
    return int(conn.execute(sql, params).fetchone()[0])


def check_ai_budget(conn: sqlite3.Connection, user_id: int | None, pending: int = 0) -> None:
    """Called before every agent run. Three limits: calls per minute per user,
    tokens per day per user, and tokens per day for the whole app. `pending` is the
    number of this user's runs still in progress (not yet in ai_runs)."""
    if user_id is not None:
        minute_ago = iso(now_utc() - timedelta(minutes=1))
        recent = conn.execute("SELECT COUNT(*) FROM ai_runs WHERE user_id = ? AND created_at >= ?",
                              (user_id, minute_ago)).fetchone()[0]
        if recent + pending >= USER_AI_CALLS_PER_MINUTE:
            log_safety(conn, "rate_limited", "rule", f"{recent} AI runs in the last minute, {pending} in progress", user_id)
            raise LimitExceeded("rate_limited", "You're sending requests very quickly. Please wait a minute and try again.")
        used = tokens_today(conn, user_id)
        if used >= USER_DAILY_TOKEN_CAP:
            log_safety(conn, "user_budget_reached", "rule", f"{used} tokens today (cap {USER_DAILY_TOKEN_CAP})", user_id)
            raise LimitExceeded("user_budget_reached",
                                "You've reached today's AI limit. Emergency features, the alert map and Resources still work.")
    total = tokens_today(conn)
    if total >= GLOBAL_DAILY_TOKEN_CAP:
        log_safety(conn, "global_budget_reached", "rule", f"{total} tokens today (cap {GLOBAL_DAILY_TOKEN_CAP})", user_id)
        raise LimitExceeded("global_budget_reached",
                            "Beacon's AI is paused for today (budget reached). Emergency features still work.")


_in_flight: dict[int, int] = {}
_in_flight_lock = threading.Lock()


@contextmanager
def ai_slot(conn: sqlite3.Connection, user_id: int | None) -> Iterator[None]:
    """Check the caps and hold a slot while a run is in progress. Runs are only logged when they
    finish, so without this a burst of simultaneous requests would all pass the per-minute check
    (the stress test sent 20 chats at once from one NetID and all 20 got through)."""
    with _in_flight_lock:
        check_ai_budget(conn, user_id, _in_flight.get(user_id, 0) if user_id is not None else 0)
        if user_id is not None:
            _in_flight[user_id] = _in_flight.get(user_id, 0) + 1
    try:
        yield
    finally:
        if user_id is not None:
            with _in_flight_lock:
                _in_flight[user_id] -= 1
                if not _in_flight[user_id]:
                    del _in_flight[user_id]


def check_post_rate(conn: sqlite3.Connection, user_id: int) -> None:
    hour_ago = iso(now_utc() - timedelta(hours=1))
    n = conn.execute("SELECT COUNT(*) FROM posts WHERE user_id = ? AND created_at >= ? AND demo = 0",
                     (user_id, hour_ago)).fetchone()[0]
    if n >= POSTS_PER_HOUR:
        log_safety(conn, "rate_limited", "rule", f"{n} posts in the last hour", user_id)
        raise LimitExceeded("rate_limited", f"You can post up to {POSTS_PER_HOUR} alerts an hour. Please try again later.")
