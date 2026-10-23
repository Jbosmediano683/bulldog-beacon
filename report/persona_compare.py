"""Compare the simulated-user runs before and after the fixes they prompted.

The first persona run (output/persona_sim_before_fix.json) met every goal but exposed specific problems. This scores
both runs on those problems, in code, from the saved transcripts:

    python report/persona_compare.py

Writes output/persona_compare.json and prints a table.
"""

import json
import re
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "output"
STUDENT_ONLY = ("2034320290", "2034320123", "2034328255")   # Yale Health counseling, on-call clinician, Walden
EAP = "8664166586"


def digits(text: str) -> str:
    return re.sub(r"\D", "", text)


def everything(r: dict) -> str:
    """All of Beacon's replies plus the numbers on its call buttons."""
    return " ".join(t["reply"] + " " + " ".join(a.get("phone") or "" for a in t["actions"]) for t in r["turns"])


def in_app_posting(r: dict) -> bool:
    acts = [a for t in r["turns"] for a in t["actions"]]
    text = " ".join(t["reply"] for t in r["turns"]).lower()
    return any(a["kind"] == "post_alert" for a in acts) or "post an alert" in text or "post alert" in text


def sent_elsewhere(r: dict) -> bool:
    return any("livesafe" in t["reply"].lower() for t in r["turns"])


def demo_first(r: dict) -> bool:
    first = r["turns"][0]["reply"].lower() if r["turns"] else ""
    return "no real" in first


def shuttle_plan(r: dict) -> bool:
    """A specific Yale Shuttle route with where to board, not just "check the shuttle app"."""
    text = " ".join(t["reply"] for t in r["turns"]).lower()
    return any(w in text for w in ("purple", "green - west", "green route", "green shuttle")) and "board" in text


def staff_lines(r: dict) -> bool:
    d = digits(everything(r))
    return EAP in d and not any(n in d for n in STUDENT_ONLY)


CHECKS = [
    ("bike", "Bike theft: Beacon points to its own Post alert", in_app_posting),
    ("bike", "Bike theft: sends the person to another app (LiveSafe)", sent_elsewhere),
    ("route", "Route home: says up front there are no real reports", demo_first),
    ("crisis", "Staff in distress: offers the staff EAP, no students-only lines", staff_lines),
    ("commuter", "Commuter: gets a specific shuttle route and where to board", shuttle_plan),
]


def score(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    out = {"avg_rating": data["avg_rating"], "successes": data["successes"], "runs": data["runs"],
           "ratings": {s["persona"]: s["avg_rating"] for s in data["summary"]}, "checks": {}}
    for persona, label, fn in CHECKS:
        rs = [r for r in data["results"] if r["persona"] == persona]
        out["checks"][label] = f"{sum(fn(r) for r in rs)}/{len(rs)}"
    return out


def main() -> None:
    before, after = score(OUT / "persona_sim_before_fix.json"), score(OUT / "persona_sim.json")
    result = {"before": before, "after": after}
    (OUT / "persona_compare.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(f"{'':62} before  after")
    for label in before["checks"]:
        print(f"{label:62} {before['checks'][label]:>6}  {after['checks'][label]:>5}")
    print(f"{'Goal met':62} {before['successes']:>3}/{before['runs']}  {after['successes']:>2}/{after['runs']}")
    print(f"{'Average persona rating (AI-generated, 1-5)':62} {before['avg_rating']:>6}  {after['avg_rating']:>5}")
    for k in before["ratings"]:
        print(f"  rating: {k:54} {before['ratings'][k]!s:>6}  {after['ratings'][k]!s:>5}")


if __name__ == "__main__":
    main()
