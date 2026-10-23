"""Stress test: many virtual Yale users hitting a fresh copy of Bulldog Beacon at once.

Phases (all against a scratch database on port 8040, real gpt-6-luna calls):
  A. Browsing load: 50 users reading the map, community feed, events and places at the same time.
  B. AI load: waves of 5, 15 and 30 users at once, each asking Beacon a question, posting an
     alert and leaving a comment (about 150 model-backed requests in total).
  C. SOS during the heaviest AI wave: does an emergency alert slow down when the AI is busy?
  D. Abuse: one NetID sends 20 chat messages as fast as it can (rate limit and budget defense).

    python report/stress_test.py

Writes output/stress_test.json and output/stress_test.md. Costs a few cents.
"""

import asyncio
import json
import os
import random
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
PORT = 8040
BASE = f"http://127.0.0.1:{PORT}"
DB = Path(tempfile.mkdtemp(prefix="beacon-stress-")) / "stress.db"
random.seed(7)

PLACES = [1, 2, 3, 5, 8, 11, 12, 13, 14, 16, 19, 21, 24, 25, 26, 27]
QUESTIONS = [
    "Is it OK to walk from here to the {dest} right now?",
    "What's been reported near the {dest} today?",
    "Is the walking escort running, and how do I get one to the {dest}?",
    "Can I get a safe ride to the {dest} tonight?",
    "Anything happening at Yale this evening near the {dest}?",
    "I'm a bit nervous walking to the {dest} alone. What do you suggest?",
]
DESTS = ["Temple Street Garage", "Air Rights Garage", "Union Station", "Payne Whitney Gym", "Sterling Memorial Library",
         "Yale Health Center", "Wooster Square", "East Rock", "Yale West Campus", "Chapel-York Garage"]
POSTS = [
    ("hazard", "Streetlight out on the sidewalk near the {dest}, very dark after 6."),
    ("theft", "Bike stolen from the rack by the {dest} between {h} and {h2}, cable lock cut."),
    ("vehicle_break_in", "Car window smashed on the second level near the {dest}, glass on the ground around {h}."),
    ("suspicious_activity", "Someone in a gray hoodie was trying car door handles near the {dest} around {h}, then walked off."),
    ("good_news", "Thanks to the Yale Security officer who walked me to the {dest} last night."),
    ("hazard", "Icy patch on the steps by the {dest}, careful."),
]
COMMENTS = ["Thanks for posting, I'll avoid that area tonight.", "Saw the same thing about ten minutes ago.",
            "Yale Security is aware, an officer was there.", "Stay safe everyone!", "Good to know, thank you."]


def pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    v = sorted(values)
    return v[min(len(v) - 1, int(round(q * (len(v) - 1))))]


class Recorder:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    async def call(self, phase: str, label: str, client: httpx.AsyncClient, method: str, url: str, **kw) -> httpx.Response | None:
        t = time.perf_counter()
        try:
            r = await client.request(method, url, **kw)
            ms = (time.perf_counter() - t) * 1000
            self.rows.append({"phase": phase, "endpoint": label, "status": r.status_code, "ms": round(ms, 1)})
            return r
        except Exception as exc:  # network error, timeout
            ms = (time.perf_counter() - t) * 1000
            self.rows.append({"phase": phase, "endpoint": label, "status": f"error:{type(exc).__name__}", "ms": round(ms, 1)})
            return None


async def make_user(i: int) -> httpx.AsyncClient:
    c = httpx.AsyncClient(base_url=BASE, timeout=150)
    await c.post("/api/auth/login", json={"netid": f"st{i:03d}", "password": "stress-pass-123", "name": f"Virtual user {i}"})
    return c


async def browse(rec: Recorder, c: httpx.AsyncClient, n: int) -> None:
    for _ in range(n):
        ep = random.choice(["/api/incidents?hours=24", "/api/community", "/api/events?hours=12", "/api/places", "/api/resources"])
        await rec.call("A browse", ep.split("?")[0], c, "GET", ep)


async def ai_session(rec: Recorder, c: httpx.AsyncClient, phase: str, notes: dict) -> None:
    dest = random.choice(DESTS)
    q = random.choice(QUESTIONS).format(dest=dest)
    r = await rec.call(phase, "/api/chat", c, "POST", "/api/chat", json={"message": q, "place_id": random.choice(PLACES)})
    if r is not None and r.status_code == 200:
        body = r.json()
        run = body.get("run") or {}
        if run.get("status") != "ok":
            notes["chat_fallbacks"] += 1
        notes["chat_rows"].append({"wave": phase, "model_calls": run.get("requests"), "tools": run.get("tool_calls"),
                                   "ms": rec.rows[-1]["ms"]})
        if any(a.get("kind") in ("request_escort", "call", "start_walk") for a in body.get("actions", [])):
            notes["chat_with_action"] += 1
        notes["chats"] += 1
    cat, text = random.choice(POSTS)
    h = random.randint(6, 10)
    r = await rec.call(phase, "/api/posts", c, "POST", "/api/posts",
                       json={"text": text.format(dest=dest, h=f"{h}pm", h2=f"{h + 1}pm"), "category": cat,
                             "place_id": random.choice(PLACES)})
    if r is not None and r.status_code == 200:
        st = r.json()["post"]["status"]
        notes["post_status"][st] = notes["post_status"].get(st, 0) + 1
    feed = await rec.call(phase, "/api/community", c, "GET", "/api/community")
    if feed is not None and feed.status_code == 200:
        others = [p for p in feed.json() if not p["mine"]]
        if others:
            target = random.choice(others)
            r = await rec.call(phase, "/api/comments", c, "POST", f"/api/posts/{target['id']}/comments",
                               json={"text": random.choice(COMMENTS)})
            if r is not None and r.status_code == 200:
                st = r.json()["comment"]["status"]
                notes["comment_status"][st] = notes["comment_status"].get(st, 0) + 1


async def sos_probe(rec: Recorder, c: httpx.AsyncClient, stop: asyncio.Event) -> None:
    while not stop.is_set():
        r = await rec.call("C SOS during AI load", "/api/sos", c, "POST", "/api/sos", json={"place_id": random.choice(PLACES)})
        if r is not None and r.status_code == 200:
            await c.post(f"/api/sos/{r.json()['id']}/safe", json={})
        await asyncio.sleep(1.5)


async def main() -> None:
    env = {**os.environ, "BEACON_DB": str(DB), "PYTHONUTF8": "1"}
    server = subprocess.Popen([sys.executable, str(ROOT / "run.py"), "--port", str(PORT), "--no-browser", "--reset"],
                              env=env, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    rec = Recorder()
    out: dict = {"phases": {}}
    started = time.time()
    try:
        for _ in range(60):
            try:
                if httpx.get(f"{BASE}/api/health", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                await asyncio.sleep(0.5)
        users = [await make_user(i) for i in range(1, 51)]
        print("50 virtual users signed in", flush=True)

        # A. browsing load
        t = time.time()
        await asyncio.gather(*(browse(rec, u, 40) for u in users))
        out["phases"]["A"] = {"users": 50, "seconds": round(time.time() - t, 1)}
        print(f"A done in {out['phases']['A']['seconds']} s", flush=True)

        # B + C. AI waves, with an SOS probe during the biggest wave
        notes = {"chats": 0, "chat_fallbacks": 0, "chat_with_action": 0, "post_status": {}, "comment_status": {}, "chat_rows": []}
        offset = 0
        for size in (5, 15, 30):
            wave = users[offset:offset + size]
            offset += size
            stop = asyncio.Event()
            probe_client = await make_user(900 + size)
            probe = asyncio.create_task(sos_probe(rec, probe_client, stop)) if size == 30 else None
            t = time.time()
            await asyncio.gather(*(ai_session(rec, u, f"B AI wave of {size}", notes) for u in wave))
            out["phases"][f"B{size}"] = {"users": size, "seconds": round(time.time() - t, 1)}
            stop.set()
            if probe:
                await probe
            await probe_client.aclose()
            print(f"wave of {size} done in {out['phases'][f'B{size}']['seconds']} s", flush=True)
        out["ai_notes"] = notes

        # D. one NetID flooding the chat
        spammer = await make_user(999)
        replies = await asyncio.gather(*(rec.call("D abuse: 20 chats from one NetID", "/api/chat", spammer, "POST", "/api/chat",
                                                   json={"message": f"spam test {k}: is the escort open?", "place_id": 1})
                                          for k in range(20)))
        limited = sum(1 for r in replies if r is not None and r.status_code == 200 and "quickly" in r.json().get("reply", ""))
        answered = sum(1 for r in replies if r is not None and r.status_code == 200 and (r.json().get("run") or {}).get("status") == "ok")
        out["abuse"] = {"sent": 20, "answered_by_ai": answered, "refused_by_rate_limit": limited}
        await spammer.aclose()
        for u in users:
            await u.aclose()
        print("D done", flush=True)
    finally:
        server.terminate()
        try:
            _, err = server.communicate(timeout=10)
            server_errors = [l for l in (err or b"").decode(errors="ignore").splitlines() if "Traceback" in l or "Error" in l]
        except subprocess.TimeoutExpired:
            server.kill()
            server_errors = []

    # model-call stats straight from the app's own log
    sys.path.insert(0, str(ROOT / "backend"))
    os.environ["BEACON_DB"] = str(DB)
    import db as dbmod
    conn = dbmod.connect()
    runs = dbmod.rows(conn.execute("SELECT agent, status, input_tokens, cached_tokens, output_tokens, latency_ms, cost_usd FROM ai_runs"))
    statuses: dict[str, int] = {}
    for r in runs:
        statuses[r["status"]] = statuses.get(r["status"], 0) + 1
    ok = [r for r in runs if r["status"] == "ok"]
    out["model_calls"] = {
        "runs": len(runs), "statuses": statuses,
        "tokens": sum(r["input_tokens"] + r["output_tokens"] for r in runs),
        "cost_usd": round(sum(r["cost_usd"] for r in runs), 5),
        "p50_latency_s": round(pct([r["latency_ms"] for r in ok], 0.5) / 1000, 2),
        "p95_latency_s": round(pct([r["latency_ms"] for r in ok], 0.95) / 1000, 2),
    }
    out["server_error_lines"] = server_errors[:10]

    groups: dict[tuple, list] = {}
    for r in rec.rows:
        groups.setdefault((r["phase"], r["endpoint"]), []).append(r)
    table = []
    for (phase, ep), rs in sorted(groups.items()):
        ms = [r["ms"] for r in rs]
        errs = [r for r in rs if not (isinstance(r["status"], int) and r["status"] < 500)]
        limited = [r for r in rs if r["status"] == 429]
        table.append({"phase": phase, "endpoint": ep, "requests": len(rs), "server_errors": len(errs), "rate_limited_429": len(limited),
                      "p50_ms": round(pct(ms, 0.5)), "p95_ms": round(pct(ms, 0.95)), "max_ms": round(max(ms))})
    out["table"] = table
    out["total_requests"] = len(rec.rows)
    out["total_server_errors"] = sum(t["server_errors"] for t in table)
    out["wall_seconds"] = round(time.time() - started, 1)

    lines = ["# Stress test (virtual users, real gpt-6-luna)", "",
             f"{out['total_requests']} requests, {out['total_server_errors']} server errors (5xx or network), "
             f"{out['model_calls']['runs']} model calls ({out['model_calls']['statuses']}), "
             f"{out['model_calls']['tokens']:,} tokens, ${out['model_calls']['cost_usd']}.", "",
             "| Phase | Endpoint | Requests | 5xx/errors | 429 | p50 | p95 | max |", "|---|---|---|---|---|---|---|---|"]
    for t in table:
        lines.append(f"| {t['phase']} | {t['endpoint']} | {t['requests']} | {t['server_errors']} | {t['rate_limited_429']} | "
                     f"{t['p50_ms']} ms | {t['p95_ms']} ms | {t['max_ms']} ms |")
    by_calls: dict[int, list[float]] = {}
    for row in out["ai_notes"]["chat_rows"]:
        by_calls.setdefault(row["model_calls"] or 0, []).append(row["ms"])
    out["chat_ms_by_model_calls"] = {k: {"n": len(v), "p50_ms": round(pct(v, 0.5))} for k, v in sorted(by_calls.items())}
    lines += ["", f"Chat time by model round trips: {json.dumps(out['chat_ms_by_model_calls'])}",
              f"AI notes: {json.dumps({k: v for k, v in out['ai_notes'].items() if k != 'chat_rows'})}", f"Abuse: {json.dumps(out['abuse'])}",
              f"Phase timings: {json.dumps(out['phases'])}", f"Server error lines: {out['server_error_lines'] or 'none'}"]
    (ROOT / "output" / "stress_test.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    (ROOT / "output" / "stress_test.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    asyncio.run(main())
