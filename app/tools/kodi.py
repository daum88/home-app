"""Kodi control via JSON-RPC over TCP (Kodi runs on the Android TV)."""
from __future__ import annotations

import asyncio
import json
import socket
from typing import Any

from .. import config
from .base import ToolError


def _rpc_sync(method: str, params: dict[str, Any] | None) -> Any:
    if not config.KODI_URL:
        raise ToolError("Kodi isn't configured — add KODI_URL to .env")
    host = config.KODI_URL.split("://", 1)[-1].split(":")[0].split("/")[0]
    payload = {"jsonrpc": "2.0", "method": method, "params": params or {}, "id": 1}
    resp: dict[str, Any] | None = None
    try:
        with socket.create_connection((host, config.KODI_PORT), timeout=config.REQUEST_TIMEOUT) as s:
            s.sendall((json.dumps(payload) + "\n").encode())
            s.settimeout(config.REQUEST_TIMEOUT)
            buf = b""
            while True:
                chunk = s.recv(65536)
                if not chunk:
                    break
                buf += chunk
                try:
                    resp = json.loads(buf)
                    break
                except json.JSONDecodeError:
                    continue
    except OSError as err:
        raise ToolError(f"can't reach Kodi ({err})") from err
    if resp is None:
        raise ToolError("Kodi closed the connection without a reply")
    if resp.get("error"):
        raise ToolError(str(resp["error"].get("message", "Kodi error")))
    return resp.get("result")


async def _rpc(method: str, params: dict[str, Any] | None = None) -> Any:
    return await asyncio.to_thread(_rpc_sync, method, params)


async def _active_playerid() -> int | None:
    players = await _rpc("Player.GetActivePlayers") or []
    if not players:
        return None
    return players[0].get("playerid")


async def kodi_status() -> dict[str, Any]:
    """What's playing on Kodi right now."""
    pid = await _active_playerid()
    if pid is None:
        return {"playing": None}
    item = await _rpc("Player.GetItem", {"playerid": pid, "properties": ["title", "showtitle", "season", "episode"]})
    props = await _rpc("Player.GetProperties", {"playerid": pid, "properties": ["speed", "percentage"]})
    it = (item or {}).get("item") or {}
    title = it.get("title") or it.get("label") or it.get("showtitle") or "something"
    if it.get("season") not in (None, -1):
        title = f"{it.get('showtitle')} S{it['season']}E{it['episode']}"
    speed = (props or {}).get("speed")
    paused = (speed == 0) if speed is not None else None
    return {
        "playing": title,
        "paused": paused,
        "percentage": (props or {}).get("percentage"),
    }


async def kodi_playpause() -> dict[str, Any]:
    """Pause or resume playback."""
    await _rpc("Input.ExecuteAction", {"action": "playpause"})
    return {"ok": True}


async def kodi_stop() -> dict[str, Any]:
    """Stop playback."""
    await _rpc("Input.ExecuteAction", {"action": "stop"})
    return {"ok": True}


async def kodi_set_volume(level: int) -> dict[str, Any]:
    """Set Kodi volume (0–100)."""
    level = max(0, min(100, int(level)))
    await _rpc("Application.SetVolume", {"volume": level})
    return {"volume": level}


async def kodi_notify(title: str, message: str = "") -> dict[str, Any]:
    """Show a notification on the TV/Kodi."""
    await _rpc("GUI.ShowNotification", {"title": (title or "").strip(), "message": (message or "").strip()})
    return {"ok": True}


async def kodi_play_movie(name: str) -> dict[str, Any]:
    """Play a movie from the Kodi library by name."""
    name = (name or "").strip()
    if not name:
        raise ToolError("which movie should I play?")
    result = await _rpc("VideoLibrary.GetMovies", {"properties": ["title"]})
    movies = (result or {}).get("movies") or []
    target = None
    n = name.lower()
    for m in movies:
        if n in (m.get("title") or "").lower():
            target = m
            break
    if target is None:
        raise ToolError(f"couldn't find '{name}' in the Kodi library")
    await _rpc("Player.Open", {"item": {"movieid": target["movieid"]}})
    return {"playing": target["title"]}
