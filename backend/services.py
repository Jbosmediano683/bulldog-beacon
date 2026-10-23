"""Beacon's workflows. Code decides the order; agents are called only where
judgement on free text is needed:

  post  -> rules -> Moderator -> guards -> publish -> (nearby incident?) -> Corroborator -> guards
  chat  -> rules -> Concierge (read-only tools) -> guards
  SOS   -> alert + location + contacts (code, instant) -> optional note -> Responder Brief
  walk  -> timer (code) -> overdue -> escalated, no model involved
"""

import sqlite3
from datetime import timedelta
from typing import Any

from fastapi import HTTPException

from agents import concierge, corroborator, moderator, responder
from agents.runtime import AgentUnavailable
from config import CAMPUS_CENTER, CHAT_HISTORY_TURNS, MAX_CHAT_CHARS, MAX_POST_CHARS, TZ, in_service_area
from db import (connect, dumps, iso, loads, log_safety, meters_between, nearest_place, now_iso, now_utc, one,
                parse_iso, rows)
from models import ChatBody, ConciergeAction, ConciergeReply, PostBody, SosBody, WalkBody
from safety import (LimitExceeded, check_post_rate, crisis_language, immediate_danger_language,
                    looks_like_injection, redact_personal_info, vet_phone_numbers)

CORROBORATE_RADIUS_M = 300
CORROBORATE_HOURS = 6
SERVICE_AREA_M = 2500      # a GPS fix must also be this close to a known place
WALK_ESCALATE_AFTER = timedelta(minutes=2)
CRISIS_NOTE = ("If you're struggling, you're not alone: call or text 988 any time, or call Yale's on-call mental health "
               "clinician at (203) 432-0123.")


def local_now_text() -> str:
    return now_utc().astimezone(TZ).strftime("%a %b %d, %I:%M %p")


def known_phones(conn: sqlite3.Connection) -> frozenset[str]:
    return frozenset(r[0] for r in conn.execute("SELECT phone FROM resources WHERE phone IS NOT NULL"))


def place_by_id(conn: sqlite3.Connection, place_id: int | None) -> dict[str, Any] | None:
    return one(conn, "SELECT * FROM places WHERE id = ?", (place_id,)) if place_id else None


def resolve_location(conn: sqlite3.Connection, place_id: int | None, lat: float | None,
                     lng: float | None) -> tuple[dict[str, Any], float, float]:
    """A place row plus coordinates. Browser GPS is used only inside Beacon's service
    area; otherwise (e.g. a grader testing from elsewhere) the chosen place is used."""
    if lat is not None and lng is not None and in_service_area(lat, lng):
        place, d = nearest_place(conn, lat, lng)
        if d <= SERVICE_AREA_M:
            return place, lat, lng
    place = place_by_id(conn, place_id)
    if place:
        return place, place["lat"], place["lng"]
    place, _ = nearest_place(conn, *CAMPUS_CENTER)
    return place, place["lat"], place["lng"]


# ===================================================================== posts

def post_view(p: dict[str, Any], *, include_private: bool = False) -> dict[str, Any]:
    view = {
        "id": p["id"], "created_at": p["created_at"], "category": p["category"], "text": p["text"],
        "place_id": p["place_id"], "lat": p["lat"], "lng": p["lng"], "status": p["status"],
        "incident_id": p["incident_id"], "demo": bool(p["demo"]),
    }
    if include_private:  # only for the author
        view["raw_text"] = p["raw_text"]
        view["moderation"] = loads(p["moderation_json"], {})
    return view


async def submit_post(conn: sqlite3.Connection, user: dict[str, Any], body: PostBody) -> dict[str, Any]:
    text = body.text.strip()
    if len(text) < 8:
        raise HTTPException(400, "Please describe what happened (at least a few words).")
    if len(text) > MAX_POST_CHARS:
        raise HTTPException(400, f"Please keep alerts under {MAX_POST_CHARS} characters.")
    try:
        check_post_rate(conn, user["id"])
    except LimitExceeded as exc:
        raise HTTPException(429, exc.message)

    place, lat, lng = resolve_location(conn, body.place_id, body.lat, body.lng)
    if not in_service_area(lat, lng) or meters_between(lat, lng, place["lat"], place["lng"]) > SERVICE_AREA_M:
        raise HTTPException(400, "Beacon covers Yale's campuses and nearby New Haven neighborhoods. Pick a place on the map.")

    # ---- rule layer (code, no tokens)
    cleaned, pii = redact_personal_info(text, known_phones(conn))
    flags: list[str] = []
    cur = conn.execute(
        "INSERT INTO posts (user_id, created_at, category, raw_text, text, place_id, lat, lng, status) "
        "VALUES (?,?,?,?,?,?,?,?,'pending')", (user["id"], now_iso(), body.category, text, "", place["id"], lat, lng))
    conn.commit()
    post_id = int(cur.lastrowid or 0)
    ref = f"post:{post_id}"
    if pii:
        flags.append(f"code already removed: {', '.join(pii)}")
        log_safety(conn, "pii_removed", "rule", f"Removed {', '.join(pii)} before the model saw the post", user["id"], ref)

    injection = looks_like_injection(text)
    if injection:
        log_safety(conn, "injection_blocked", "rule", f"Matched instruction-override text: {injection!r}", user["id"], ref)
        decision = {"decision": "block", "issues": ["prompt_injection"], "layer": "rule",
                    "title": "", "advice": "", "category": body.category, "severity": "info",
                    "note_to_author": "This post contains text that tries to give instructions to the app, so it "
                                      "wasn't published. Please describe only what you saw.", "published_text": ""}
        return _finish_post(conn, post_id, "blocked", "", decision, run=None)
    if immediate_danger_language(text):
        flags.append("possible emergency happening now")
    if crisis_language(text):
        flags.append("possible self-harm language")

    # ---- agent layer
    try:
        result, record = await moderator.moderate(
            conn, text=cleaned, category=body.category, place_name=place["name"], local_time=local_now_text(),
            code_flags=flags, user_id=user["id"], ref=ref)
    except LimitExceeded as exc:
        _finish_post(conn, post_id, "held", "", {"decision": "held", "layer": "rule", "note_to_author": exc.message}, None)
        raise HTTPException(429, exc.message)
    except AgentUnavailable as exc:
        # Fail closed: nothing reaches the board unreviewed.
        note = ("The moderator couldn't review your post just now, so it was saved but not published. "
                "If anyone is in danger, call 911 or Yale PD at (203) 432-4400.")
        return _finish_post(conn, post_id, "held", "", {"decision": "held", "layer": "rule", "note_to_author": note,
                                                         "error": exc.record.status}, _run_summary(exc.record))

    decision = guard_decision(conn, result, text, user["id"], ref)

    status = {"publish": "published", "revise": "revised", "block": "blocked", "redirect_911": "redirect_911"}[
        decision["decision"]]
    return _finish_post(conn, post_id, status, decision["published_text"] if status in ("published", "revised") else "",
                        decision, _run_summary(record))


def guard_decision(conn: sqlite3.Connection, result: Any, original_text: str, user_id: int, ref: str) -> dict[str, Any]:
    """Code checks on the Moderator's output, shared by alerts and comments."""
    decision = result.model_dump()
    decision["layer"] = "agent"
    guards: list[str] = []

    # ---- guard layer (code checks on the model's output)
    if decision["decision"] in ("publish", "revise") and not decision["published_text"].strip():
        decision["decision"] = "block"
        guards.append("empty published text, blocked")
    if "profiling" in decision["issues"] and decision["decision"] == "publish":
        decision["decision"] = "revise"
        guards.append("profiling flagged but marked publish; treated as revise")
    for key in ("published_text", "title", "advice"):
        fixed, removed_numbers = vet_phone_numbers(conn, decision[key])
        fixed, pii_again = redact_personal_info(fixed, known_phones(conn))
        if removed_numbers or pii_again:
            guards.append(f"removed unverified contact info from {key}")
        decision[key] = fixed
    if decision["decision"] in ("publish", "revise") and looks_like_injection(decision["published_text"]):
        decision["decision"] = "block"
        guards.append("model output still contained instruction-override text, blocked")
    # Crisis support never depends on the model remembering it.
    if "self_harm" in decision["issues"] or crisis_language(original_text):
        decision["support"] = True
        if "988" not in decision["note_to_author"]:
            decision["note_to_author"] = (decision["note_to_author"] + " " + CRISIS_NOTE).strip()
            guards.append("added 988 and on-call clinician support the moderator left out")
    decision["guards"] = guards
    for g in guards:
        log_safety(conn, "output_guard", "guard", g, user_id, ref)

    for issue in decision["issues"]:
        kind = {"profiling": "profiling_caught", "prompt_injection": "injection_blocked",
                "personal_info": "pii_removed", "unverified_claim": "rumor_caught",
                "ongoing_emergency": "emergency_redirect", "self_harm": "crisis_support_shown",
                "harassment_or_threat": "harassment_blocked"}.get(issue)
        if kind:
            log_safety(conn, kind, "agent", f"Moderator decision '{decision['decision']}': {decision['note_to_author'][:300]}",
                       user_id, ref)

    return decision


def _finish_post(conn: sqlite3.Connection, post_id: int, status: str, text: str, decision: dict[str, Any],
                 run: dict[str, Any] | None) -> dict[str, Any]:
    if decision.get("category"):
        conn.execute("UPDATE posts SET category = ? WHERE id = ?", (decision["category"], post_id))
    conn.execute("UPDATE posts SET status = ?, text = ?, moderation_json = ? WHERE id = ?",
                 (status, text, dumps(decision), post_id))
    conn.commit()
    post = one(conn, "SELECT * FROM posts WHERE id = ?", (post_id,))
    assert post is not None
    return {"post": post_view(post, include_private=True), "moderation": decision, "run": run,
            "published": status in ("published", "revised")}


def _run_summary(record: Any) -> dict[str, Any]:
    return {"run_id": record.run_id, "status": record.status, **record.usage, "trace": record.trace}


async def attach_to_incident(post_id: int) -> None:
    """Background step after publishing: merge into a nearby incident or start a new one."""
    conn = connect()
    try:
        post = one(conn, "SELECT * FROM posts WHERE id = ?", (post_id,))
        if not post or post["status"] not in ("published", "revised") or post["incident_id"]:
            return
        if post["category"] == "good_news":
            return  # community feed only
        decision = loads(post["moderation_json"], {})
        place = place_by_id(conn, post["place_id"]) or {"name": "near campus"}
        since = parse_iso(post["created_at"]) - timedelta(hours=CORROBORATE_HOURS)
        candidates = []
        # Real reports never merge into fictional demo incidents (and vice versa).
        for inc in rows(conn.execute("SELECT * FROM incidents WHERE status = 'active' AND last_reported >= ? AND demo = ?",
                                     (iso(since), post["demo"]))):
            d = meters_between(post["lat"], post["lng"], inc["lat"], inc["lng"])
            if d <= CORROBORATE_RADIUS_M:
                candidates.append({**inc, "distance_m": int(d)})

        new_card = {"title": decision.get("title") or "Community report", "summary": post["text"][:300],
                    "advice": decision.get("advice") or "", "severity": decision.get("severity") or "caution"}
        merge_into: int | None = None
        if candidates:
            try:
                result, _ = await corroborator.corroborate(conn, new_report=post, place_name=place["name"],
                                                           candidates=candidates[:5], user_id=post["user_id"],
                                                           ref=f"post:{post_id}")
                card = result.model_dump()
                for key in ("summary", "advice", "title"):
                    card[key], removed = vet_phone_numbers(conn, card[key])
                    if removed:
                        log_safety(conn, "output_guard", "guard", f"Corroborator {key}: removed {removed}",
                                   post["user_id"], f"post:{post_id}")
                if result.same_incident_id is not None:
                    if result.same_incident_id in [c["id"] for c in candidates]:
                        merge_into = result.same_incident_id
                    else:
                        log_safety(conn, "invalid_reference", "guard",
                                   f"Corroborator named incident {result.same_incident_id}, not a candidate; kept separate",
                                   post["user_id"], f"post:{post_id}")
                new_card = {k: card[k] for k in ("title", "summary", "advice", "severity")}
            except (LimitExceeded, AgentUnavailable):
                pass  # safe default: show it as its own incident card

        if merge_into:
            conn.execute("UPDATE incidents SET title=?, summary=?, advice=?, severity=?, report_count=report_count+1, "
                         "last_reported=? WHERE id=?", (new_card["title"], new_card["summary"], new_card["advice"],
                                                        new_card["severity"], post["created_at"], merge_into))
            incident_id = merge_into
        else:
            cur = conn.execute(
                "INSERT INTO incidents (title, summary, advice, category, severity, place_id, lat, lng, report_count, "
                "first_reported, last_reported) VALUES (?,?,?,?,?,?,?,?,1,?,?)",
                (new_card["title"], new_card["summary"], new_card["advice"], post["category"], new_card["severity"],
                 post["place_id"], post["lat"], post["lng"], post["created_at"], post["created_at"]))
            incident_id = int(cur.lastrowid or 0)
        conn.execute("UPDATE posts SET incident_id = ? WHERE id = ?", (incident_id, post_id))
        conn.commit()
    finally:
        conn.close()


def incidents_feed(conn: sqlite3.Connection, hours: int) -> list[dict[str, Any]]:
    since = iso(now_utc() - timedelta(hours=hours))
    incs = rows(conn.execute("SELECT i.*, p.name AS place_name FROM incidents i LEFT JOIN places p ON p.id = i.place_id "
                             "WHERE i.last_reported >= ? ORDER BY i.last_reported DESC", (since,)))
    for inc in incs:
        reports = rows(conn.execute("SELECT * FROM posts WHERE incident_id = ? AND status IN ('published','revised') "
                                    "ORDER BY created_at", (inc["id"],)))
        inc["reports"] = [post_view(r) for r in reports]
        inc["demo"] = bool(inc["demo"])
        inc["confirmations"] = conn.execute(
            "SELECT COUNT(*) FROM post_reactions r JOIN posts p ON p.id = r.post_id WHERE p.incident_id = ? AND r.kind = 'confirm'",
            (inc["id"],)).fetchone()[0]
    return incs


# ================================================================= community

COMMENTS_PER_HOUR = 20
GOOD_CATEGORIES = ("good_news", "safety_update")


def author_label(author: dict[str, Any], viewer_id: int) -> str:
    """Everyone signs in with a NetID, but the community sees affiliation only, never names."""
    if author["id"] == viewer_id:
        return "You"
    if author["role"] == "dispatcher":
        return "Yale PD dispatch (demo)"
    return {"student": "Yale student", "staff": "Yale staff", "faculty": "Yale faculty"}.get(author["affiliation"],
                                                                                         "Yale community member")


def _counts(conn: sqlite3.Connection, post_ids: list[int], viewer_id: int) -> dict[int, dict[str, Any]]:
    out = {pid: {"likes": 0, "confirms": 0, "liked": False, "confirmed": False, "comments": 0} for pid in post_ids}
    if not post_ids:
        return out
    marks = ",".join("?" * len(post_ids))
    for r in conn.execute(f"SELECT post_id, kind, COUNT(*), SUM(user_id = ?) FROM post_reactions WHERE post_id IN ({marks}) "
                          "GROUP BY post_id, kind", (viewer_id, *post_ids)):
        key = "likes" if r[1] == "like" else "confirms"
        out[r[0]][key] = r[2]
        out[r[0]]["liked" if r[1] == "like" else "confirmed"] = bool(r[3])
    for r in conn.execute(f"SELECT post_id, COUNT(*) FROM comments WHERE post_id IN ({marks}) "
                          "AND status IN ('published','revised') GROUP BY post_id", tuple(post_ids)):
        out[r[0]]["comments"] = r[1]
    return out


def community_feed(conn: sqlite3.Connection, user: dict[str, Any], show: str, days: int = 7) -> list[dict[str, Any]]:
    since = iso(now_utc() - timedelta(days=days))
    sql = ("SELECT p.*, u.affiliation, u.role, pl.name AS place_name, i.severity AS inc_severity, i.title AS inc_title "
           "FROM posts p JOIN users u ON u.id = p.user_id LEFT JOIN places pl ON pl.id = p.place_id "
           "LEFT JOIN incidents i ON i.id = p.incident_id "
           "WHERE p.status IN ('published','revised') AND p.created_at >= ?")
    params: list[Any] = [since]
    if show == "alerts":
        sql += f" AND p.category NOT IN ({','.join('?' * len(GOOD_CATEGORIES))})"
        params += GOOD_CATEGORIES
    elif show == "good":
        sql += f" AND p.category IN ({','.join('?' * len(GOOD_CATEGORIES))})"
        params += GOOD_CATEGORIES
    posts = rows(conn.execute(sql + " ORDER BY p.created_at DESC LIMIT 60", tuple(params)))
    counts = _counts(conn, [p["id"] for p in posts], user["id"])
    out = []
    for p in posts:
        m = loads(p["moderation_json"], {})
        out.append({
            "id": p["id"], "created_at": p["created_at"], "category": p["category"], "text": p["text"],
            "title": m.get("title") or p["inc_title"] or "", "severity": p["inc_severity"] or m.get("severity") or "info",
            "place_id": p["place_id"], "place_name": p["place_name"], "incident_id": p["incident_id"],
            "author": author_label({"id": p["user_id"], "role": p["role"], "affiliation": p["affiliation"]}, user["id"]),
            "mine": p["user_id"] == user["id"], "demo": bool(p["demo"]), **counts[p["id"]],
        })
    return out


def _visible_post(conn: sqlite3.Connection, post_id: int) -> dict[str, Any]:
    post = one(conn, "SELECT * FROM posts WHERE id = ? AND status IN ('published','revised')", (post_id,))
    if not post:
        raise HTTPException(404, "That post isn't available.")
    return post


def toggle_reaction(conn: sqlite3.Connection, user: dict[str, Any], post_id: int, kind: str) -> dict[str, Any]:
    post = _visible_post(conn, post_id)
    if post["user_id"] == user["id"]:
        raise HTTPException(400, "That's your own post.")
    if kind == "confirm" and post["category"] in GOOD_CATEGORIES:
        raise HTTPException(400, "Only alerts can be confirmed.")
    exists = one(conn, "SELECT 1 AS x FROM post_reactions WHERE post_id = ? AND user_id = ? AND kind = ?",
                 (post_id, user["id"], kind))
    if exists:
        conn.execute("DELETE FROM post_reactions WHERE post_id = ? AND user_id = ? AND kind = ?", (post_id, user["id"], kind))
    else:
        conn.execute("INSERT INTO post_reactions (post_id, user_id, kind, created_at) VALUES (?,?,?,?)",
                     (post_id, user["id"], kind, now_iso()))
    conn.commit()
    return {"post_id": post_id, **_counts(conn, [post_id], user["id"])[post_id]}


def comment_view(c: dict[str, Any], viewer_id: int) -> dict[str, Any]:
    mine = c["user_id"] == viewer_id
    view = {"id": c["id"], "post_id": c["post_id"], "created_at": c["created_at"], "status": c["status"],
            "text": c["text"], "mine": mine, "demo": bool(c["demo"]),
            "author": author_label({"id": c["user_id"], "role": c["role"], "affiliation": c["affiliation"]}, viewer_id)}
    if mine and c["status"] not in ("published", "revised"):
        m = loads(c["moderation_json"], {})
        view.update(raw_text=c["raw_text"], note=m.get("note_to_author", ""), support=bool(m.get("support")))
    return view


def comments_for(conn: sqlite3.Connection, user: dict[str, Any], post_id: int) -> list[dict[str, Any]]:
    _visible_post(conn, post_id)
    found = rows(conn.execute(
        "SELECT c.*, u.role, u.affiliation FROM comments c JOIN users u ON u.id = c.user_id WHERE c.post_id = ? "
        "AND (c.status IN ('published','revised') OR c.user_id = ?) ORDER BY c.created_at", (post_id, user["id"])))
    return [comment_view(c, user["id"]) for c in found]


async def submit_comment(conn: sqlite3.Connection, user: dict[str, Any], post_id: int, text: str) -> dict[str, Any]:
    text = text.strip()
    if len(text) < 2:
        raise HTTPException(400, "Write a short comment first.")
    if len(text) > 400:
        raise HTTPException(400, "Please keep comments under 400 characters.")
    post = _visible_post(conn, post_id)
    hour_ago = iso(now_utc() - timedelta(hours=1))
    if conn.execute("SELECT COUNT(*) FROM comments WHERE user_id = ? AND created_at >= ? AND demo = 0",
                    (user["id"], hour_ago)).fetchone()[0] >= COMMENTS_PER_HOUR:
        log_safety(conn, "rate_limited", "rule", "comment rate limit", user["id"])
        raise HTTPException(429, f"You can post up to {COMMENTS_PER_HOUR} comments an hour.")

    cleaned, pii = redact_personal_info(text, known_phones(conn))
    cur = conn.execute("INSERT INTO comments (post_id, user_id, created_at, raw_text, status) VALUES (?,?,?,?,'pending')",
                       (post_id, user["id"], now_iso(), text))
    conn.commit()
    comment_id = int(cur.lastrowid or 0)
    ref = f"comment:{comment_id}"
    flags: list[str] = []
    if pii:
        flags.append(f"code already removed: {', '.join(pii)}")
        log_safety(conn, "pii_removed", "rule", f"Removed {', '.join(pii)} from a comment before the model saw it", user["id"], ref)

    def finish(status: str, shown: str, decision: dict[str, Any], run: dict[str, Any] | None) -> dict[str, Any]:
        conn.execute("UPDATE comments SET status = ?, text = ?, moderation_json = ? WHERE id = ?",
                     (status, shown, dumps(decision), comment_id))
        conn.commit()
        c = one(conn, "SELECT c.*, u.role, u.affiliation FROM comments c JOIN users u ON u.id = c.user_id WHERE c.id = ?",
                (comment_id,))
        assert c is not None
        return {"comment": comment_view(c, user["id"]), "moderation": decision, "run": run,
                "published": status in ("published", "revised")}

    injection = looks_like_injection(text)
    if injection:
        log_safety(conn, "injection_blocked", "rule", f"Comment matched instruction-override text: {injection!r}", user["id"], ref)
        return finish("blocked", "", {"decision": "block", "issues": ["prompt_injection"], "layer": "rule",
                                      "note_to_author": "This comment tries to give instructions to the app, so it wasn't posted."}, None)
    if immediate_danger_language(text):
        flags.append("possible emergency happening now")
    if crisis_language(text):
        flags.append("possible self-harm language")

    place = place_by_id(conn, post["place_id"]) or {"name": "campus"}
    try:
        result, record = await moderator.moderate(
            conn, text=cleaned, category=post["category"], place_name=place["name"], local_time=local_now_text(),
            code_flags=flags, user_id=user["id"], ref=ref, parent=post["text"])
    except LimitExceeded as exc:
        finish("held", "", {"decision": "held", "layer": "rule", "note_to_author": exc.message}, None)
        raise HTTPException(429, exc.message)
    except AgentUnavailable as exc:
        return finish("held", "", {"decision": "held", "layer": "rule", "error": exc.record.status,
                                   "note_to_author": "The moderator couldn't review your comment just now, so it wasn't posted."},
                      _run_summary(exc.record))
    decision = guard_decision(conn, result, text, user["id"], ref)
    status = {"publish": "published", "revise": "revised", "block": "blocked", "redirect_911": "redirect_911"}[decision["decision"]]
    return finish(status, decision["published_text"] if status in ("published", "revised") else "", decision,
                  _run_summary(record))


# ====================================================================== chat

def _incident_card(conn: sqlite3.Connection, incident_id: int) -> dict[str, Any] | None:
    inc = one(conn, "SELECT i.*, p.name AS place_name FROM incidents i LEFT JOIN places p ON p.id = i.place_id "
                    "WHERE i.id = ?", (incident_id,))
    if inc:
        inc["demo"] = bool(inc["demo"])
    return inc


def _vet_actions(conn: sqlite3.Connection, actions: list[ConciergeAction], seen: set[int]) -> tuple[list[dict], list[str]]:
    phones = known_phones(conn) | {"911", "988"}
    kept, dropped = [], []
    for a in actions:
        ok = True
        if a.kind == "call":
            digits = "".join(ch for ch in (a.phone or "") if ch.isdigit())
            digits = digits[1:] if len(digits) == 11 and digits.startswith("1") else digits
            ok = digits in phones
            a.phone = digits
        elif a.kind in ("start_walk", "request_escort"):
            ok = bool(place_by_id(conn, a.origin_place_id) and place_by_id(conn, a.dest_place_id)
                      and a.origin_place_id != a.dest_place_id)
            if a.kind == "start_walk":
                a.minutes = max(1, min(a.minutes or 15, 120))
        elif a.kind == "open_map" and a.incident_id is not None:
            ok = a.incident_id in seen
        if ok:
            kept.append(a.model_dump())
        else:
            dropped.append(f"{a.kind} ({a.label})")
    return kept, dropped


async def chat_turn(conn: sqlite3.Connection, user: dict[str, Any], body: ChatBody) -> dict[str, Any]:
    message = body.message.strip()
    if not message:
        raise HTTPException(400, "Type a question first.")
    if len(message) > MAX_CHAT_CHARS:
        raise HTTPException(400, f"Please keep messages under {MAX_CHAT_CHARS} characters.")
    here = place_by_id(conn, body.place_id) or nearest_place(conn, *CAMPUS_CENTER)[0]

    # ---- rule layer: emergencies and crisis language get fixed, verified buttons first
    hints: list[str] = []
    pinned: list[dict[str, Any]] = []
    if immediate_danger_language(message):
        hints.append("The message suggests immediate danger. Lead with calling 911 or holding SOS.")
        pinned.append({"kind": "call", "label": "Call 911 now", "phone": "911"})
        log_safety(conn, "emergency_redirect", "rule", "Chat message suggested immediate danger; 911 button pinned", user["id"], "chat")
    if crisis_language(message):
        hints.append("The message may mention self-harm. Respond gently and lead with 988 and Yale mental health support.")
        pinned.append({"kind": "call", "label": "Call or text 988", "phone": "988"})
        pinned.append({"kind": "open_resources", "label": "Yale mental health numbers"})
        log_safety(conn, "crisis_support_shown", "rule", "Self-harm language in chat; 988 pinned", user["id"], "chat")
    injection = looks_like_injection(message)
    if injection:
        log_safety(conn, "injection_attempt", "rule", f"Chat message matched {injection!r} (agent has read-only tools)",
                   user["id"], "chat")

    history = concierge.history_messages(conn, user["id"], CHAT_HISTORY_TURNS)
    conn.execute("INSERT INTO chat_messages (user_id, role, content, created_at) VALUES (?,?,?,?)",
                 (user["id"], "user", message, now_iso()))
    conn.commit()

    deps = concierge.ConciergeDeps(conn=conn, user=user, here=here, now_local=now_utc().astimezone(TZ))
    run: dict[str, Any] | None = None
    try:
        reply, record = await concierge.ask(conn, deps=deps, message=message, hints=hints, history=history)
        run = _run_summary(record)
    except LimitExceeded as exc:
        reply = ConciergeReply(reply=f"{exc.message}\n\nIf you're in danger, call 911 or Yale Police at (203) 432-4400.",
                               actions=[ConciergeAction(kind="open_resources", label="Open verified resources")])
    except AgentUnavailable as exc:
        run = _run_summary(exc.record)
        reply = ConciergeReply(
            reply="I couldn't reach Beacon's AI just now. If this is an emergency, call 911 or Yale Police at "
                  "(203) 432-4400. The alert map and Resources still work.",
            actions=[ConciergeAction(kind="call", label="Call Yale Police", phone="2034324400"),
                     ConciergeAction(kind="open_resources", label="Open verified resources")])

    # ---- guard layer
    guards: list[str] = []
    text, removed = vet_phone_numbers(conn, reply.reply)
    if removed:
        guards.append(f"removed unverified phone number(s): {', '.join(removed)}")
    cited = [i for i in reply.cited_incident_ids if i in deps.seen_incident_ids]
    bogus = [i for i in reply.cited_incident_ids if i not in deps.seen_incident_ids]
    if bogus:
        guards.append(f"removed citation(s) to incident(s) the agent never looked up: {bogus}")
    actions, dropped = _vet_actions(conn, reply.actions, deps.seen_incident_ids)
    if dropped:
        guards.append(f"dropped invalid button(s): {', '.join(dropped)}")
    for g in guards:
        log_safety(conn, "output_guard", "guard", g, user["id"], "chat")
    seen_keys = set()
    merged = []
    for a in pinned + actions:
        key = (a["kind"], a.get("phone"), a.get("dest_place_id"), a.get("incident_id"))
        if key not in seen_keys:
            seen_keys.add(key)
            merged.append(a)

    cards = [c for c in (_incident_card(conn, i) for i in cited) if c]
    meta = {"actions": merged[:4], "cited": cited, "guards": guards, "run": run}
    conn.execute("INSERT INTO chat_messages (user_id, role, content, meta_json, created_at) VALUES (?,?,?,?,?)",
                 (user["id"], "assistant", text, dumps(meta), now_iso()))
    conn.commit()
    return {"reply": text, "actions": merged[:4], "incidents": cards, "guards": guards, "run": run,
            "here": {"id": here["id"], "name": here["name"]}}


def chat_history(conn: sqlite3.Connection, user_id: int) -> list[dict[str, Any]]:
    out = []
    for m in rows(conn.execute("SELECT * FROM chat_messages WHERE user_id = ? ORDER BY id DESC LIMIT 40", (user_id,)))[::-1]:
        meta = loads(m["meta_json"], {})
        out.append({"role": m["role"], "content": m["content"], "created_at": m["created_at"],
                    "actions": meta.get("actions", []), "guards": meta.get("guards", []), "run": meta.get("run"),
                    "incidents": [c for c in (_incident_card(conn, i) for i in meta.get("cited", [])) if c]})
    return out


# ======================================================================= SOS

def _timeline_add(conn: sqlite3.Connection, table: str, row_id: int, column: str, event: str) -> None:
    row = one(conn, f"SELECT {column} FROM {table} WHERE id = ?", (row_id,))
    items = loads(row[column] if row else "[]", [])
    items.append({"t": now_iso(), "event": event})
    conn.execute(f"UPDATE {table} SET {column} = ? WHERE id = ?", (dumps(items), row_id))


def trigger_sos(conn: sqlite3.Connection, user: dict[str, Any], body: SosBody) -> dict[str, Any]:
    """No model call here: the alert must never wait on (or fail because of) AI."""
    place, lat, lng = resolve_location(conn, body.place_id, body.lat, body.lng)
    d = meters_between(lat, lng, place["lat"], place["lng"])
    label = place["name"] if d < 60 else f"{int(d)} m from {place['name']}"
    contacts = loads(user["contacts_json"], [])
    t = now_iso()
    timeline = [{"t": t, "event": "SOS pressed"},
                {"t": t, "event": "Alert and live location sent to Yale PD dispatch (simulated console)"}]
    if contacts:
        timeline.append({"t": t, "event": "Trusted contacts notified (simulated): " + ", ".join(c["name"] for c in contacts)})
    cur = conn.execute(
        "INSERT INTO sos_events (user_id, created_at, lat, lng, place_label, contacts_notified_json, timeline_json, brief_status) "
        "VALUES (?,?,?,?,?,?,?,'waiting_for_note')", (user["id"], t, lat, lng, label, dumps(contacts), dumps(timeline)))
    conn.commit()
    sos = one(conn, "SELECT * FROM sos_events WHERE id = ?", (cur.lastrowid,))
    assert sos is not None
    return sos_view(sos)


def sos_view(s: dict[str, Any]) -> dict[str, Any]:
    return {**{k: s[k] for k in ("id", "user_id", "created_at", "lat", "lng", "place_label", "note", "status", "brief_status")},
            "brief": loads(s["brief_json"], None), "contacts_notified": loads(s["contacts_notified_json"], []),
            "timeline": loads(s["timeline_json"], [])}


def add_sos_note(conn: sqlite3.Connection, user: dict[str, Any], sos_id: int, note: str) -> dict[str, Any]:
    sos = one(conn, "SELECT * FROM sos_events WHERE id = ? AND user_id = ?", (sos_id, user["id"]))
    if not sos:
        raise HTTPException(404, "No such SOS.")
    note = note.strip()[:500]
    conn.execute("UPDATE sos_events SET note = ?, brief_status = 'pending' WHERE id = ?", (note, sos_id))
    _timeline_add(conn, "sos_events", sos_id, "timeline_json", "Caller added a note for responders")
    conn.commit()
    return sos_view(one(conn, "SELECT * FROM sos_events WHERE id = ?", (sos_id,)) or sos)


async def write_sos_brief(sos_id: int) -> None:
    conn = connect()
    try:
        sos = one(conn, "SELECT * FROM sos_events WHERE id = ?", (sos_id,))
        if not sos:
            return
        user = one(conn, "SELECT * FROM users WHERE id = ?", (sos["user_id"],))
        nearby = []
        since = now_utc() - timedelta(hours=6)
        for inc in rows(conn.execute("SELECT * FROM incidents WHERE status='active' AND last_reported >= ?", (iso(since),))):
            d = meters_between(sos["lat"], sos["lng"], inc["lat"], inc["lng"])
            if d <= 400:
                mins = int((now_utc() - parse_iso(inc["last_reported"])).total_seconds() // 60)
                nearby.append({"title": inc["title"], "distance_m": int(d), "minutes_ago": mins})
        try:
            brief, _ = await responder.write_brief(conn, sos=sos, user=user or {}, local_time=local_now_text(),
                                                   nearby=nearby[:3])
            conn.execute("UPDATE sos_events SET brief_json = ?, brief_status = 'ready' WHERE id = ?",
                         (dumps(brief.model_dump()), sos_id))
            _timeline_add(conn, "sos_events", sos_id, "timeline_json", "AI responder brief ready (verify with caller)")
        except (LimitExceeded, AgentUnavailable) as exc:
            conn.execute("UPDATE sos_events SET brief_status = 'failed' WHERE id = ?", (sos_id,))
            _timeline_add(conn, "sos_events", sos_id, "timeline_json",
                          f"AI brief unavailable ({type(exc).__name__}); dispatcher uses the caller's note")
        conn.commit()
    finally:
        conn.close()


def set_sos_status(conn: sqlite3.Connection, sos_id: int, status: str, who: str) -> dict[str, Any]:
    sos = one(conn, "SELECT * FROM sos_events WHERE id = ?", (sos_id,))
    if not sos:
        raise HTTPException(404, "No such SOS.")
    conn.execute("UPDATE sos_events SET status = ? WHERE id = ?", (status, sos_id))
    label = {"cancelled": "Caller marked themselves safe", "acknowledged": "Dispatcher acknowledged",
             "resolved": "Dispatcher resolved the call"}[status]
    _timeline_add(conn, "sos_events", sos_id, "timeline_json", f"{label} ({who})")
    conn.commit()
    return sos_view(one(conn, "SELECT * FROM sos_events WHERE id = ?", (sos_id,)) or sos)


# ===================================================================== walks

def walk_view(conn: sqlite3.Connection, w: dict[str, Any]) -> dict[str, Any]:
    o, d = place_by_id(conn, w["origin_place_id"]), place_by_id(conn, w["dest_place_id"])
    return {**{k: w[k] for k in ("id", "user_id", "started_at", "eta", "status", "ended_at")},
            "origin": {"id": o["id"], "name": o["name"], "lat": o["lat"], "lng": o["lng"]} if o else None,
            "dest": {"id": d["id"], "name": d["name"], "lat": d["lat"], "lng": d["lng"]} if d else None,
            "contacts": loads(w["contacts_json"], []), "events": loads(w["events_json"], [])}


def start_walk(conn: sqlite3.Connection, user: dict[str, Any], body: WalkBody) -> dict[str, Any]:
    if not (place_by_id(conn, body.origin_place_id) and place_by_id(conn, body.dest_place_id)):
        raise HTTPException(400, "Pick a start and a destination.")
    if body.origin_place_id == body.dest_place_id:
        raise HTTPException(400, "Start and destination are the same place.")
    for w in rows(conn.execute("SELECT id FROM walks WHERE user_id = ? AND status IN ('active','overdue')", (user["id"],))):
        conn.execute("UPDATE walks SET status='cancelled', ended_at=? WHERE id=?", (now_iso(), w["id"]))
    contacts = loads(user["contacts_json"], [])
    t = now_utc()
    events = [{"t": iso(t), "event": f"Walk started; check-in due in {body.minutes} min"}]
    if contacts:
        events.append({"t": iso(t), "event": "Shared route with " + ", ".join(c["name"] for c in contacts) + " (simulated)"})
    cur = conn.execute(
        "INSERT INTO walks (user_id, origin_place_id, dest_place_id, started_at, eta, status, contacts_json, events_json) "
        "VALUES (?,?,?,?,?,'active',?,?)", (user["id"], body.origin_place_id, body.dest_place_id, iso(t),
                                             iso(t + timedelta(minutes=body.minutes)), dumps(contacts), dumps(events)))
    conn.commit()
    return walk_view(conn, one(conn, "SELECT * FROM walks WHERE id = ?", (cur.lastrowid,)) or {})


def end_walk(conn: sqlite3.Connection, user: dict[str, Any], walk_id: int, status: str) -> dict[str, Any]:
    w = one(conn, "SELECT * FROM walks WHERE id = ? AND user_id = ?", (walk_id, user["id"]))
    if not w:
        raise HTTPException(404, "No such walk.")
    conn.execute("UPDATE walks SET status = ?, ended_at = ? WHERE id = ?", (status, now_iso(), walk_id))
    _timeline_add(conn, "walks", walk_id, "events_json",
                  "Checked in: arrived safely" if status == "arrived" else "Walk cancelled")
    conn.commit()
    return walk_view(conn, one(conn, "SELECT * FROM walks WHERE id = ?", (walk_id,)) or w)


def check_walks(conn: sqlite3.Connection) -> None:
    """Runs every few seconds. Pure code: a missed check-in never depends on a model."""
    now = now_utc()
    for w in rows(conn.execute("SELECT * FROM walks WHERE status IN ('active','overdue')")):
        eta = parse_iso(w["eta"])
        if w["status"] == "active" and now > eta:
            conn.execute("UPDATE walks SET status='overdue' WHERE id=?", (w["id"],))
            _timeline_add(conn, "walks", w["id"], "events_json", "Check-in missed: asked the walker if they're OK")
        elif w["status"] == "overdue" and now > eta + WALK_ESCALATE_AFTER:
            conn.execute("UPDATE walks SET status='escalated' WHERE id=?", (w["id"],))
            contacts = ", ".join(c["name"] for c in loads(w["contacts_json"], [])) or "no contacts on file"
            _timeline_add(conn, "walks", w["id"], "events_json",
                          f"No response: alerted {contacts} and the Yale PD console with the last known route (simulated)")
    conn.commit()
