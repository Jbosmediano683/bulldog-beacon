"""Yale Shuttle: routes, stops, live buses, and arrival times from Yale's own shuttle system.

Yale's "Yale Shuttles in Real-time" page (yale.downtownerapp.com, linked from your.yale.edu) reads public JSON
from the same server. Beacon reads it too and caches it, so members see the shuttle map inside the app.
If the feed can't be reached, Beacon serves its last good copy and says so; it never makes up a bus.
"""

import math
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any

import httpx

from db import meters_between

BASE = "https://yale.downtownerapp.com"
SOURCE = "Yale Shuttle real-time system (yale.downtownerapp.com, linked from your.yale.edu)"
HOURS = "Sunday to Saturday, 5:30 am to midnight; each route has its own hours"
TTL = {"routes": 300, "stops": 6 * 3600, "announcements": 300, "buses": 8}
ETA_TTL = 20
HEADERS = {"User-Agent": "BulldogBeacon/1.0 (Yale MGT 409 class project)"}

_cache: dict[str, dict[str, Any]] = {k: {"at": 0.0, "data": None, "error": None} for k in TTL}
_eta: dict[int, tuple[float, list[dict[str, Any]]]] = {}
_lock = threading.Lock()


_client = httpx.Client(base_url=BASE, headers=HEADERS, timeout=6,
                       limits=httpx.Limits(max_connections=16, max_keepalive_connections=16))  # reuse connections


def _get(path: str, params: dict[str, Any] | None = None) -> Any:
    r = _client.get(f"/{path}", params=params)
    r.raise_for_status()
    return r.json()


def _path_points(flat: list[float]) -> list[list[float]]:
    return [[round(flat[i], 6), round(flat[i + 1], 6)] for i in range(0, len(flat) - 1, 2)]


def _fetch(kind: str) -> Any:
    if kind == "routes":
        return [{"id": r["id"], "name": r["name"], "short_name": r.get("short_name") or "",
                 "hours": r.get("description") or "", "color": "#" + (r.get("color") or "286dc0"),
                 "running_now": bool(r.get("active")), "stops": r.get("stops") or [],
                 "path": _path_points(r.get("path") or [])}
                for r in _get("routes_routes.php", {"inactive": "true"})]
    if kind == "stops":
        return {s["id"]: {"id": s["id"], "name": s["name"].strip(), "lat": s["lat"], "lng": s["lon"]}
                for s in _get("routes_stops.php")}
    if kind == "announcements":
        return [{"title": a.get("title") or "", "message": a.get("message") or ""}
                for a in (_get("routes_announcements.php") or [])]
    if kind == "buses":
        return [{"id": b["id"], "name": b.get("name") or "", "lat": b["lat"], "lng": b["lon"],
                 "heading": b.get("heading") or 0, "route": b.get("route"), "updated": b.get("lastUpdate")}
                for b in (_get("routes_buses.php") or [])]
    raise ValueError(kind)


def get(kind: str) -> dict[str, Any]:
    """Cached copy of one feed: {"data", "at", "error"}. Fetches when stale; keeps the last good copy on failure."""
    c = _cache[kind]
    if time.time() - c["at"] < TTL[kind] and (c["data"] is not None or c["error"]):
        return c
    with _lock:
        if time.time() - c["at"] < TTL[kind] and (c["data"] is not None or c["error"]):
            return c
        try:
            c.update(data=_fetch(kind), error=None)
        except Exception as exc:  # keep serving the last good copy
            c["error"] = f"Couldn't reach Yale's shuttle system ({type(exc).__name__})"
        c["at"] = time.time()
        return c


def system() -> dict[str, Any]:
    """Routes, stops, and announcements for the shuttle map."""
    routes, stops, notes = get("routes"), get("stops"), get("announcements")
    error = routes["error"] or stops["error"]
    return {"routes": routes["data"] or [], "stops": list((stops["data"] or {}).values()),
            "announcements": notes["data"] or [], "hours": HOURS, "source": SOURCE,
            "error": error if not (routes["data"] and stops["data"]) else None}


def live() -> dict[str, Any]:
    b = get("buses")
    return {"buses": b["data"] or [], "error": b["error"] if b["data"] is None else None, "fetched_at": int(b["at"])}


def etas(stop_id: int) -> list[dict[str, Any]]:
    """Next arrivals at a stop: [{route, bus, minutes}], soonest first (minutes 0 means arriving now)."""
    hit = _eta.get(stop_id)
    if hit and time.time() - hit[0] < ETA_TTL:
        return hit[1]
    try:
        raw = _get("routes_eta.php", {"stop": stop_id}).get("etas") or {}
        rows = [{"route": e.get("route"), "bus": e.get("bus_name") or "", "bus_id": e.get("bus_id"),
                 "minutes": int(e.get("avg") or 0)}
                for v in raw.values() for e in (v.get("etas") or [])]
    except Exception:
        return hit[1] if hit else []
    rows.sort(key=lambda e: e["minutes"])
    _eta[stop_id] = (time.time(), rows)
    return rows


# ------------------------------------------------------------------ trip planning

def _xy(lat: float, lng: float, lat0: float) -> tuple[float, float]:
    return lng * 111320.0 * math.cos(math.radians(lat0)), lat * 110540.0


def route_geometry(route: dict[str, Any], stops: dict[int, dict[str, Any]]) -> dict[str, Any] | None:
    """Distance along the route (meters from the path's start) of each stop in the route's stop list.

    Every Yale route is a loop drawn in driving order, and its stop list is in the same order. Stops are matched to the
    path in that order (each one after the previous), so a road the bus drives twice, out and back, is matched correctly.
    """
    path = route["path"]
    if len(path) < 2 or not route["stops"]:
        return None
    lat0 = path[0][0]
    pts = [_xy(a, b, lat0) for a, b in path]
    cum = [0.0]
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        cum.append(cum[-1] + math.hypot(x2 - x1, y2 - y1))
    length = cum[-1]

    def project(p: tuple[float, float], start: float) -> tuple[float, float]:
        best = (float("inf"), 0.0)
        for i, ((x1, y1), (x2, y2)) in enumerate(zip(pts, pts[1:])):
            if cum[i + 1] < start:
                continue
            dx, dy = x2 - x1, y2 - y1
            seg = dx * dx + dy * dy or 1.0
            t = max(0.0, min(1.0, ((p[0] - x1) * dx + (p[1] - y1) * dy) / seg))
            along = cum[i] + t * (cum[i + 1] - cum[i])
            if along < start:
                continue
            d = math.hypot(p[0] - (x1 + t * dx), p[1] - (y1 + t * dy))
            if d < best[0] - 1e-6:
                best = (d, along)
        return best

    positions, prev = [], 0.0
    for sid in route["stops"]:
        s = stops.get(sid)
        if not s:
            positions.append(None)
            continue
        p = _xy(s["lat"], s["lng"], lat0)
        off, along = project(p, max(0.0, prev - 40))
        if off > 150:  # in-order match failed (rare): fall back to the nearest point anywhere on the loop
            off2, along2 = project(p, 0.0)
            if off2 < off:
                off, along = off2, along2
        positions.append(along)
        prev = along
    return {"length": length, "cum": cum, "positions": positions}


def ride_meters(geo: dict[str, Any], i: int, j: int) -> float:
    """Meters the bus drives from stop index i to stop index j, going forward around the loop."""
    a, b = geo["positions"][i], geo["positions"][j]
    if a is None or b is None:
        return float("inf")
    if j > i:
        return max(0.0, b - a) if b >= a else geo["length"] - a + b
    return geo["length"] - a + b


def segment(route: dict[str, Any], geo: dict[str, Any], i: int, j: int) -> list[list[float]]:
    """The part of the route's path the bus drives from stop index i to stop index j (for drawing the ride)."""
    a, b, cum, path = geo["positions"][i], geo["positions"][j], geo["cum"], route["path"]
    if a is None or b is None:
        return []
    def between(lo: float, hi: float) -> list[list[float]]:
        return [pt for pt, c in zip(path, cum) if lo <= c <= hi]
    if j > i and b >= a:
        return between(a, b)
    return between(a, geo["length"]) + between(0.0, b)


WALK_M_PER_MIN = 80        # unhurried walking pace, the same one the Concierge uses
DETOUR = 1.3               # streets are longer than a straight line
NEAR_M = 700               # stops farther than this (straight line) aren't worth walking to
TYPICAL_M_PER_MIN = {"in_town": 120.0, "long": 300.0}   # used only when live arrivals can't measure a route
_speed: dict[int, tuple[float, float]] = {}


def walk_min(meters: float) -> int:
    return max(1, round(meters * DETOUR / WALK_M_PER_MIN))


def _etas_many(stop_ids: set[int]) -> dict[int, list[dict[str, Any]]]:
    ids = list(stop_ids)
    with ThreadPoolExecutor(max_workers=16) as pool:
        return dict(zip(ids, pool.map(etas, ids)))


def _sample_stops(route: dict[str, Any]) -> list[int]:
    """Indexes of six stops spread around the route, used to measure its speed."""
    n = len(route["stops"])
    return sorted({round(k * (n - 1) / 5) for k in range(6)}) if n else []


def _speed_fresh(route_id: int) -> bool:
    hit = _speed.get(route_id)
    return bool(hit and time.time() - hit[0] < 600)


def route_speed(route: dict[str, Any], geo: dict[str, Any], found: dict[int, list[dict[str, Any]]]) -> tuple[float, str]:
    """Meters per minute this route is moving right now, measured from live arrival times at six of its stops
    (`found` holds those arrivals). In-town loops run about 90 to 190 m a minute with stops; the West Campus
    routes, mostly highway, about 500."""
    if _speed_fresh(route["id"]):
        return _speed[route["id"]][1], "measured"
    idxs = _sample_stops(route)
    per_bus: dict[Any, list[tuple[int, int]]] = {}
    for i in idxs:
        for e in found.get(route["stops"][i]) or []:
            if e["route"] == route["id"]:
                per_bus.setdefault(e["bus_id"] or e["bus"], []).append((e["minutes"], i))
    speeds = []
    for obs in per_bus.values():
        obs.sort()
        for (m1, i1), (m2, i2) in zip(obs, obs[1:]):
            d = ride_meters(geo, i1, i2)
            if m2 - m1 >= 3 and d < geo["length"]:
                speeds.append(d / (m2 - m1))
    if speeds:
        v = statistics.median(speeds)
        _speed[route["id"]] = (time.time(), v)
        return v, "measured"
    return TYPICAL_M_PER_MIN["long" if geo["length"] > 15000 else "in_town"], "typical"


def plan(origin: dict[str, Any], dest: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    """The fastest way from origin to dest: a single Yale Shuttle ride, or just walking.

    For each running route it tries the stops near you and near your destination, in the direction the bus actually
    drives, so a bus that would loop halfway across town first comes out slow. Each option's time is
    walk to the stop + wait for the first bus you can catch + ride + walk to the destination."""
    now = now or datetime.now()
    direct_m = _meters(origin, dest)
    walking = walk_min(direct_m)
    sysm = system()
    result: dict[str, Any] = {"walk_only_min": walking, "walk_only_m": int(direct_m * DETOUR), "options": [],
                              "announcements": sysm["announcements"], "error": sysm["error"]}
    if sysm["error"]:
        return result
    stops = {s["id"]: s for s in sysm["stops"]}
    near_o = {sid: _meters(origin, s) for sid, s in stops.items() if _meters(origin, s) <= NEAR_M}
    near_d = {sid: _meters(dest, s) for sid, s in stops.items() if _meters(dest, s) <= NEAR_M}
    candidates = []
    for r in sysm["routes"]:
        if not r["running_now"]:
            continue
        boards = sorted((i for i, sid in enumerate(r["stops"]) if sid in near_o), key=lambda i: near_o[r["stops"][i]])[:3]
        alights = sorted((j for j, sid in enumerate(r["stops"]) if sid in near_d), key=lambda j: near_d[r["stops"][j]])[:3]
        if boards and alights:
            candidates.append((r, boards, alights))
    if not candidates:
        later = [r for r in sysm["routes"] if not r["running_now"]
                 and any(sid in near_o for sid in r["stops"]) and any(sid in near_d for sid in r["stops"])]
        result["not_running_now"] = [{"route": r["name"], "hours": r["hours"]} for r in later]
        result["recommend"] = "walk" if walking <= 20 else "none"   # no single shuttle ride connects these places now
        return result

    # One parallel batch: arrivals at every candidate stop, plus six stops on each route whose speed isn't measured yet.
    need = {r["stops"][k] for r, b, a in candidates for k in b + a}
    need |= {r["stops"][k] for r, _, _ in candidates if not _speed_fresh(r["id"]) for k in _sample_stops(r)}
    live_etas = _etas_many(need)
    buses = live()["buses"]
    options = []
    for r, boards, alights in candidates:
        geo = route_geometry(r, stops)
        if not geo:
            continue
        speed, speed_src = route_speed(r, geo, live_etas)
        on_route = sum(1 for b in buses if b["route"] == r["id"])
        for i in boards:
            for j in alights:
                if r["stops"][i] == r["stops"][j]:
                    continue
                ride_m = ride_meters(geo, i, j)
                to_stop, from_stop = walk_min(near_o[r["stops"][i]]), walk_min(near_d[r["stops"][j]])
                if to_stop + from_stop >= walking:   # walking to and from the stops alone takes longer than walking there
                    continue
                at_board = sorted((e for e in live_etas[r["stops"][i]] if e["route"] == r["id"]), key=lambda e: e["minutes"])
                catch = next((e for e in at_board if e["minutes"] >= to_stop), None)
                if catch:
                    wait_until, timing = catch["minutes"], "live"
                elif at_board and on_route:   # the next bus leaves before you'd reach the stop: the one after it
                    wait_until, timing = at_board[0]["minutes"] + round(geo["length"] / speed / on_route), "estimated"
                else:
                    continue
                ride, ride_src = ride_m / speed, speed_src
                if catch and catch["bus_id"] is not None:
                    later = next((e for e in live_etas[r["stops"][j]]
                                  if e["bus_id"] == catch["bus_id"] and e["minutes"] > catch["minutes"]), None)
                    if later and abs((later["minutes"] - catch["minutes"]) - ride) < max(8.0, ride):
                        ride, ride_src = later["minutes"] - catch["minutes"], "live"
                total = wait_until + round(ride) + from_stop
                options.append({
                    "route_id": r["id"], "route": r["name"], "color": r["color"], "hours": r["hours"],
                    "board": {"stop_id": r["stops"][i], "name": stops[r["stops"][i]]["name"], "lat": stops[r["stops"][i]]["lat"],
                              "lng": stops[r["stops"][i]]["lng"], "walk_min": to_stop, "walk_m": int(near_o[r["stops"][i]] * DETOUR)},
                    "alight": {"stop_id": r["stops"][j], "name": stops[r["stops"][j]]["name"], "lat": stops[r["stops"][j]]["lat"],
                               "lng": stops[r["stops"][j]]["lng"], "walk_min": from_stop, "walk_m": int(near_d[r["stops"][j]] * DETOUR)},
                    "bus": catch["bus"] if catch else None, "bus_in_min": wait_until, "bus_timing": timing,
                    "ride_min": max(1, round(ride)), "ride_km": round(ride_m / 1000, 1), "ride_timing": ride_src,
                    "stops_on_ride": (j - i - 1) if j > i else (len(r["stops"]) - i - 1 + j),
                    "long_way_around": ride_m > max(2500.0, 2.5 * direct_m),
                    "total_min": total, "arrive_at": (now + timedelta(minutes=total)).strftime("%I:%M %p").lstrip("0"),
                    "path": [[stops[r["stops"][i]]["lat"], stops[r["stops"][i]]["lng"]], *segment(r, geo, i, j),
                             [stops[r["stops"][j]]["lat"], stops[r["stops"][j]]["lng"]]],
                })
    # Best per route, then fastest first.
    best: dict[int, dict[str, Any]] = {}
    for o in options:
        if o["route_id"] not in best or o["total_min"] < best[o["route_id"]]["total_min"]:
            best[o["route_id"]] = o
    ranked = sorted(best.values(), key=lambda o: (o["total_min"], o["board"]["walk_min"]))
    result["options"] = ranked[:3]
    if not ranked:
        result["recommend"] = "walk" if walking <= 20 else "none"
    else:
        result["recommend"] = "walk" if walking <= ranked[0]["total_min"] + 2 else "shuttle"
    return result


def _meters(a: dict[str, Any], b: dict[str, Any]) -> float:
    return meters_between(a["lat"], a["lng"], b["lat"], b["lng"])


def options(origin: dict[str, Any], dest: dict[str, Any]) -> dict[str, Any]:
    """Compact plan for the Concierge's `shuttle_options` tool (no map geometry)."""
    p = plan(origin, dest)
    if p.get("error"):
        return {"error": p["error"]}
    return {
        "walk_only_min": p["walk_only_min"], "recommend": p.get("recommend"),
        "options": [{k: o[k] for k in ("route", "bus_in_min", "ride_min", "stops_on_ride", "long_way_around", "total_min", "arrive_at")}
                    | {"board_at": o["board"]["name"], "walk_to_stop_min": o["board"]["walk_min"],
                       "get_off_at": o["alight"]["name"], "walk_from_stop_min": o["alight"]["walk_min"]} for o in p["options"]],
        "not_running_now": p.get("not_running_now", []),
        "announcements": p["announcements"],
        "note": "Live from Yale's shuttle system. Members can plan this trip on the map in Resources > Yale Shuttle.",
    }
