"""Happening at Yale: real events from Yale's public calendar.

Source: events.yale.edu (Localist API v2, public, no key). Fetched at most every
15 minutes and cached in memory. Only in-person events whose venue is inside
Beacon's service area get a map pin; everything is labeled with its source, and
nothing is made up. If the calendar can't be reached, the app says so.
"""

import re
import threading
import time
from datetime import datetime, timedelta
from typing import Any

import httpx

from config import TZ, in_service_area

FEED = "https://events.yale.edu/api/2/events"
CACHE_SECONDS = 15 * 60
NOW_WINDOW = timedelta(hours=2)  # an event with no end time counts as "on" for 2 hours
OPEN_HOURS = timedelta(hours=5)  # longer than this = gallery-style opening hours, not an event you'd "go to"

# Event types that make for a good night out rank first; seminars and meetings last.
FUN_TYPES = {"Performances", "Music", "Theater", "Film", "Exhibitions", "Tours", "Athletics", "Sports", "Recreation",
             "Festivals", "Arts", "Dance", "Family", "Social", "Wellness", "Food", "Readings"}
SERIOUS_TYPES = {"Conferences Meetings & Seminars", "Colloquia & Symposia", "Workshops", "Information Sessions",
                 "Classes", "Defenses", "Training"}

_cache: dict[str, Any] = {"at": 0.0, "events": [], "error": None}
_lock = threading.Lock()


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(TZ)
    except ValueError:
        return None


def _clean(text: str) -> str:
    """Tidy the calendar's plain-text description: trim lines, keep paragraph breaks, cap the length."""
    paragraphs = ["\n".join(line.strip() for line in block.splitlines() if line.strip())
                  for block in re.split(r"\n\s*\n", text.replace("\r", ""))]
    out = "\n\n".join(p for p in paragraphs if p)
    return out if len(out) <= 2500 else out[:2500].rsplit(" ", 1)[0] + "..."


def _kind(types: list[str], title: str) -> str:
    t = set(types)
    low = title.lower()
    if t & {"Performances", "Music", "Theater", "Film", "Dance"}:
        return "performance"
    if "Exhibitions" in t:
        return "exhibition"
    if t & {"Athletics", "Sports", "Recreation"}:
        return "sports"
    if "fest" in low or "festival" in low or t & {"Festivals", "Social", "Food", "Family"}:
        return "social"
    if "Tours" in t:
        return "tour"
    if t & SERIOUS_TYPES:
        return "seminar"
    if "Talks & Lectures" in t or "lecture" in low:
        return "talk"
    return "event"


def _normalize(raw: dict[str, Any], today: datetime) -> list[dict[str, Any]]:
    ev = raw["event"]
    if ev.get("experience") == "virtual":
        return []
    geo = ev.get("geo") or {}
    try:
        lat, lng = float(geo.get("latitude")), float(geo.get("longitude"))
        if not in_service_area(lat, lng):
            lat, lng = None, None  # bad or far-away coordinates: list it, but no pin
    except (TypeError, ValueError):
        lat, lng = None, None
    types = [f["name"] for f in (ev.get("filters") or {}).get("event_types", [])]
    out = []
    for inst in ev.get("event_instances") or []:
        i = inst["event_instance"]
        start, end = _parse(i.get("start")), _parse(i.get("end"))
        if not start or start.date() < today.date() - timedelta(days=0) and not i.get("all_day"):
            continue
        out.append({
            "id": int(i["id"]),
            "event_id": int(ev["id"]),
            "title": ev.get("title", "").strip(),
            "start": start.isoformat(),
            "end": end.isoformat() if end else None,
            "all_day": bool(i.get("all_day")) or (start.hour == 0 and start.minute == 0 and not end),
            "venue": (ev.get("location_name") or "").strip(),
            "room": (ev.get("room_number") or "").strip(),
            "lat": lat, "lng": lng,
            "free": bool(ev.get("free")),
            "types": types,
            "kind": _kind(types, ev.get("title", "")),
            "url": ev.get("localist_url") or ev.get("url") or "https://events.yale.edu",
            "photo_url": (ev.get("photo_url") or "").replace("/huge/", "/big/") or None,  # 11 KB thumbnail, not 78 KB
            "photo_large": ev.get("photo_url") or None,
            "open_hours": bool(end and end - start >= OPEN_HOURS),
            # The full "About this event" text, shown inside Beacon (plain text only, never HTML).
            "description": _clean(ev.get("description_text") or ""),
            "address": (ev.get("address") or "").strip(),
            "ics_url": ev.get("localist_ics_url") or None,
            "ticket_cost": (ev.get("ticket_cost") or "").strip(),
            "ticket_url": ev.get("ticket_url") or None,
        })
    return out


def _fresh() -> bool:
    return time.time() - _cache["at"] < CACHE_SECONDS and bool(_cache["events"] or _cache["error"])


def _fetch() -> None:
    """Fetch the calendar into the cache. Call only while holding _lock."""
    today = datetime.now(TZ)
    try:
        resp = httpx.get(FEED, params={"days": 2, "pp": 100}, timeout=8,
                         headers={"User-Agent": "BulldogBeacon/1.0 (Yale MGT 409 class project)"})
        resp.raise_for_status()
        events: list[dict[str, Any]] = []
        for raw in resp.json().get("events", []):
            events += _normalize(raw, today)
        _cache.update(at=time.time(), events=events, error=None)
    except Exception as exc:  # keep serving the last good copy
        _cache.update(at=time.time(), error=f"Couldn't reach events.yale.edu ({type(exc).__name__})")


def _fetch_in_background() -> None:
    try:
        _fetch()
    finally:
        _lock.release()


def refresh(force: bool = False) -> dict[str, Any]:
    """Return the cached calendar, fetching it again when it's older than 15 minutes.

    Once there is a copy, a stale one is served at once while a background thread fetches the new one,
    so nobody waits on events.yale.edu (the stress test showed 50 users queuing behind one slow fetch).
    Only the very first fetch, which run.py starts at launch, makes callers wait."""
    if _fresh() and not force:
        return _cache
    if _cache["events"] and not force:
        if _lock.acquire(blocking=False):
            threading.Thread(target=_fetch_in_background, daemon=True).start()
        return _cache
    with _lock:
        if force or not _fresh():
            _fetch()
    return _cache


def happening(hours_ahead: int = 12, now: datetime | None = None) -> dict[str, Any]:
    """Events on now, starting within `hours_ahead`, or open all day today. Sorted for a calm, fun feed."""
    cache = refresh()
    now = now or datetime.now(TZ)
    horizon = now + timedelta(hours=hours_ahead)
    out = []
    for e in cache["events"]:
        start = datetime.fromisoformat(e["start"])
        end = datetime.fromisoformat(e["end"]) if e["end"] else None
        if e["all_day"]:
            if start.date() != now.date():
                continue
            status = "all_day"
        else:
            finish = end or start + NOW_WINDOW
            if finish < now or start > horizon:
                continue
            if e["open_hours"]:
                status = "all_day"  # e.g. a gallery open 10-5: show it with today's openings, after real happenings
            elif start <= now:
                status = "now"
            elif start - now <= timedelta(minutes=90):
                status = "soon"
            else:
                status = "later"
        out.append({**e, "status": status})
    rank = {"now": 0, "soon": 1, "later": 2, "all_day": 3}
    fun = {"performance": 0, "social": 0, "sports": 0, "exhibition": 1, "tour": 1, "event": 2, "talk": 2, "seminar": 3}
    out.sort(key=lambda e: (rank[e["status"]], fun.get(e["kind"], 2), e["start"]))
    # One card per event (multi-day events can list several instances).
    seen, unique = set(), []
    for e in out:
        if e["event_id"] not in seen:
            seen.add(e["event_id"])
            unique.append(e)
    return {"events": unique, "source": "events.yale.edu", "error": cache["error"],
            "fetched_at": datetime.fromtimestamp(cache["at"], TZ).isoformat() if cache["at"] else None}
