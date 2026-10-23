"""Yale's blue emergency phones, traced from Yale's own blue-phone map.

data_seed/blue_phones.json holds about 500 positions. They were read from the PDF map Yale publishes on
your.yale.edu (scripts/trace_blue_phones.py does it), so members can see the phones on a real map in the app.
"""

import json
import math
from functools import lru_cache
from typing import Any

from config import ROOT
from db import meters_between

DATA = ROOT / "backend" / "data_seed" / "blue_phones.json"


@lru_cache(maxsize=1)
def load() -> dict[str, Any]:
    return json.loads(DATA.read_text(encoding="utf-8"))


def nearest(lat: float, lng: float, k: int = 3) -> list[dict[str, Any]]:
    ranked = sorted(load()["phones"], key=lambda p: meters_between(lat, lng, p["lat"], p["lng"]))
    return [{**p, "meters": int(meters_between(lat, lng, p["lat"], p["lng"]))} for p in ranked[:k]]


def along(a: dict[str, Any], b: dict[str, Any], within_m: float = 60) -> int:
    """How many blue phones are within `within_m` of the straight line from a to b."""
    kx = math.cos(math.radians(a["lat"])) * 111320.0
    ky = 110540.0
    bx, by = (b["lng"] - a["lng"]) * kx, (b["lat"] - a["lat"]) * ky
    seg = bx * bx + by * by or 1.0
    n = 0
    for p in load()["phones"]:
        px, py = (p["lng"] - a["lng"]) * kx, (p["lat"] - a["lat"]) * ky
        t = max(0.0, min(1.0, (px * bx + py * by) / seg))
        if math.hypot(px - t * bx, py - t * by) <= within_m:
            n += 1
    return n
