"""Estonian electricity exchange prices (Nord Pool day-ahead via Elering)."""
from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from .base import ToolError

ELERING_URL = "https://dashboard.elering.ee/api/nps/price"
TZ = ZoneInfo("Europe/Tallinn")


def _hour_label(ts: int) -> str:
    return datetime.fromtimestamp(ts, TZ).strftime("%H:00")


def _hour_ts(ts: int) -> int:
    return ts // 3600 * 3600


def _window(start: datetime, end: datetime) -> dict[str, str]:
    """Elering query window (UTC ISO strings)."""
    return {
        "start": start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end": end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _hourly(rows: list[dict]) -> list[dict]:
    """Aggregate Elering's 15-min blocks into hourly averages (cents/kWh)."""
    buckets: dict[int, list[float]] = defaultdict(list)
    for p in rows:
        buckets[_hour_ts(int(p["timestamp"]))].append(float(p["price"]) / 10)
    return [{"time": h, "price": round(sum(v) / len(v), 2)} for h, v in sorted(buckets.items())]


def _labelled(rows: list[dict]) -> list[dict]:
    return [{"hour": _hour_label(p["time"]), "price": p["price"]} for p in rows]


async def _get(client: httpx.AsyncClient, params: dict | None = None) -> list[dict]:
    resp = await client.get(ELERING_URL, params=params)
    resp.raise_for_status()
    return (resp.json().get("data") or {}).get("ee") or []


_cache: dict[str, Any] = {"data": None, "ts": 0.0}


async def electricity_price() -> dict[str, Any]:
    """Current price + today's actuals + tomorrow's day-ahead prices (60s cache)."""
    if _cache["data"] is not None and time.time() - _cache["ts"] < 60:
        return _cache["data"]
    now = datetime.now(TZ)
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            # Live "current" price = the most recently settled 15-min actual. The
            # bare API returns only past actuals, unlike the windowed query which
            # mixes settled actuals with intra-day forecasts for unexpired blocks.
            actuals = await _get(client)
            # Today's full day (past actuals + future day-ahead). The bare API
            # returns only past actuals, so ask for an explicit midnight→midnight
            # window to get all 24 hours.
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = today_start + timedelta(days=1)
            today_raw = _hourly(await _get(client, _window(today_start, today_end)))
            # Tomorrow's day-ahead (published in the early afternoon, may be partial).
            tomorrow_raw = _hourly(await _get(client, _window(today_end, today_end + timedelta(days=1))))
    except httpx.HTTPError as err:
        raise ToolError(f"can't reach Elering ({err})") from err

    # Elering's windowed query is end-inclusive: it also returns the first 15-min
    # block of the *next* day, which _hourly() folds into a bogus extra "00:00"
    # hour (a 25-hour "day"). Keep only hours whose local date is the requested day.
    def _keep(rows: list[dict], day: datetime) -> list[dict]:
        return [p for p in rows if datetime.fromtimestamp(p["time"], TZ).date() == day.date()]

    today_rows = _keep(today_raw, today_start)
    tomorrow_rows = _keep(tomorrow_raw, today_end)

    current_price = round(float(actuals[-1]["price"]) / 10, 2) if actuals else None

    now_hour = _hour_ts(int(now.timestamp()))
    # Make the current hour's bar show the live settled price (not the mixed
    # actual+forecast average) so the graph and the big number agree.
    if current_price is not None:
        for p in today_rows:
            if p["time"] == now_hour:
                p["price"] = current_price

    def stats(rows: list[dict]) -> tuple[float | None, float | None, float | None]:
        if not rows:
            return None, None, None
        prices = [p["price"] for p in rows]
        return min(prices), max(prices), round(sum(prices) / len(prices), 2)

    today_min, today_max, today_avg = stats(today_rows)
    tomorrow_min, tomorrow_max, _ = stats(tomorrow_rows)

    upcoming = [p for p in today_rows if p["time"] >= now_hour] + tomorrow_rows
    future = [p for p in upcoming if p["time"] > now_hour]
    cheapest = sorted(future, key=lambda p: p["price"])[:3] if future else []
    upcoming_24 = upcoming[:24]

    result = {
        "current_cents_per_kwh": current_price,
        "today_min": today_min,
        "today_max": today_max,
        "today_avg": today_avg,
        "today_hours": _labelled(today_rows),
        "upcoming_hours": _labelled(upcoming_24),
        "tomorrow_hours": _labelled(tomorrow_rows),
        "tomorrow_min": tomorrow_min,
        "tomorrow_max": tomorrow_max,
        "next_hours": _labelled([p for p in upcoming if p["time"] < now_hour + 8 * 3600]),
        "cheapest_hours": _labelled(cheapest),
    }
    _cache["data"] = result
    _cache["ts"] = time.time()
    return result
