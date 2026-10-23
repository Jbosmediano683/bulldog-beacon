"""Cost vs quality: does a cheaper Moderator setting make worse decisions?

Runs the 30 labelled posts in moderation_cases.py through the real Moderator
(gpt-6-luna) at reasoning effort none, low (the app's setting) and medium,
twice each, and measures accuracy, tokens, latency and cost. Portkey's response
cache is bypassed so every call is a real model call.

    python experiments/moderator_effort.py            # all efforts, 2 rounds
    python experiments/moderator_effort.py --rounds 1

Writes output/moderator_experiment.json and output/moderator_experiment.md.
"""

import argparse
import asyncio
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ["BEACON_DB"] = str(Path(tempfile.mkdtemp(prefix="beacon-exp-")) / "exp.db")
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "experiments"))

from agents import moderator  # noqa: E402
from agents.runtime import AgentUnavailable, run_logged, settings  # noqa: E402
from db import connect  # noqa: E402
import moderation_cases  # noqa: E402
import moderation_holdout  # noqa: E402
from safety import looks_like_injection, redact_personal_info  # noqa: E402
from seed import seed  # noqa: E402

CASES: list[dict] = moderation_cases.CASES
OUTCOME = {"publish": "published", "revise": "published", "block": "blocked", "redirect_911": "911"}


def score(case: dict, result) -> tuple[bool, str]:
    expect = case["expect"] if isinstance(case["expect"], tuple) else (case["expect"],)
    got = OUTCOME[result.decision]
    if got not in expect:
        return False, f"expected {'/'.join(expect)}, got {result.decision}"
    if got == "published":
        text = (result.published_text + " " + result.title).lower()
        leaked = [w for w in case.get("must_not_contain", []) if w in text]
        if leaked:
            return False, f"published text still contains {leaked}"
    return True, ""


def expects(case: dict) -> tuple[str, ...]:
    return case["expect"] if isinstance(case["expect"], tuple) else (case["expect"],)


async def run_one(conn, case: dict, effort: str, sem: asyncio.Semaphore) -> dict:
    """Scores the case the way the app's pipeline handles it: code rules first, then the model."""
    zero = {"input_tokens": 0, "cached_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "latency_ms": 0,
            "cost_usd": 0.0, "requests": 0}
    if looks_like_injection(case["text"]):
        return {"case": case["id"], "effort": effort, "ok": "blocked" in expects(case), "why": "", "decision": "block",
                "layer": "rule", **zero}
    cleaned, _ = redact_personal_info(case["text"], frozenset({"2034324400", "2037855555"}))
    prompt = moderator.build_prompt(cleaned, case["category"], case["place"], "Thu Oct 22, 09:40 PM", [])
    model_settings = settings("moderator", effort=effort, max_tokens=1500)
    model_settings["extra_headers"] = {"x-portkey-cache-force-refresh": "true"}  # real calls, not gateway replays
    async with sem:
        try:
            rec = await run_logged(conn, moderator.get_agent(), prompt, agent_name="moderator", user_id=None,
                                   ref=f"exp:{effort}:{case['id']}", limits=moderator.LIMITS, model_settings=model_settings)
        except AgentUnavailable as exc:
            # The app fails closed: a post the model can't review is held, never published.
            filtered = "content_filter" in (exc.record.error or "")
            return {"case": case["id"], "effort": effort, "ok": "blocked" in expects(case),
                    "why": "" if "blocked" in expects(case) else f"held ({'provider filter' if filtered else exc.record.status})",
                    "decision": "held", "layer": "provider filter" if filtered else "error", **exc.record.usage}
    ok, why = score(case, rec.output)
    sev_expected = case.get("severity")
    sev_ok = None
    if sev_expected and OUTCOME[rec.output.decision] == "published":
        sev_ok = rec.output.severity in (sev_expected if isinstance(sev_expected, tuple) else (sev_expected,))
    return {"case": case["id"], "effort": effort, "ok": ok, "why": why, "decision": rec.output.decision, "layer": "model",
            "severity": rec.output.severity, "severity_ok": sev_ok,
            "issues": rec.output.issues, "published_text": rec.output.published_text, **rec.usage}


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--efforts", default="none,low,medium")
    ap.add_argument("--set", choices=["tuning", "holdout"], default="tuning")
    args = ap.parse_args()
    global CASES
    CASES = moderation_holdout.CASES if args.set == "holdout" else moderation_cases.CASES
    suffix = "_holdout" if args.set == "holdout" else ""
    conn = connect()
    seed(conn)
    sem = asyncio.Semaphore(4)
    efforts = args.efforts.split(",")
    rows: list[dict] = []
    started = time.time()
    for rnd in range(args.rounds):
        for effort in efforts:
            batch = await asyncio.gather(*(run_one(conn, c, effort, sem) for c in CASES))
            for b in batch:
                b["round"] = rnd + 1
            rows += batch
            acc = sum(b["ok"] for b in batch) / len(batch)
            print(f"round {rnd + 1} effort={effort:6s} accuracy {acc:.0%}  ({time.time() - started:.0f}s)")

    # The rule layer in front of the model: which cases never need a model call?
    rule_caught = [c["id"] for c in CASES if looks_like_injection(c["text"])]

    summary = {}
    for effort in efforts:
        everything = [r for r in rows if r["effort"] == effort]
        rs = [r for r in everything if r["layer"] == "model"]  # token stats: real model answers only
        summary[effort] = {
            "calls": len(rs),
            "accuracy": round(sum(r["ok"] for r in everything) / len(everything), 3),
            "model_only_accuracy": round(sum(r["ok"] for r in rs) / len(rs), 3),
            "avg_input_tokens": round(statistics.mean(r["input_tokens"] for r in rs), 1),
            "avg_cached_tokens": round(statistics.mean(r["cached_tokens"] for r in rs), 1),
            "avg_output_tokens": round(statistics.mean(r["output_tokens"] for r in rs), 1),
            "avg_reasoning_tokens": round(statistics.mean(r["reasoning_tokens"] for r in rs), 1),
            "avg_latency_s": round(statistics.mean(r["latency_ms"] for r in rs) / 1000, 2),
            "p90_latency_s": round(sorted(r["latency_ms"] for r in rs)[int(0.9 * (len(rs) - 1))] / 1000, 2),
            "avg_cost_usd": round(statistics.mean(r["cost_usd"] for r in rs), 7),
            "severity_accuracy": (round(sum(r["severity_ok"] for r in rs if r.get("severity_ok") is not None)
                                        / max(1, sum(1 for r in rs if r.get("severity_ok") is not None)), 3)),
            "severity_misses": sorted({f"{r['case']}: got {r['severity']}" for r in rs if r.get("severity_ok") is False}),
            "misses": sorted({f"{r['case']}: {r['why']}" for r in everything if not r["ok"]}),
            "not_sent_to_model": sorted({f"{r['case']} ({r['layer']})" for r in everything if r["layer"] != "model"}),
        }
    out = {"model": "gpt-6-luna", "cases": len(CASES), "rounds": args.rounds, "summary": summary,
           "rule_layer_blocks_without_model": rule_caught, "runs": rows}
    (ROOT / "output").mkdir(exist_ok=True)
    (ROOT / "output" / f"moderator_experiment{suffix}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")

    lines = ["# Moderator: reasoning effort vs. quality and cost", "",
             f"{len(CASES)} labelled posts x {args.rounds} rounds per setting, gpt-6-luna, gateway cache bypassed.", "",
             "Accuracy = the whole pipeline (code rules, then the model; a post the model can't review is held). "
             "Token columns = calls the model actually answered.", "",
             "Severity = published posts graded on the scale info (no crime) / caution (property crime, suspicious "
             "behavior) / warning (crimes against people, a series) / urgent (violence in the last hour).", "",
             "| Effort | Accuracy | Model-only accuracy | Severity | Avg input | Avg cached | Avg output | Avg reasoning | Avg latency | p90 latency | Avg cost / post |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for e, s in summary.items():
        lines.append(f"| {e} | {s['accuracy']:.0%} | {s['model_only_accuracy']:.0%} | {s['severity_accuracy']:.0%} | {s['avg_input_tokens']:.0f} | {s['avg_cached_tokens']:.0f} | "
                     f"{s['avg_output_tokens']:.0f} | {s['avg_reasoning_tokens']:.0f} | {s['avg_latency_s']} s | "
                     f"{s['p90_latency_s']} s | ${s['avg_cost_usd']:.6f} |")
    lines += ["", f"Rule layer (code, 0 tokens) would block before any model call: {', '.join(rule_caught) or 'none'}", ""]
    for e, s in summary.items():
        lines.append(f"**Misses at {e}:** " + ("; ".join(s["misses"]) or "none"))
        lines.append("")
        lines.append(f"Severity misses at {e}: " + ("; ".join(s["severity_misses"]) or "none"))
        lines.append("")
        lines.append(f"Handled without a model answer at {e}: " + (", ".join(s["not_sent_to_model"]) or "none"))
        lines.append("")
    (ROOT / "output" / f"moderator_experiment{suffix}.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    asyncio.run(main())
