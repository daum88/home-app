"""Haier fridge via pyhOn (unofficial hOn cloud API — fragile, isolated).

Every call is wrapped: if the hOn backend changes again (it has before), this
module raises a friendly ToolError and the rest of the assistant keeps working.

Requires an email+password hOn account (see AGENTS.md / RESEARCH.md).
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from .. import config
from .base import ToolError

if TYPE_CHECKING:
    from pyhon import Hon

# Cache the fridge status for 180s — pyhOn re-logins on every call otherwise (slow).
_status_cache: dict[str, Any] = {"data": None, "ts": 0.0}
_CACHE_TTL = 180.0


def _hon():
    """Lazy import so a broken pyhOn never takes down the whole agent."""
    from pyhon import Hon  # noqa: PLC0415
    return Hon


def _no_auth_exc():
    from pyhon.exceptions import NoAuthenticationException  # noqa: PLC0415
    return NoAuthenticationException

# "settings.tempSelZ1" → fridge, "settings.tempSelZ2" → freezer (REF appliance).
_ZONE_KEYS = {
    "fridge": "settings.tempSelZ1",
    "freezer": "settings.tempSelZ2",
    "1": "settings.tempSelZ1",
    "2": "settings.tempSelZ2",
}


def _configured() -> bool:
    return bool(config.HON_USER and config.HON_PASS)


def _find_fridge(hon: Hon) -> Any:
    for appliance in hon.appliances:
        if appliance.appliance_type == "REF":
            return appliance
    # Fallback: any appliance that exposes the fridge climate settings.
    for appliance in hon.appliances:
        if "settings.tempSelZ1" in getattr(appliance, "settings", {}):
            return appliance
    return None


def _zone_key(zone: str) -> str:
    return _ZONE_KEYS.get((zone or "").strip().lower(), "")


def _setting_value(appliance: Any, key: str) -> Any:
    setting = appliance.settings.get(key)
    return getattr(setting, "value", None) if setting is not None else None


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

async def fridge_status() -> dict[str, Any]:
    """Fridge + freezer temperatures, door state, super cool/freeze.

    Result is cached for 180s because every pyhOn call re-runs the slow login.
    """
    if _status_cache["data"] is not None and (time.time() - _status_cache["ts"]) < _CACHE_TTL:
        return _status_cache["data"]
    if not _configured():
        raise ToolError("the fridge isn't configured — add HON_USER and HON_PASS to .env")
    Hon = _hon()
    try:
        async with Hon(config.HON_USER, config.HON_PASS) as hon:
            fridge = _find_fridge(hon)
            if fridge is None:
                raise ToolError("no fridge found on your hOn account")
            result = {
                "connected": bool(fridge.connection),
                "fridge_temp": fridge.get("tempZ1"),
                "freezer_temp": fridge.get("tempZ2"),
                "fridge_set_temp": _setting_value(fridge, "settings.tempSelZ1"),
                "freezer_set_temp": _setting_value(fridge, "settings.tempSelZ2"),
                "fridge_door_open": fridge.get("doorStatusZ1") == 1,
                "freezer_door_open": fridge.get("doorStatusZ2") == 1,
                "super_cool": fridge.get("quickModeZ1") == 1,
                "super_freeze": fridge.get("quickModeZ2") == 1,
                "on": fridge.get("onOffStatus") != 0,
            }
    except _no_auth_exc():
        raise ToolError("the fridge is offline — hOn login failed (check the credentials in .env)") from None
    except ToolError:
        raise
    except Exception as err:  # noqa: BLE001 — pyhOn is fragile; catch everything
        raise ToolError(f"the fridge is offline ({err})") from err

    _status_cache["data"] = result
    _status_cache["ts"] = time.time()
    return result


async def fridge_set_temp(zone: str, celsius: float) -> dict[str, Any]:
    """Set the fridge or freezer target temperature."""
    key = _zone_key(zone)
    if not key:
        raise ToolError("zone must be 'fridge' or 'freezer'")
    try:
        celsius = float(celsius)
    except (TypeError, ValueError):
        raise ToolError("temperature must be a number in degrees Celsius") from None
    if not _configured():
        raise ToolError("the fridge isn't configured — add HON_USER and HON_PASS to .env")
    Hon = _hon()

    try:
        async with Hon(config.HON_USER, config.HON_PASS) as hon:
            fridge = _find_fridge(hon)
            if fridge is None:
                raise ToolError("no fridge found on your hOn account")
            setting = fridge.settings.get(key)
            if setting is None:
                raise ToolError("this fridge doesn't support setting that zone's temperature")
            # Clamp to the device's allowed range.
            low = getattr(setting, "min", None)
            high = getattr(setting, "max", None)
            if low is not None and celsius < float(low):
                celsius = float(low)
            if high is not None and celsius > float(high):
                celsius = float(high)
            setting.value = str(int(celsius))
            await fridge.commands["settings"].send()
            _status_cache["data"] = None  # invalidate so the next status refreshes
            return {"zone": zone.strip().lower(), "set_to": int(celsius)}
    except _no_auth_exc():
        raise ToolError("the fridge is offline — hOn login failed") from None
    except ToolError:
        raise
    except Exception as err:  # noqa: BLE001
        raise ToolError(f"couldn't set the fridge temperature ({err})") from err
