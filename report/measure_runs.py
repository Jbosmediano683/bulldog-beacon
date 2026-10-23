"""Tokenomics: measure a typical mix of real requests through every agent.

Runs realistic chats, posts, comments and SOS notes through the app's API on a
scratch database (real gpt-6-luna calls, normal caching, no forced refresh), then
summarizes tokens, latency and cost per agent from the ai_runs log.

    python report/measure_runs.py

Writes output/tokenomics_runs.json and output/tokenomics_runs.md.
"""

import json
import os
import statistics
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ["BEACON_DB"] = str(Path(tempfile.mkdtemp(prefix="beacon-tok-")) / "tok.db")
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from config import PRICE_PER_MTOK, PRICE_SOURCE  # noqa: E402
from db import connect, rows  # noqa: E402

CHATS = [  # (place_id, question)
    (5, "I'm finishing a night shift at YCCI around 11. Is it OK to walk to the Temple Street Garage?"),
    (1, "Is the walking escort running right now, and how do I get one from Evans Hall?"),
    (2, "What's been reported near Sterling Memorial Library today?"),
    (11, "I'm parked at the Air Rights Garage. Anything I should know before I walk to my car?"),
    (3, "All the crime news has me anxious. Anything nice happening at Yale today?"),
    (16, "Can I get a safe ride home to East Rock tonight?"),
    (25, "I work at West Campus. Who do I call if something happens out here?"),
    (21, "Is it safe to walk across the Green to Union Station after dark?"),
]
POSTS = [  # (place_id, category, text)
    (12, "vehicle_break_in", "Car window smashed on level 2 of the Temple Street garage around 9pm, glass everywhere, nothing taken."),
    (12, "vehicle_break_in", "Another smashed passenger window on level 2 of Temple St garage, maybe 9:30. My laptop bag is gone."),
    (8, "suspicious_activity", "Hispanic guy in a black jacket pulling on car door handles on Lock St around 10:45, headed toward Prospect."),
    (14, "hazard", "Streetlight out on the walkway between Kline Tower and Ingalls, very dark tonight."),
    (2, "theft", "My bike was stolen outside Sterling between 2 and 4, cable lock cut. Text me at 203-555-0187 if you saw anything."),
    (13, "good_news", "Thank you to the Yale Security officer who walked me from Payne Whitney to my car last night."),
    (21, "harassment", "A man followed two of us from the bus stop on the Green, yelling. We went into a store and he left."),
    (2, "suspicious_activity", "Black guy standing outside Sterling who doesn't look like a student."),
]
COMMENTS = [
    "Thanks for posting, I'll park on a lower level tonight.",
    "Saw the same thing around 9:15 on level 3.",
    "Stay safe everyone!",
    "It's probably one of those homeless guys from the Green.",
    "Yale Security was there by 10, they're aware.",
    "Glad you're okay. Please report it to Yale PD too.",
]
SOS_NOTES = [
    (12, "guy following me from the garage, im by the stairwell, he has something in his hand"),
    (5, "my coworker fainted in the lobby and isn't answering, she's breathing"),
    (21, "someone grabbed my bag and ran toward church st, i'm ok but shaken"),
]


def login(client: TestClient, n: int) -> None:
    client.post("/api/auth/login", json={"netid": f"tk{100 + n}", "password": "measure-pass", "name": f"Measure {n}"})


def main_() -> None:
    with TestClient(main.app) as c:
        n = 0
        for place, q in CHATS:
            login(c, n); n += 1
            c.post("/api/chat", json={"message": q, "place_id": place})
        post_ids = []
        for place, cat, text in POSTS:
            login(c, n); n += 1
            r = c.post("/api/posts", json={"text": text, "category": cat, "place_id": place}).json()
            post_ids.append(r["post"]["id"])
        visible = [p["id"] for p in c.get("/api/community?show=all").json() if not p["demo"]][:3] or post_ids[:3]
        for i, text in enumerate(COMMENTS):
            login(c, n); n += 1
            c.post(f"/api/posts/{visible[i % len(visible)]}/comments", json={"text": text})
        for place, note in SOS_NOTES:
            login(c, n); n += 1
            s = c.post("/api/sos", json={"place_id": place}).json()
            c.post(f"/api/sos/{s['id']}/note", json={"note": note})

    conn = connect()
    runs = rows(conn.execute("SELECT * FROM ai_runs WHERE status = 'ok' ORDER BY id"))
    by_ref = {"post": 0, "comment": 0}
    for r in runs:
        if r["agent"] == "moderator":
            by_ref["comment" if r["ref"].startswith("comment") else "post"] += 1
    summary = {}
    for agent in ("moderator", "corroborator", "concierge", "responder"):
        rs = [r for r in runs if r["agent"] == agent]
        if not rs:
            continue
        lat = sorted(r["latency_ms"] for r in rs)
        summary[agent] = {
            "runs": len(rs),
            "avg_requests": round(statistics.mean(r["requests"] for r in rs), 2),
            "avg_tool_calls": round(statistics.mean(r["tool_calls"] for r in rs), 2),
            "avg_input": round(statistics.mean(r["input_tokens"] for r in rs)),
            "avg_cached": round(statistics.mean(r["cached_tokens"] for r in rs)),
            "avg_output": round(statistics.mean(r["output_tokens"] for r in rs)),
            "avg_reasoning": round(statistics.mean(r["reasoning_tokens"] for r in rs)),
            "cached_share": round(sum(r["cached_tokens"] for r in rs) / max(1, sum(r["input_tokens"] for r in rs)), 3),
            "p50_latency_s": round(lat[len(lat) // 2] / 1000, 2),
            "p90_latency_s": round(lat[int(0.9 * (len(lat) - 1))] / 1000, 2),
            "avg_cost_usd": round(statistics.mean(r["cost_usd"] for r in rs), 7),
            "max_cost_usd": round(max(r["cost_usd"] for r in rs), 7),
        }
    posts_published = conn.execute("SELECT COUNT(*) FROM posts WHERE demo = 0 AND status IN ('published','revised')").fetchone()[0]
    out = {"prices_per_million": PRICE_PER_MTOK, "price_source": PRICE_SOURCE, "summary": summary,
           "workload": {"chats": len(CHATS), "posts": len(POSTS), "comments": len(COMMENTS), "sos_notes": len(SOS_NOTES),
                        "moderator_posts": by_ref["post"], "moderator_comments": by_ref["comment"],
                        "posts_published": posts_published},
           "runs": [{k: r[k] for k in ("agent", "ref", "requests", "tool_calls", "input_tokens", "cached_tokens",
                                        "output_tokens", "reasoning_tokens", "latency_ms", "cost_usd")} for r in runs]}
    (ROOT / "output").mkdir(exist_ok=True)
    (ROOT / "output" / "tokenomics_runs.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    lines = ["# Measured runs per agent (gpt-6-luna, normal caching)", "",
             "| Agent | Runs | Model calls | Tool calls | Input | Cached | Output | Cached share | p50 latency | Avg cost |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for a, s in summary.items():
        lines.append(f"| {a} | {s['runs']} | {s['avg_requests']} | {s['avg_tool_calls']} | {s['avg_input']} | {s['avg_cached']} | "
                     f"{s['avg_output']} | {s['cached_share']:.0%} | {s['p50_latency_s']} s | ${s['avg_cost_usd']:.6f} |")
    (ROOT / "output" / "tokenomics_runs.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(json.dumps(out["workload"]))


if __name__ == "__main__":
    main_()
