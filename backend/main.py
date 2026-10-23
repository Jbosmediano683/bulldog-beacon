"""Bulldog Beacon API + web app.

Run from the repo root with `python run.py` (or
`uvicorn main:app --app-dir backend --port 8000`). The built front end in
backend/static is served from the same origin, so there is one process to start.
"""

import asyncio
import sqlite3
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any, Iterator

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import auth
import bluephones
import events
import services
import shuttle
from config import (GLOBAL_DAILY_TOKEN_CAP, MODEL_NAME, PRICE_PER_MTOK, PRICE_SOURCE, STATIC_DIR,
                    USER_DAILY_TOKEN_CAP, env_file_used)
from db import connect, dumps, iso, loads, now_iso, now_utc, one, rows
from models import (ChatBody, CommentBody, EscortBody, LoginBody, PostBody, ProfileBody, ReactBody, SosBody, SosNoteBody,
                    WalkBody)
from safety import tokens_today
from seed import seed


async def _walk_watcher() -> None:
    while True:
        conn = connect()
        try:
            services.check_walks(conn)
        except Exception as exc:  # keep the watcher alive
            print("walk watcher:", exc)
        finally:
            conn.close()
        await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(_: FastAPI):
    conn = connect()
    seed(conn)
    conn.close()
    task = asyncio.create_task(_walk_watcher())
    yield
    task.cancel()


app = FastAPI(title="Bulldog Beacon", lifespan=lifespan)


# ------------------------------------------------------------- dependencies

def get_conn() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def current_user(request: Request, conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    user = auth.user_for_token(conn, request.cookies.get(auth.COOKIE))
    if not user:
        raise HTTPException(401, "Sign in with your NetID.")
    return user


def dispatcher(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    if user["role"] != "dispatcher":
        raise HTTPException(403, "Dispatch console only.")
    return user


# -------------------------------------------------------------------- auth

@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "model": MODEL_NAME, "env_file": env_file_used()}


@app.post("/api/auth/login")
def login(body: LoginBody, response: Response, conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    netid = body.netid.strip().lower()
    if not auth.valid_netid(netid):
        raise HTTPException(400, "That doesn't look like a Yale NetID (letters then numbers, e.g. abc123).")
    user = one(conn, "SELECT * FROM users WHERE netid = ?", (netid,))
    if user:
        if not auth.verify_password(body.password, user["password_hash"]):
            raise HTTPException(401, "NetID or password is incorrect.")
    else:
        # Mock CAS: the first sign-in for a new NetID creates the account.
        if not body.name or len(body.password) < 8:
            raise HTTPException(404, "new_netid")
        cur = conn.execute(
            "INSERT INTO users (netid, name, affiliation, unit, role, password_hash, created_at) VALUES (?,?,?,?,?,?,?)",
            (netid, body.name.strip()[:60], body.affiliation or "student", "", "member",
             auth.hash_password(body.password), now_iso()))
        conn.commit()
        user = one(conn, "SELECT * FROM users WHERE id = ?", (cur.lastrowid,))
    assert user is not None
    token = auth.create_session(conn, user["id"])
    response.set_cookie(auth.COOKIE, token, httponly=True, samesite="lax", max_age=auth.SESSION_DAYS * 86400)
    return auth.public_user(user)


@app.post("/api/auth/logout")
def logout(request: Request, response: Response, conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, bool]:
    token = request.cookies.get(auth.COOKIE)
    if token:
        auth.end_session(conn, token)
    response.delete_cookie(auth.COOKIE)
    return {"ok": True}


@app.get("/api/auth/me")
def me(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    return auth.public_user(user)


@app.put("/api/profile")
def update_profile(body: ProfileBody, user: dict[str, Any] = Depends(current_user),
                   conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    contacts = [{"name": c.get("name", "")[:40], "phone": c.get("phone", "")[:20]} for c in body.contacts if c.get("name")]
    conn.execute("UPDATE users SET contacts_json = ?, medical_note = ? WHERE id = ?",
                 (dumps(contacts), body.medical_note.strip(), user["id"]))
    conn.commit()
    return auth.public_user(one(conn, "SELECT * FROM users WHERE id = ?", (user["id"],)) or user)


# ------------------------------------------------------------ public data

@app.get("/api/places")
def places(_: dict = Depends(current_user), conn: sqlite3.Connection = Depends(get_conn)) -> list[dict[str, Any]]:
    return [{**p, "aliases": loads(p.pop("aliases_json"), [])} for p in rows(conn.execute("SELECT * FROM places ORDER BY name"))]


@app.get("/api/resources")
def resources(_: dict = Depends(current_user), conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    from agents.concierge import services_status
    from config import TZ
    return {"resources": rows(conn.execute("SELECT * FROM resources ORDER BY id")),
            "status": services_status(conn, now_utc().astimezone(TZ))}


@app.get("/api/events")
def yale_events(hours: int = 12, _: dict = Depends(current_user)) -> dict[str, Any]:
    """Happening at Yale: real events from events.yale.edu (cached 15 minutes)."""
    return events.happening(max(1, min(hours, 36)))


@app.get("/api/blue-phones")
def blue_phones(_: dict = Depends(current_user)) -> dict[str, Any]:
    """Yale's blue emergency phones, traced from Yale's own blue-phone map."""
    return bluephones.load()


@app.get("/api/shuttle")
def shuttle_system(_: dict = Depends(current_user)) -> dict[str, Any]:
    """Yale Shuttle routes, stops, and service announcements (from Yale's real-time shuttle system)."""
    return shuttle.system()


@app.get("/api/shuttle/live")
def shuttle_live(_: dict = Depends(current_user)) -> dict[str, Any]:
    return shuttle.live()


@app.get("/api/shuttle/plan")
def shuttle_plan(dest_place_id: int, place_id: int | None = None, lat: float | None = None, lng: float | None = None,
                 _: dict = Depends(current_user), conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    """Fastest way to a Yale place from where you are: one shuttle ride or walking. Your location is the phone's GPS
    when it's in New Haven, otherwise the place you chose."""
    dest = services.place_by_id(conn, dest_place_id)
    if not dest:
        raise HTTPException(404, "Unknown destination.")
    start, s_lat, s_lng = services.resolve_location(conn, place_id, lat, lng)
    used_gps = lat is not None and (s_lat, s_lng) == (lat, lng)
    origin = {"lat": s_lat, "lng": s_lng, "name": "Your location" if used_gps else start["name"], "gps": used_gps}
    return {"origin": origin, "dest": {"id": dest["id"], "name": dest["name"], "lat": dest["lat"], "lng": dest["lng"]},
            **shuttle.plan(origin, dest)}


@app.get("/api/shuttle/eta")
def shuttle_eta(stop: int, _: dict = Depends(current_user)) -> list[dict[str, Any]]:
    return shuttle.etas(stop)


@app.get("/api/incidents")
def incidents(hours: int = 48, _: dict = Depends(current_user),
              conn: sqlite3.Connection = Depends(get_conn)) -> list[dict[str, Any]]:
    return services.incidents_feed(conn, max(1, min(hours, 24 * 14)))


# -------------------------------------------------------------------- posts

@app.post("/api/posts")
async def create_post(body: PostBody, tasks: BackgroundTasks, user: dict[str, Any] = Depends(current_user),
                      conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    result = await services.submit_post(conn, user, body)
    if result["published"]:
        tasks.add_task(services.attach_to_incident, result["post"]["id"])
    return result


@app.get("/api/posts/mine")
def my_posts(user: dict[str, Any] = Depends(current_user), conn: sqlite3.Connection = Depends(get_conn)) -> list[dict[str, Any]]:
    return [services.post_view(p, include_private=True)
            for p in rows(conn.execute("SELECT * FROM posts WHERE user_id = ? AND demo = 0 ORDER BY id DESC LIMIT 30",
                                       (user["id"],)))]


@app.get("/api/posts/{post_id}")
def get_post(post_id: int, user: dict[str, Any] = Depends(current_user),
             conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    p = one(conn, "SELECT * FROM posts WHERE id = ?", (post_id,))
    if not p or (p["user_id"] != user["id"] and p["status"] not in ("published", "revised")):
        raise HTTPException(404, "No such post.")
    return services.post_view(p, include_private=p["user_id"] == user["id"])


# ---------------------------------------------------------------- community

@app.get("/api/community")
def community(show: str = "all", user: dict[str, Any] = Depends(current_user),
              conn: sqlite3.Connection = Depends(get_conn)) -> list[dict[str, Any]]:
    return services.community_feed(conn, user, show if show in ("all", "alerts", "good") else "all")


@app.post("/api/posts/{post_id}/react")
def react(post_id: int, body: ReactBody, user: dict[str, Any] = Depends(current_user),
          conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    return services.toggle_reaction(conn, user, post_id, body.kind)


@app.get("/api/posts/{post_id}/comments")
def get_comments(post_id: int, user: dict[str, Any] = Depends(current_user),
                 conn: sqlite3.Connection = Depends(get_conn)) -> list[dict[str, Any]]:
    return services.comments_for(conn, user, post_id)


@app.post("/api/posts/{post_id}/comments")
async def add_comment(post_id: int, body: CommentBody, user: dict[str, Any] = Depends(current_user),
                      conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    return await services.submit_comment(conn, user, post_id, body.text)


# --------------------------------------------------------------------- chat

@app.post("/api/chat")
async def chat(body: ChatBody, user: dict[str, Any] = Depends(current_user),
               conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    return await services.chat_turn(conn, user, body)


@app.get("/api/chat/history")
def chat_history(user: dict[str, Any] = Depends(current_user), conn: sqlite3.Connection = Depends(get_conn)) -> list[dict[str, Any]]:
    return services.chat_history(conn, user["id"])


@app.delete("/api/chat/history")
def clear_chat(user: dict[str, Any] = Depends(current_user), conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, bool]:
    conn.execute("DELETE FROM chat_messages WHERE user_id = ?", (user["id"],))
    conn.commit()
    return {"ok": True}


# ---------------------------------------------------------------------- SOS

@app.post("/api/sos")
def sos(body: SosBody, user: dict[str, Any] = Depends(current_user),
        conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    return services.trigger_sos(conn, user, body)


@app.post("/api/sos/{sos_id}/note")
def sos_note(sos_id: int, body: SosNoteBody, tasks: BackgroundTasks, user: dict[str, Any] = Depends(current_user),
             conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    result = services.add_sos_note(conn, user, sos_id, body.note)
    if result["note"]:
        tasks.add_task(services.write_sos_brief, sos_id)
    return result


@app.post("/api/sos/{sos_id}/safe")
def sos_safe(sos_id: int, user: dict[str, Any] = Depends(current_user),
             conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    if not one(conn, "SELECT id FROM sos_events WHERE id = ? AND user_id = ?", (sos_id, user["id"])):
        raise HTTPException(404, "No such SOS.")
    return services.set_sos_status(conn, sos_id, "cancelled", user["name"])


@app.get("/api/sos/{sos_id}")
def sos_get(sos_id: int, user: dict[str, Any] = Depends(current_user),
            conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    s = one(conn, "SELECT * FROM sos_events WHERE id = ?", (sos_id,))
    if not s or (s["user_id"] != user["id"] and user["role"] != "dispatcher"):
        raise HTTPException(404, "No such SOS.")
    return services.sos_view(s)


# -------------------------------------------------------------------- walks

@app.post("/api/walks")
def walk_start(body: WalkBody, user: dict[str, Any] = Depends(current_user),
               conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    return services.start_walk(conn, user, body)


@app.get("/api/walks/active")
def walk_active(user: dict[str, Any] = Depends(current_user), conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any] | None:
    w = one(conn, "SELECT * FROM walks WHERE user_id = ? AND status IN ('active','overdue','escalated') "
                  "ORDER BY id DESC LIMIT 1", (user["id"],))
    return services.walk_view(conn, w) if w else None


@app.post("/api/walks/{walk_id}/arrived")
def walk_arrived(walk_id: int, user: dict[str, Any] = Depends(current_user),
                 conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    return services.end_walk(conn, user, walk_id, "arrived")


@app.post("/api/walks/{walk_id}/cancel")
def walk_cancel(walk_id: int, user: dict[str, Any] = Depends(current_user),
                conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    return services.end_walk(conn, user, walk_id, "cancelled")


@app.post("/api/escorts")
def escort(body: EscortBody, user: dict[str, Any] = Depends(current_user),
           conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    if not (services.place_by_id(conn, body.from_place_id) and services.place_by_id(conn, body.to_place_id)):
        raise HTTPException(400, "Pick both places.")
    cur = conn.execute("INSERT INTO escort_requests (user_id, from_place_id, to_place_id, created_at) VALUES (?,?,?,?)",
                       (user["id"], body.from_place_id, body.to_place_id, now_iso()))
    conn.commit()
    return {"id": cur.lastrowid, "status": "requested",
            "note": "Beacon can't reach Yale Security directly yet. Call (203) 785-5555 to confirm your escort."}


# ----------------------------------------------------------------- dispatch

@app.get("/api/dispatch")
def dispatch_board(_: dict = Depends(dispatcher), conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    since = iso(now_utc() - timedelta(hours=24))
    users = {u["id"]: u for u in rows(conn.execute("SELECT id, netid, name, affiliation, unit FROM users"))}
    sos_list = [{**services.sos_view(s), "caller": users.get(s["user_id"])}
                for s in rows(conn.execute("SELECT * FROM sos_events WHERE created_at >= ? ORDER BY id DESC", (since,)))]
    walks = [{**services.walk_view(conn, w), "walker": users.get(w["user_id"])}
             for w in rows(conn.execute("SELECT * FROM walks WHERE started_at >= ? ORDER BY id DESC LIMIT 30", (since,)))]
    escorts = rows(conn.execute(
        "SELECT e.*, a.name AS from_name, b.name AS to_name, u.name AS user_name FROM escort_requests e "
        "JOIN places a ON a.id = e.from_place_id JOIN places b ON b.id = e.to_place_id JOIN users u ON u.id = e.user_id "
        "WHERE e.created_at >= ? ORDER BY e.id DESC LIMIT 20", (since,)))
    return {"sos": sos_list, "walks": walks, "escorts": escorts}


@app.post("/api/dispatch/sos/{sos_id}/{action}")
def dispatch_sos(sos_id: int, action: str, user: dict[str, Any] = Depends(dispatcher),
                 conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    status = {"ack": "acknowledged", "resolve": "resolved"}.get(action)
    if not status:
        raise HTTPException(400, "Unknown action.")
    return services.set_sos_status(conn, sos_id, status, user["name"])


# -------------------------------------------------------- usage and safety

@app.get("/api/usage")
def usage(user: dict[str, Any] = Depends(current_user), conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    by_agent = rows(conn.execute(
        "SELECT agent, COUNT(*) AS runs, AVG(requests) AS avg_requests, AVG(tool_calls) AS avg_tool_calls, "
        "AVG(input_tokens) AS avg_input, AVG(cached_tokens) AS avg_cached, AVG(output_tokens) AS avg_output, "
        "AVG(reasoning_tokens) AS avg_reasoning, AVG(latency_ms) AS avg_latency_ms, AVG(cost_usd) AS avg_cost, "
        "SUM(cost_usd) AS total_cost, SUM(input_tokens) AS total_input, SUM(cached_tokens) AS total_cached, "
        "SUM(output_tokens) AS total_output, SUM(gateway_cache_hits) AS gateway_hits "
        "FROM ai_runs WHERE status = 'ok' GROUP BY agent ORDER BY agent"))
    mine = rows(conn.execute(
        "SELECT id, created_at, agent, ref, status, requests, tool_calls, input_tokens, cached_tokens, output_tokens, "
        "reasoning_tokens, latency_ms, cost_usd, gateway_cache_hits FROM ai_runs WHERE user_id = ? ORDER BY id DESC LIMIT 25",
        (user["id"],)))
    totals = one(conn, "SELECT COUNT(*) AS runs, COALESCE(SUM(cost_usd),0) AS cost, "
                       "COALESCE(SUM(input_tokens),0) AS input, COALESCE(SUM(cached_tokens),0) AS cached, "
                       "COALESCE(SUM(output_tokens),0) AS output FROM ai_runs") or {}
    statuses = rows(conn.execute("SELECT status, COUNT(*) AS n FROM ai_runs GROUP BY status"))
    return {"model": MODEL_NAME, "prices_per_million": PRICE_PER_MTOK, "price_source": PRICE_SOURCE,
            "my_tokens_today": tokens_today(conn, user["id"]), "my_daily_cap": USER_DAILY_TOKEN_CAP,
            "app_tokens_today": tokens_today(conn), "app_daily_cap": GLOBAL_DAILY_TOKEN_CAP,
            "by_agent": by_agent, "my_runs": mine, "totals": totals, "statuses": statuses}


@app.get("/api/runs/{run_id}")
def run_detail(run_id: int, user: dict[str, Any] = Depends(current_user),
               conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    r = one(conn, "SELECT * FROM ai_runs WHERE id = ?", (run_id,))
    if not r or (r["user_id"] != user["id"] and user["role"] != "dispatcher"):
        raise HTTPException(404, "No such run.")
    r["trace"] = loads(r.pop("trace_json"), [])
    return r


@app.get("/api/safety/events")
def safety_events(user: dict[str, Any] = Depends(current_user), conn: sqlite3.Connection = Depends(get_conn)) -> list[dict[str, Any]]:
    if user["role"] == "dispatcher":
        return rows(conn.execute("SELECT * FROM safety_events ORDER BY id DESC LIMIT 60"))
    return rows(conn.execute("SELECT * FROM safety_events WHERE user_id = ? ORDER BY id DESC LIMIT 30", (user["id"],)))


@app.post("/api/admin/reset-demo")
def reset_demo(_: dict = Depends(dispatcher), conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, bool]:
    """Re-seed demo data so the fictional reports are fresh again (keeps AI usage logs)."""
    runs = rows(conn.execute("SELECT * FROM ai_runs"))
    events = rows(conn.execute("SELECT * FROM safety_events"))
    seed(conn, reset=True)
    for table, data in (("ai_runs", runs), ("safety_events", events)):
        for r in data:
            r["user_id"] = None  # accounts are re-created, so old ids would point at the wrong person
            cols = ",".join(r.keys())
            conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({','.join('?' * len(r))})", tuple(r.values()))
    conn.commit()
    return {"ok": True}


# ------------------------------------------------------------- the web app

@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


if (STATIC_DIR / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str) -> Any:
    if path.startswith("api/"):
        raise HTTPException(404, "Not found")
    file = STATIC_DIR / path
    if path and file.is_file() and STATIC_DIR in file.resolve().parents:
        return FileResponse(file)
    index = STATIC_DIR / "index.html"
    if index.is_file():
        return FileResponse(index)
    return JSONResponse({"detail": "Front end not built. Run `npm run build` in frontend/."}, status_code=503)
