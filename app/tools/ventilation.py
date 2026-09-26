"""Systemair SAVE ventilation via the SaveConnect 2.0 local REST API.

No cloud, no auth. Register map copied from ``antikristian/ha-saveconnect``
(0-based registers). All reads go through one ``/mread`` call; writes through
``/mwrite``. Temperatures are 16-bit signed, scale 0.1.
"""
from __future__ import annotations

import json
from typing import Any

import httpx

from .. import config
from .base import ToolError

IAQ_MAP = {0: "economic", 1: "good", 2: "improving"}
SEASON_MAP = {0: "winter", 1: "summer"}
AIRFLOW_MAP = {0: "off", 2: "low", 3: "normal", 4: "high"}
USER_MODE_MAP = {0: "auto", 1: "manual", 2: "crowded", 3: "refresh", 4: "fireplace", 5: "away", 6: "holiday"}

AIRFLOW_WRITE = {v: k for k, v in AIRFLOW_MAP.items()}
USER_MODE_WRITE = {v: k for k, v in USER_MODE_MAP.items()}

# register -> (field, kind). kind: "temp" | "raw" | "map:IAQ" | "map:SEASON" | ...
_READ_REGISTERS: dict[int, tuple[str, str]] = {
    12101: ("outdoor_temp", "temp"),
    12102: ("supply_temp", "temp"),
    12104: ("extract_temp", "temp"),
    12543: ("extract_temp_inbuilt", "temp"),
    12135: ("humidity", "raw"),          # % RH (inbuilt)
    12114: ("co2", "raw"),               # ppm
    14000: ("supply_fan_pct", "raw"),
    14001: ("extract_fan_pct", "raw"),
    12400: ("supply_fan_rpm", "raw"),
    12401: ("extract_fan_rpm", "raw"),
    1122: ("iaq_level", "map:IAQ"),
    1038: ("season", "map:SEASON"),
    1160: ("user_mode", "map:USER"),
    1130: ("airflow", "map:AIRFLOW"),
    2000: ("temp_setpoint", "temp"),
    2504: ("eco_mode", "raw"),
    4100: ("free_cooling", "raw"),
    4110: ("free_cooling_active", "raw"),
    14002: ("alarm", "raw"),
    7004: ("filter_remaining_low", "raw"),   # 32-bit, combined with 7005 below
    7005: ("filter_remaining_high", "raw"),
}


def _require_config() -> None:
    if not config.SAVECONNECT_URL:
        raise ToolError(
            "ventilation isn't configured — add SAVECONNECT_URL (e.g. http://192.168.8.x) to .env"
        )


async def _read(registers: list[int]) -> dict[int, int]:
    _require_config()
    payload = json.dumps({str(r): 1 for r in registers}, separators=(",", ":"))
    url = f"{config.SAVECONNECT_URL}/mread?{payload}"
    try:
        async with httpx.AsyncClient(timeout=config.REQUEST_TIMEOUT) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            raw = resp.json()
    except httpx.HTTPError as err:
        raise ToolError(f"can't reach the ventilation unit ({err})") from err
    if not isinstance(raw, dict):
        raise ToolError("unexpected response from the ventilation unit")
    return {int(k): v for k, v in raw.items()}


async def _write(register: int, value: int) -> None:
    _require_config()
    payload = json.dumps({str(register): value}, separators=(",", ":"))
    url = f"{config.SAVECONNECT_URL}/mwrite?{payload}"
    try:
        async with httpx.AsyncClient(timeout=config.REQUEST_TIMEOUT) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except httpx.HTTPError as err:
        raise ToolError(f"couldn't change the ventilation setting ({err})") from err


def _signed16(value: int) -> int:
    return value - 65536 if value > 32767 else value


def _decode(value: int | None, kind: str) -> Any:
    if value is None:
        return None
    if kind == "temp":
        return round(_signed16(int(value)) * 0.1, 1)
    if kind == "map:IAQ":
        return IAQ_MAP.get(int(value), int(value))
    if kind == "map:SEASON":
        return SEASON_MAP.get(int(value), int(value))
    if kind == "map:USER":
        return USER_MODE_MAP.get(int(value), int(value))
    if kind == "map:AIRFLOW":
        return AIRFLOW_MAP.get(int(value), int(value))
    return int(value)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

async def ventilation_status() -> dict[str, Any]:
    """Temperatures, humidity, CO2, fan speeds, mode and filter time."""
    raw = await _read(list(_READ_REGISTERS.keys()))
    fields = {field: _decode(raw.get(reg), kind) for reg, (field, kind) in _READ_REGISTERS.items()}

    # Filter remaining time: 32-bit value split across two 16-bit registers.
    low = raw.get(7004)
    high = raw.get(7005)
    filter_days = None
    if low is not None and high is not None:
        filter_days = round(((high << 16) | low) / 86400)

    return {
        "outdoor_temp": fields.get("outdoor_temp"),
        "supply_temp": fields.get("supply_temp"),
        "extract_temp": fields.get("extract_temp"),
        "humidity": fields.get("humidity"),
        "co2": fields.get("co2"),
        "supply_fan": {"pct": fields.get("supply_fan_pct"), "rpm": fields.get("supply_fan_rpm")},
        "extract_fan": {"pct": fields.get("extract_fan_pct"), "rpm": fields.get("extract_fan_rpm")},
        "airflow": fields.get("airflow"),
        "user_mode": fields.get("user_mode"),
        "temp_setpoint": fields.get("temp_setpoint"),
        "eco_mode": bool(fields.get("eco_mode")),
        "free_cooling": bool(fields.get("free_cooling")),
        "free_cooling_active": bool(fields.get("free_cooling_active")),
        "alarm": bool(fields.get("alarm")),
        "iaq_level": fields.get("iaq_level"),
        "season": fields.get("season"),
        "filter_days_left": filter_days,
    }


async def ventilation_set(level: str) -> dict[str, Any]:
    """Set fan speed (off/low/normal/high) or user mode (auto/manual/crowded/...)."""
    lv = (level or "").strip().lower()
    if lv in AIRFLOW_WRITE:
        await _write(1130, AIRFLOW_WRITE[lv])
        return {"airflow": lv}
    if lv in USER_MODE_WRITE:
        await _write(1161, USER_MODE_WRITE[lv])
        return {"user_mode": lv}
    raise ToolError(
        "level must be one of: off, low, normal, high (fan speed) "
        "or auto, manual, crowded, refresh, fireplace, away, holiday (mode)"
    )


async def ventilation_set_temp(celsius: float) -> dict[str, Any]:
    """Set the supply-air temperature setpoint (12.0–30.0 °C)."""
    try:
        value = float(celsius)
    except (TypeError, ValueError):
        raise ToolError("temperature must be a number in degrees Celsius") from None
    value = max(12.0, min(30.0, value))
    await _write(2000, int(round(value * 10)))
    return {"temp_setpoint": round(value, 1)}
