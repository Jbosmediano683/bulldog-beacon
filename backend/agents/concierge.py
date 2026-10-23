"""Safety Concierge agent: the chat assistant ("Ask Beacon").

Tools are read-only lookups against Beacon's own database (places, incidents,
verified resources) plus a clock. The agent can *propose* actions as buttons
(start a walk, call a number, request an escort); only the person can tap them.
"""

import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.usage import UsageLimits

import bluephones
import events
import shuttle
from agents.runtime import as_json, load_prompt, run_logged, settings
from config import TZ
from db import loads, meters_between, now_utc, parse_iso, rows
from models import ConciergeReply
from safety import fence

LIMITS = UsageLimits(request_limit=6, tool_calls_limit=8, total_tokens_limit=60_000)
WALK_M_PER_MIN = 80        # an unhurried walking pace
DETOUR = 1.3               # streets are longer than a straight line
ROUTE_BUFFER_M = 220       # incidents this close to the route count as "on the way"


@dataclass
class ConciergeDeps:
    conn: sqlite3.Connection
    user: dict[str, Any]
    here: dict[str, Any]                       # place row for the user's location
    now_local: datetime
    seen_incident_ids: set[int] = field(default_factory=set)


# ------------------------------------------------------------ tool helpers

def _place(conn: sqlite3.Connection, place_id: int) -> dict[str, Any] | None:
    r = conn.execute("SELECT * FROM places WHERE id = ?", (place_id,)).fetchone()
    return dict(r) if r else None


def _incident_view(inc: dict[str, Any], distance_m: float) -> dict[str, Any]:
    minutes = int((now_utc() - parse_iso(inc["last_reported"])).total_seconds() // 60)
    return {
        "id": inc["id"], "title": inc["title"], "category": inc["category"], "severity": inc["severity"],
        "reports": inc["report_count"], "last_report_minutes_ago": minutes, "distance_m": int(distance_m),
        "demo": bool(inc["demo"]),
        "summary": f"<community_report>{fence(inc['summary'])}</community_report>",
        "advice": f"<community_report>{fence(inc['advice'])}</community_report>",
    }


def _active_incidents(conn: sqlite3.Connection, hours: int) -> list[dict[str, Any]]:
    since = (now_utc().timestamp() - hours * 3600)
    return [i for i in rows(conn.execute("SELECT * FROM incidents WHERE status = 'active'"))
            if parse_iso(i["last_reported"]).timestamp() >= since]


def _dist_to_segment_m(p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    """Approximate distance from point p to segment ab (fine at city scale)."""
    import math
    k = 111_320.0
    kx = k * math.cos(math.radians(a[0]))
    px, py = (p[1] - a[1]) * kx, (p[0] - a[0]) * k
    bx, by = (b[1] - a[1]) * kx, (b[0] - a[0]) * k
    seg = bx * bx + by * by
    t = 0.0 if seg == 0 else max(0.0, min(1.0, (px * bx + py * by) / seg))
    return math.hypot(px - t * bx, py - t * by)


def services_status(conn: sqlite3.Connection, now_local: datetime) -> dict[str, Any]:
    """Deterministic open/closed status from the hours on Yale's pages."""
    h = now_local.hour + now_local.minute / 60
    weekday = now_local.weekday() < 5
    res = {r["name"]: r for r in rows(conn.execute("SELECT name, phone, phone_display, hours FROM resources"))}

    def item(name: str, open_now: bool | None) -> dict[str, Any]:
        r = res[name]
        return {"name": name, "phone": r["phone"], "phone_display": r["phone_display"], "hours": r["hours"],
                "open_now": open_now}

    return {
        "new_haven_time": now_local.strftime("%A %I:%M %p"),
        "after_dark_approx": h >= 18 or h < 7,
        "services": [
            item("Emergency: 911", True),
            item("Yale Police Department", True),
            item("Yale Security walking escort", True),
            item("Nighttime Safe Ride", h >= 18 or h < 6),
            item("Yale Mental Health & Counseling", weekday and 8.5 <= h < 17),
            item("On-call mental health clinician", not (weekday and 8.5 <= h < 17)),
            item("Walden Peer Counseling", h >= 20 or h < 8),
            item("Yale Employee Assistance Program (Optum)", True),
            item("Yale Shuttle", h >= 5.5),
            item("SHARE Center", True),
            item("988 Suicide & Crisis Lifeline", True),
        ],
    }


# ------------------------------------------------------------------ agent

_agent: Agent | None = None


def get_agent() -> Agent:
    global _agent
    if _agent is not None:
        return _agent
    agent = Agent(None, deps_type=ConciergeDeps, output_type=ConciergeReply,
                  instructions=load_prompt("concierge"), name="concierge", retries=1)

    @agent.tool
    def find_place(ctx: RunContext[ConciergeDeps], query: str) -> str:
        """Look up a Yale or New Haven place by name or nickname. Returns up to 3 matches with IDs."""
        q = re.sub(r"[^a-z0-9 ]", " ", query.lower()).split()
        scored = []
        for p in rows(ctx.deps.conn.execute("SELECT * FROM places")):
            names = [p["name"].lower(), *loads(p["aliases_json"], [])]
            text = " ".join(names)
            score = sum(1 for w in q if len(w) > 2 and w in text)
            if any(a in query.lower() for a in names if len(a) > 3):
                score += 3
            if score:
                d = meters_between(ctx.deps.here["lat"], ctx.deps.here["lng"], p["lat"], p["lng"])
                scored.append((score, {"id": p["id"], "name": p["name"], "kind": p["kind"],
                                       "address": p["address"], "distance_from_user_m": int(d)}))
        scored.sort(key=lambda s: -s[0])
        if not scored:
            return as_json({"matches": [], "note": "No known place matches. Ask the person to pick a nearby landmark."})
        return as_json({"matches": [s[1] for s in scored[:3]]})

    @agent.tool
    def incidents_near(ctx: RunContext[ConciergeDeps], place_id: int, radius_m: int = 500, hours: int = 24) -> str:
        """Active incidents on the community board within radius_m meters of a place, reported in the last `hours`."""
        place = _place(ctx.deps.conn, place_id)
        if not place:
            return as_json({"error": f"Unknown place_id {place_id}. Use find_place first."})
        radius_m, hours = max(100, min(radius_m, 2000)), max(1, min(hours, 72))
        found = []
        for inc in _active_incidents(ctx.deps.conn, hours):
            d = meters_between(place["lat"], place["lng"], inc["lat"], inc["lng"])
            if d <= radius_m:
                found.append(_incident_view(inc, d))
                ctx.deps.seen_incident_ids.add(inc["id"])
        found.sort(key=lambda i: i["distance_m"])
        return as_json({"place": place["name"], "radius_m": radius_m, "hours": hours,
                        "count": len(found), "incidents": found[:8]})

    @agent.tool
    def route_check(ctx: RunContext[ConciergeDeps], origin_place_id: int, dest_place_id: int, hours: int = 12) -> str:
        """Everything for an 'A to B' question in one call: walking estimate, incidents along the
        route in the last `hours`, and which escort/ride services are open right now."""
        a, b = _place(ctx.deps.conn, origin_place_id), _place(ctx.deps.conn, dest_place_id)
        if not a or not b:
            return as_json({"error": "Unknown place id. Use find_place first."})
        straight = meters_between(a["lat"], a["lng"], b["lat"], b["lng"])
        walk_min = max(1, round(straight * DETOUR / WALK_M_PER_MIN))
        on_route = []
        for inc in _active_incidents(ctx.deps.conn, max(1, min(hours, 72))):
            d = _dist_to_segment_m((inc["lat"], inc["lng"]), (a["lat"], a["lng"]), (b["lat"], b["lng"]))
            if d <= ROUTE_BUFFER_M:
                on_route.append(_incident_view(inc, d))
                ctx.deps.seen_incident_ids.add(inc["id"])
        status = services_status(ctx.deps.conn, ctx.deps.now_local)
        return as_json({
            "from": a["name"], "to": b["name"], "walk_estimate_min": walk_min,
            "distance_m": int(straight * DETOUR),
            "incidents_on_route": on_route[:8], "after_dark_approx": status["after_dark_approx"],
            "blue_phones_along_route": bluephones.along(a, b, 60),
            "escort_and_rides": [s for s in status["services"]
                                 if s["name"] in ("Yale Security walking escort", "Nighttime Safe Ride")],
        })

    @agent.tool
    def shuttle_options(ctx: RunContext[ConciergeDeps], origin_place_id: int, dest_place_id: int) -> str:
        """Fastest way between two places: walking vs. each Yale Shuttle route running now, live from Yale's shuttle
        system. Each option: where to board and get off, minutes until the bus, ride minutes in the direction the bus
        drives (long_way_around flags a bus that loops across town first), total minutes and arrival time.
        `recommend` is "shuttle", "walk", or "none" (no single ride connects them now)."""
        a, b = _place(ctx.deps.conn, origin_place_id), _place(ctx.deps.conn, dest_place_id)
        if not a or not b:
            return as_json({"error": "Unknown place id. Use find_place first."})
        return as_json({"from": a["name"], "to": b["name"], **shuttle.options(a, b)})

    @agent.tool
    def get_resources(ctx: RunContext[ConciergeDeps],
                      category: Literal["emergency", "escort", "ride", "mental_health", "sexual_misconduct",
                                        "all"] = "all") -> str:
        """Verified Yale safety and support resources (phone numbers, hours, who can use them)."""
        sql, params = "SELECT name, category, phone, phone_display, hours, who, description FROM resources", ()
        if category != "all":
            sql += " WHERE category = ?"
            params = (category,)
        return as_json(rows(ctx.deps.conn.execute(sql, params)))

    @agent.tool
    def yale_events(ctx: RunContext[ConciergeDeps], hours_ahead: int = 6) -> str:
        """Real Yale events (from Yale's public calendar) happening now or starting within `hours_ahead`,
        nearest to the person first. Good for someone who feels anxious or isolated, or asks what's going on."""
        data = events.happening(max(1, min(hours_ahead, 24)))
        here = ctx.deps.here
        items = []
        for e in data["events"]:
            d = meters_between(here["lat"], here["lng"], e["lat"], e["lng"]) if e["lat"] is not None else None
            items.append({"title": fence(e["title"]), "status": e["status"], "start": e["start"][11:16],
                          "end": (e["end"] or "")[11:16], "venue": e["venue"], "free": e["free"], "kind": e["kind"],
                          "distance_m": int(d) if d is not None else None})
        items.sort(key=lambda x: (x["status"] not in ("now", "soon"), x["distance_m"] if x["distance_m"] is not None else 9e9))
        return as_json({"source": "events.yale.edu", "error": data["error"], "events": items[:8]})

    @agent.tool
    def services_open_now(ctx: RunContext[ConciergeDeps]) -> str:
        """Current New Haven time and which Yale safety and support services are open right now."""
        return as_json(services_status(ctx.deps.conn, ctx.deps.now_local))

    _agent = agent
    return agent


def history_messages(conn: sqlite3.Connection, user_id: int, turns: int) -> list[Any]:
    """Recent chat turns as PydanticAI messages (text only, no old tool output)."""
    recent = rows(conn.execute("SELECT role, content FROM chat_messages WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                               (user_id, turns * 2)))[::-1]
    out: list[Any] = []
    for m in recent:
        if m["role"] == "user":
            out.append(ModelRequest(parts=[UserPromptPart(content=m["content"])]))
        else:
            out.append(ModelResponse(parts=[TextPart(content=m["content"])]))
    return out


def build_prompt(deps: ConciergeDeps, message: str, hints: list[str]) -> str:
    u, here = deps.user, deps.here
    lines = [
        f"[Context] New Haven time: {deps.now_local.strftime('%A %b %d, %I:%M %p')}. "
        f"Person: {u['name']} ({u['affiliation']}, {u['unit'] or 'Yale'}). "
        f"Current location: {here['name']} (place_id {here['id']}).",
    ]
    lines += [f"[Code check] {h}" for h in hints]
    lines += ["[Message]", message]
    return "\n".join(lines)


async def ask(conn: sqlite3.Connection, *, deps: ConciergeDeps, message: str, hints: list[str],
              history: list[Any], ref: str = "chat") -> tuple[ConciergeReply, Any]:
    record = await run_logged(
        conn, get_agent(), build_prompt(deps, message, hints), agent_name="concierge",
        user_id=deps.user["id"], ref=ref, limits=LIMITS, deps=deps, message_history=history,
        model_settings=settings("concierge", max_tokens=1600),
    )
    return record.output, record
