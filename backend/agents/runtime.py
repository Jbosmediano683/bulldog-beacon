"""Shared runtime for Beacon's four agents.

Every model call goes through `run_logged`, which:
1. checks the rate limit and the daily token budgets (safety.ai_slot),
2. runs the PydanticAI agent with per-run UsageLimits and a timeout,
3. records tokens (input, cached input, output, reasoning), latency, cost,
   Portkey gateway cache hits, and the tool-call trace in the ai_runs table.
"""

import asyncio
import contextvars
import json
import os
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from openai import AsyncOpenAI
from pydantic_ai import Agent
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import ToolCallPart, ToolReturnPart
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import RunUsage, UsageLimits

from config import MODEL_NAME, MODEL_TIMEOUT_S, PORTKEY_BASE_URL, PRICE_PER_MTOK, PROMPTS_DIR
from db import dumps, now_iso
from safety import ai_slot

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

# Portkey tells us in a response header whether it answered from its cache.
_gateway_statuses: contextvars.ContextVar[list[str] | None] = contextvars.ContextVar("gateway", default=None)


async def _record_gateway_status(response: httpx.Response) -> None:
    seen = _gateway_statuses.get()
    if seen is not None:
        seen.append(response.headers.get("x-portkey-cache-status", ""))


_model: Model | None = None


def get_model() -> Model:
    """gpt-6-luna through Portkey's OpenAI-compatible Responses API. Built on first use."""
    global _model
    if _model is None:
        key = os.environ.get("PORTKEY_API_KEY")
        if not key:
            raise RuntimeError("PORTKEY_API_KEY is not set. Put it in .env in this folder or the folder above.")
        client = AsyncOpenAI(
            api_key=key,
            base_url=PORTKEY_BASE_URL,
            default_headers={"x-portkey-api-key": key},
            max_retries=2,
            timeout=MODEL_TIMEOUT_S,
            http_client=httpx.AsyncClient(event_hooks={"response": [_record_gateway_status]},
                                          timeout=MODEL_TIMEOUT_S),
        )
        _model = OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))
    return _model


def use_model(model: Model | None) -> None:
    """Tests swap in a scripted FunctionModel so they cost no tokens."""
    global _model
    _model = model


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def settings(agent_name: str, effort: str = "low", max_tokens: int = 1200) -> OpenAIResponsesModelSettings:
    return OpenAIResponsesModelSettings(
        openai_reasoning_effort=effort,  # type: ignore[typeddict-item]
        openai_text_verbosity="low",
        max_tokens=max_tokens,
        # Same key for every call of one agent, so the static prefix (instructions
        # + tool schemas) lands on the same cache and is billed as cached input.
        openai_prompt_cache_key=f"bulldog-beacon-{agent_name}",
    )


def cost_usd(input_tokens: int, cached_tokens: int, output_tokens: int) -> float:
    fresh = max(input_tokens - cached_tokens, 0)
    return (fresh * PRICE_PER_MTOK["input"] + cached_tokens * PRICE_PER_MTOK["cached_input"]
            + output_tokens * PRICE_PER_MTOK["output"]) / 1_000_000


@dataclass
class RunRecord:
    run_id: int
    status: str
    output: Any = None
    error: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    trace: list[dict[str, Any]] = field(default_factory=list)


class AgentUnavailable(Exception):
    """The model call failed or was stopped; callers fall back to a safe default."""

    def __init__(self, record: RunRecord):
        super().__init__(record.error or record.status)
        self.record = record


def _trace(messages: list[Any]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for msg in messages:
        for part in getattr(msg, "parts", []):
            if isinstance(part, ToolCallPart) and part.tool_name != "final_result":
                steps.append({"type": "tool_call", "tool": part.tool_name, "args": part.args_as_dict()})
            elif isinstance(part, ToolReturnPart) and part.tool_name != "final_result":
                text = part.model_response_str()
                steps.append({"type": "tool_result", "tool": part.tool_name,
                              "preview": text[:600] + (" ..." if len(text) > 600 else "")})
    return steps


async def run_logged(
    conn: sqlite3.Connection,
    agent: Agent,
    prompt: str,
    *,
    agent_name: str,
    user_id: int | None,
    ref: str,
    limits: UsageLimits,
    deps: Any = None,
    message_history: list[Any] | None = None,
    model_settings: OpenAIResponsesModelSettings | None = None,
    timeout_s: float = 75.0,
) -> RunRecord:
    """Run one agent with budget checks and full usage logging.

    Raises safety.LimitExceeded before any model call if a cap is reached, and
    AgentUnavailable if the run fails; the caller decides the safe fallback.
    """
    usage = RunUsage()
    gateway: list[str] = []
    status, error, result = "ok", None, None
    with ai_slot(conn, user_id):  # raises LimitExceeded before any model call
        token = _gateway_statuses.set(gateway)
        started = time.perf_counter()
        try:
            result = await asyncio.wait_for(
                agent.run(prompt, deps=deps, usage=usage, usage_limits=limits, model=get_model(),
                          message_history=message_history, model_settings=model_settings),
                timeout=timeout_s,
            )
        except UsageLimitExceeded as exc:
            status, error = "limit_stopped", str(exc)
        except asyncio.TimeoutError:
            status, error = "timeout", f"No answer within {timeout_s:.0f} s"
        except Exception as exc:  # network, provider content filter, bad output after retries
            status, error = "error", f"{type(exc).__name__}: {str(exc)[:1200]}"
        finally:
            _gateway_statuses.reset(token)
    latency_ms = int((time.perf_counter() - started) * 1000)

    trace = _trace(result.all_messages()) if result is not None else []
    cached = usage.cache_read_tokens or 0
    record_usage = {
        "requests": usage.requests, "tool_calls": usage.tool_calls,
        "input_tokens": usage.input_tokens, "cached_tokens": cached,
        "output_tokens": usage.output_tokens, "reasoning_tokens": usage.output_reasoning_tokens or 0,
        "gateway_cache_hits": sum(1 for s in gateway if s.upper() == "HIT"),
        "latency_ms": latency_ms,
        "cost_usd": round(cost_usd(usage.input_tokens, cached, usage.output_tokens), 8),
    }
    cur = conn.execute(
        "INSERT INTO ai_runs (created_at, user_id, agent, ref, model, status, requests, tool_calls, input_tokens, "
        "cached_tokens, output_tokens, reasoning_tokens, gateway_cache_hits, latency_ms, cost_usd, trace_json, error) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (now_iso(), user_id, agent_name, ref, MODEL_NAME, status, record_usage["requests"], record_usage["tool_calls"],
         record_usage["input_tokens"], cached, record_usage["output_tokens"], record_usage["reasoning_tokens"],
         record_usage["gateway_cache_hits"], latency_ms, record_usage["cost_usd"], dumps(trace), error),
    )
    conn.commit()
    record = RunRecord(run_id=int(cur.lastrowid or 0), status=status, error=error, usage=record_usage, trace=trace,
                       output=result.output if result is not None else None)
    if status != "ok":
        raise AgentUnavailable(record)
    return record


def as_json(value: Any) -> str:
    """Compact JSON for tool results (fewer tokens than pretty-printed)."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
