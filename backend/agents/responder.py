"""Responder Brief agent: writes the dispatcher's summary AFTER an SOS has fired.

The SOS itself never waits on a model: the alert, location, and contact
notifications are written by code first. This agent only adds a readable brief
when the caller types a note. No tools.
"""

import sqlite3
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from agents.runtime import load_prompt, run_logged, settings
from models import ResponderBrief
from safety import fence

LIMITS = UsageLimits(request_limit=3, total_tokens_limit=15_000)

_agent: Agent | None = None


def get_agent() -> Agent:
    global _agent
    if _agent is None:
        _agent = Agent(None, output_type=ResponderBrief, instructions=load_prompt("responder"),
                       name="responder", retries=1)
    return _agent


def build_prompt(sos: dict[str, Any], user: dict[str, Any], local_time: str, nearby: list[dict[str, Any]]) -> str:
    lines = [
        f"SOS pressed at (New Haven time): {local_time}",
        f"Location: {sos['place_label']} (lat {sos['lat']:.5f}, lng {sos['lng']:.5f})",
        f"Caller: {user['name']}, {user['affiliation']}, {user['unit'] or 'Yale'}",
        f"Caller's medical note (opt-in): {user['medical_note'] or 'none shared'}",
        "Nearby board incidents (last 6 h):",
    ]
    lines += [f"- {n['title']} ({n['distance_m']} m away, {n['minutes_ago']} min ago)" for n in nearby] or ["- none"]
    lines += ["", f"<caller_note>{fence(sos['note']) or '(empty)'}</caller_note>"]
    return "\n".join(lines)


async def write_brief(conn: sqlite3.Connection, *, sos: dict[str, Any], user: dict[str, Any], local_time: str,
                      nearby: list[dict[str, Any]]) -> tuple[ResponderBrief, Any]:
    record = await run_logged(
        conn, get_agent(), build_prompt(sos, user, local_time, nearby), agent_name="responder",
        user_id=user["id"], ref=f"sos:{sos['id']}", limits=LIMITS,
        model_settings=settings("responder", max_tokens=1200),
        timeout_s=45.0,
    )
    return record.output, record
