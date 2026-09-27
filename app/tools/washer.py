"""Samsung washer via the SmartThings REST API (Bearer PAT).

Field map and commands verified against the ``dineshrajaram/ha-samsung-washer``
Home Assistant integration (same device family / capability layout).

Important: Samsung only allows remote *start* after the user loads the machine,
closes the door and physically presses the Smart Control button. Status reads
work regardless. We surface this as a friendly message, never a raw error.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import httpx

from .. import config, smartthings_oauth
from .base import ToolError

BASE = config.SMARTTHINGS_API
DEVICE = config.WASHER_DEVICE_ID


async def _headers() -> dict[str, str]:
    token = await smartthings_oauth.get_access_token()
    return {"Authorization": f"Bearer {token}"}


def _cmd(
    capability: str, command: str, arguments: list | None = None, component: str = "main"
) -> dict[str, Any]:
    c: dict[str, Any] = {"component": component, "capability": capability, "command": command}
    if arguments is not None:
        c["arguments"] = arguments
    return c


def _require_config() -> None:
    if not (smartthings_oauth.configured() or config.SMARTTHINGS_PAT):
        raise ToolError("the washer isn't configured — set up SmartThings OAuth or add SMARTTHINGS_PAT")


async def _get(url: str) -> dict[str, Any]:
    _require_config()
    try:
        async with httpx.AsyncClient(timeout=config.REQUEST_TIMEOUT) as client:
            resp = await client.get(url, headers=await _headers())
    except httpx.HTTPError as err:
        raise ToolError(f"can't reach SmartThings ({err})") from err
    if resp.status_code in (401, 403):
        raise ToolError("the washer is unreachable — the SmartThings token is invalid or expired")
    resp.raise_for_status()
    return resp.json()


async def _post_commands(commands: list[dict]) -> dict[str, Any]:
    _require_config()
    try:
        async with httpx.AsyncClient(timeout=config.REQUEST_TIMEOUT) as client:
            resp = await client.post(
                f"{BASE}/devices/{DEVICE}/commands",
                headers=await _headers(),
                json={"commands": commands},
            )
    except httpx.HTTPError as err:
        raise ToolError(f"can't reach SmartThings ({err})") from err
    if resp.status_code in (401, 403):
        raise ToolError("the washer is unreachable — the SmartThings token is invalid or expired")
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Status parsing (mirrors ha-samsung-washer coordinator)
# ---------------------------------------------------------------------------

def _parse(raw: dict[str, Any]) -> dict[str, Any]:
    components = raw.get("components", {}) or {}
    main = components.get("main", {}) or {}

    def val(cap: str, attr: str) -> Any:
        node = (main.get(cap, {}) or {}).get(attr, {}) or {}
        return node.get("value")

    machine_state = val("samsungce.washerOperatingState", "operatingState") or val(
        "washerOperatingState", "machineState"
    )
    job_state = val("samsungce.washerOperatingState", "washerJobState") or val(
        "washerOperatingState", "washerJobState"
    )
    completion_time = val("washerOperatingState", "completionTime")

    remaining_min = None
    if completion_time and machine_state in ("run", "running"):
        try:
            dt = datetime.fromisoformat(str(completion_time).replace("Z", "+00:00"))
            remaining_min = max(0, round((dt - datetime.now(timezone.utc)).total_seconds() / 60))
        except (ValueError, TypeError):
            remaining_min = None

    raw_cycle = val("samsungce.washerCycle", "washerCycle")
    current_cycle = raw_cycle.split("_", 2)[-1] if raw_cycle else None

    return {
        "machine_state": machine_state,
        "job_state": job_state,
        "progress": val("samsungce.washerOperatingState", "progress"),
        "remaining_minutes": remaining_min,
        "completion_time": completion_time,
        "current_cycle": current_cycle,
        "water_temp": val("custom.washerWaterTemperature", "washerWaterTemperature"),
        "spin_level": val("custom.washerSpinLevel", "washerSpinLevel"),
        "rinse_cycles": val("custom.washerRinseCycles", "washerRinseCycles"),
        "dry_level": val("custom.dryerDryLevel", "dryerDryLevel"),
        "switch": val("switch", "switch"),
        "remote_control_enabled": val("remoteControlStatus", "remoteControlEnabled"),
        "scheduled_jobs": val("samsungce.washerOperatingState", "scheduledJobs"),
    }


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

_status_cache: dict[str, Any] = {"data": None, "ts": 0.0}
_CACHE_TTL = 15.0


def _invalidate_status() -> None:
    _status_cache["data"] = None


async def washer_status() -> dict[str, Any]:
    """Current washer state: running/stopped, progress, minutes left, cycle (15s cache)."""
    if _status_cache["data"] is not None and (time.time() - _status_cache["ts"]) < _CACHE_TTL:
        return _status_cache["data"]
    raw = await _get(f"{BASE}/devices/{DEVICE}/status")
    result = _parse(raw)
    _status_cache["data"] = result
    _status_cache["ts"] = time.time()
    return result


async def washer_start() -> dict[str, Any]:
    """Start the washer. Fails with a friendly hint if Smart Control isn't on."""
    try:
        status = await washer_status()
        remote = str(status.get("remote_control_enabled", "")).lower()
        if remote in ("false", "0", "no", "none"):
            raise ToolError(
                "I can't start the washer remotely right now — load it, close the door, "
                "then press the Smart Control button on the machine first."
            )
    except ToolError as err:
        if "Smart Control" in err.message:
            raise err
        # washer_status failed (offline) — fall through and try the start anyway

    try:
        await _post_commands([_cmd("samsungce.washerOperatingState", "start")])
        _invalidate_status()
        return {"started": True, "note": "start command sent"}
    except ToolError as first:
        try:
            await _post_commands([_cmd("washerOperatingState", "setMachineState", ["run"])])
            _invalidate_status()
            return {"started": True, "note": "start command sent (legacy)"}
        except ToolError:
            if "token" in first.message.lower():
                raise first
            raise ToolError(
                "I couldn't start the washer. Load it, close the door, then press the "
                "Smart Control button on the machine and ask again — Samsung only allows "
                "remote start after that."
            ) from first


async def washer_stop() -> dict[str, Any]:
    """Stop/cancel the current wash."""
    try:
        await _post_commands([_cmd("samsungce.washerOperatingState", "cancel")])
    except ToolError:
        await _post_commands([_cmd("washerOperatingState", "setMachineState", ["stop"])])
    _invalidate_status()
    return {"stopped": True}


async def washer_pause() -> dict[str, Any]:
    """Pause the current wash."""
    await _post_commands([_cmd("samsungce.washerOperatingState", "pause")])
    _invalidate_status()
    return {"paused": True}
