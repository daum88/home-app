"""Weather via Open-Meteo (free, no API key)."""
from __future__ import annotations

import time
from typing import Any

import httpx

from .. import config
from .base import ToolError

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

_WMO: dict[int, str] = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "icy fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain",
    66: "freezing rain", 67: "freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains",
    80: "light showers", 81: "showers", 82: "heavy showers",
    85: "snow showers", 86: "snow showers",
    95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with hail",
}


def _desc(code: Any) -> str:
    return _WMO.get(int(code) if code is not None else -1, "unknown")


async def _fetch(params: dict[str, Any]) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=config.REQUEST_TIMEOUT) as client:
            resp = await client.get(FORECAST_URL, params=params)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as err:
        raise ToolError(f"weather service is unreachable ({err})") from err


_cache: dict[str, Any] = {"data": None, "ts": 0.0}


async def weather_now() -> dict[str, Any]:
    """Current weather at the configured location (5-minute cache)."""
    if _cache["data"] is not None and time.time() - _cache["ts"] < 300:
        return _cache["data"]
    data = await _fetch({
        "latitude": config.WEATHER_LAT,
        "longitude": config.WEATHER_LON,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m,is_day",
        "daily": "temperature_2m_max,temperature_2m_min",
        "forecast_days": 1,
        "timezone": "auto",
    })
    cur = data.get("current") or {}
    daily = data.get("daily") or {}
    result = {
        "temperature": cur.get("temperature_2m"),
        "feels_like": cur.get("apparent_temperature"),
        "humidity": cur.get("relative_humidity_2m"),
        "wind_kmh": cur.get("wind_speed_10m"),
        "condition": _desc(cur.get("weather_code")),
        "is_day": cur.get("is_day"),
        "temp_max": (daily.get("temperature_2m_max") or [None])[0],
        "temp_min": (daily.get("temperature_2m_min") or [None])[0],
    }
    _cache["data"] = result
    _cache["ts"] = time.time()
    return result


async def weather_forecast(days: int = 3) -> dict[str, Any]:
    """Daily forecast for the next N days (max 7)."""
    days = max(1, min(7, int(days or 3)))
    data = await _fetch({
        "latitude": config.WEATHER_LAT,
        "longitude": config.WEATHER_LON,
        "daily": "temperature_2m_max,temperature_2m_min,weather_code,precipitation_probability_max",
        "forecast_days": days,
        "timezone": "auto",
    })
    daily = data.get("daily") or {}
    out = []
    for i in range(days):
        out.append({
            "date": (daily.get("time") or [None])[i],
            "max": (daily.get("temperature_2m_max") or [None])[i],
            "min": (daily.get("temperature_2m_min") or [None])[i],
            "condition": _desc((daily.get("weather_code") or [None])[i]),
            "precip_prob": (daily.get("precipitation_probability_max") or [None])[i],
        })
    return {"days": out}
