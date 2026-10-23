"""Corroborator agent: merges a new report into a matching incident, or starts a new one.

It only runs when code finds at least one active incident nearby (same area,
recent). Most posts have no neighbour, so most posts cost zero Corroborator tokens.
Its one tool is read-only.
"""

import sqlite3
from dataclasses import dataclass
from typing import Any

from pydantic_ai import Agent, RunContext
from pydantic_ai.usage import UsageLimits

from agents.runtime import as_json, load_prompt, run_logged, settings
from db import rows
from models import CorroborationResult
from safety import fence

LIMITS = UsageLimits(request_limit=4, tool_calls_limit=3, total_tokens_limit=30_000)


@dataclass
class CorroboratorDeps:
    conn: sqlite3.Connection
    candidate_ids: list[int]


_agent: Agent | None = None


def get_agent() -> Agent:
    global _agent
    if _agent is not None:
        return _agent
    agent = Agent(None, deps_type=CorroboratorDeps, output_type=CorroborationResult,
                  instructions=load_prompt("corroborator"), name="corroborator", retries=1)

    @agent.tool
    def read_reports(ctx: RunContext[CorroboratorDeps], incident_id: int) -> str:
        """All published reports for one candidate incident, oldest first."""
        if incident_id not in ctx.deps.candidate_ids:
            return as_json({"error": f"Incident {incident_id} is not one of the candidates {ctx.deps.candidate_ids}."})
        reports = rows(ctx.deps.conn.execute(
            "SELECT created_at, text FROM posts WHERE incident_id = ? AND status IN ('published','revised') "
            "ORDER BY created_at", (incident_id,)))
        return "\n".join(f'<community_report time="{r["created_at"]}">{fence(r["text"])}</community_report>'
                         for r in reports) or "No reports."

    _agent = agent
    return agent


def build_prompt(new_report: dict[str, Any], place_name: str, candidates: list[dict[str, Any]]) -> str:
    lines = [f"NEW REPORT (category {new_report['category']}, at {place_name}, {new_report['created_at']}):",
             f"<community_report>{fence(new_report['text'])}</community_report>", "", "CANDIDATE INCIDENTS:"]
    for c in candidates:
        lines.append(f"- id {c['id']}: {c['title']} | category {c['category']} | {c['report_count']} report(s) | "
                     f"last {c['last_reported']} | {c['distance_m']} m away")
        lines.append(f"  <community_report>{fence(c['summary'])}</community_report>")
    return "\n".join(lines)


async def corroborate(conn: sqlite3.Connection, *, new_report: dict[str, Any], place_name: str,
                      candidates: list[dict[str, Any]], user_id: int | None, ref: str) -> tuple[CorroborationResult, Any]:
    record = await run_logged(
        conn, get_agent(), build_prompt(new_report, place_name, candidates),
        agent_name="corroborator", user_id=user_id, ref=ref, limits=LIMITS,
        deps=CorroboratorDeps(conn=conn, candidate_ids=[c["id"] for c in candidates]),
        model_settings=settings("corroborator", max_tokens=1200),
    )
    return record.output, record
