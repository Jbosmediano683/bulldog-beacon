"""Moderator agent: screens every community post before it is published.

Least privilege: this agent reads raw, untrusted text, so it has NO tools. Even
a successful prompt injection has nothing to call; the worst case is a wrong
decision, which the code guards below catch.
"""

import sqlite3
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from agents.runtime import load_prompt, run_logged, settings
from models import ModerationResult
from safety import fence

LIMITS = UsageLimits(request_limit=3, total_tokens_limit=20_000)
EFFORT = "low"  # see experiments/moderator_effort.py for the low-vs-medium comparison

_agent: Agent | None = None


def get_agent() -> Agent:
    global _agent
    if _agent is None:
        _agent = Agent(None, output_type=ModerationResult, instructions=load_prompt("moderator"),
                       name="moderator", retries=1)
    return _agent


def build_prompt(text: str, category: str, place_name: str, local_time: str, code_flags: list[str],
                 parent: str | None = None) -> str:
    """A new alert, or (when `parent` is given) a comment replying to that alert."""
    flags = "; ".join(code_flags) if code_flags else "none"
    if parent is not None:
        return (
            "Kind: COMMENT replying to a published alert.\n"
            f"The alert (category {category}, at {place_name}):\n<community_report>{fence(parent)}</community_report>\n"
            f"Time posted (New Haven): {local_time}\n"
            f"Code checks before you: {flags}\n\n"
            f"<untrusted_post>\n{fence(text)}\n</untrusted_post>"
        )
    return (
        "Kind: new ALERT.\n"
        f"Author's chosen category: {category}\n"
        f"Location picked on the map: {place_name}\n"
        f"Time posted (New Haven): {local_time}\n"
        f"Code checks before you: {flags}\n\n"
        f"<untrusted_post>\n{fence(text)}\n</untrusted_post>"
    )


async def moderate(conn: sqlite3.Connection, *, text: str, category: str, place_name: str, local_time: str,
                   code_flags: list[str], user_id: int | None, ref: str, effort: str = EFFORT,
                   parent: str | None = None) -> tuple[ModerationResult, Any]:
    record = await run_logged(
        conn, get_agent(), build_prompt(text, category, place_name, local_time, code_flags, parent),
        agent_name="moderator", user_id=user_id, ref=ref, limits=LIMITS,
        model_settings=settings("moderator", effort=effort, max_tokens=1500),
    )
    return record.output, record
