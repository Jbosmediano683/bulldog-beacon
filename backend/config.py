"""Settings for Bulldog Beacon: keys, the model, spending limits, and paths.

The .env file is looked up in two places, in this order:
  1. this repo's own folder (Final Project/.env)
  2. the folder one level above it (the grader's submissions/.env)
python-dotenv never overrides a value that is already set, so the first file wins.
"""

import os
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"

ENV_FILES = [ROOT / ".env", ROOT.parent / ".env"]
for _env in ENV_FILES:
    load_dotenv(_env)


def env_file_used() -> str | None:
    """Which .env file supplied the key (shown on /api/health, never the key itself)."""
    for path in ENV_FILES:
        if path.is_file() and "PORTKEY_API_KEY" in path.read_text(encoding="utf-8", errors="ignore"):
            return "repo folder" if path.parent == ROOT else "parent folder"
    return "environment" if os.environ.get("PORTKEY_API_KEY") else None


# ---------------------------------------------------------------- the model
# Course rule: the course PORTKEY_API_KEY may only call gpt-6-luna. Every agent
# uses this one constant, and there is no fallback model.
MODEL_NAME = "gpt-6-luna"
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"
MODEL_TIMEOUT_S = 90.0

# Price per million tokens, used to turn measured token counts into dollars.
# Input/output: AnotherWrapper's LLM price list for GPT-6 Luna (Oct 2026), a
# third-party aggregator; OpenAI's own page could not be checked. Cached input
# is not listed there, so it assumes the usual 90% discount on input.
# Override with BEACON_PRICE_* env vars if Yale publishes its own rates.
PRICE_PER_MTOK = {
    "input": float(os.environ.get("BEACON_PRICE_INPUT", "0.10")),
    "cached_input": float(os.environ.get("BEACON_PRICE_CACHED", "0.01")),
    "output": float(os.environ.get("BEACON_PRICE_OUTPUT", "0.50")),
}
PRICE_SOURCE = "AnotherWrapper GPT-6 Luna list price, Oct 2026 (unverified; cached = 10% of input, assumed)"

# ------------------------------------------------------- spending guardrails
USER_DAILY_TOKEN_CAP = int(os.environ.get("BEACON_USER_DAILY_TOKENS", "150000"))
GLOBAL_DAILY_TOKEN_CAP = int(os.environ.get("BEACON_GLOBAL_DAILY_TOKENS", "3000000"))
USER_AI_CALLS_PER_MINUTE = int(os.environ.get("BEACON_USER_AI_PER_MIN", "8"))
POSTS_PER_HOUR = int(os.environ.get("BEACON_POSTS_PER_HOUR", "6"))
MAX_POST_CHARS = 600
MAX_CHAT_CHARS = 800
CHAT_HISTORY_TURNS = 8

# ------------------------------------------------------------------- places
TZ = ZoneInfo("America/New_York")
CAMPUS_CENTER = (41.3111, -72.9267)  # Cross Campus, used when a browser location is far away
# Beacon's service area: central campus, the medical campus, West Campus, and the
# neighborhoods where students and staff live (East Rock, Wooster Square, Dixwell,
# Prospect Hill, Westville, the Hill, downtown). (south, west, north, east)
SERVICE_BOUNDS = (41.245, -73.005, 41.338, -72.885)


def in_service_area(lat: float, lng: float) -> bool:
    s, w, n, e = SERVICE_BOUNDS
    return s <= lat <= n and w <= lng <= e

DB_PATH = Path(os.environ.get("BEACON_DB", ROOT / "data" / "beacon.db")).resolve()
STATIC_DIR = BACKEND / "static"
PROMPTS_DIR = BACKEND / "prompts"
OUTPUT_DIR = ROOT / "output"
