"""Transmission torrent tools (local JSON-RPC on :9091).

Uses the maintained ``transmission-rpc`` library. Transmission 4.x speaks
JSON-RPC 2.0 with snake_case fields, but the library normalises these for us
(``t.percent_done``, ``t.download_dir``, ``t.status`` ...).
"""
from __future__ import annotations

from typing import Any

from .. import config
from .base import ToolError, format_size, run_sync

_client: Any = None


def _get_client() -> Any:
    global _client
    if _client is None:
        from transmission_rpc import Client  # noqa: PLC0415 — lazy, light import

        host, port, user, password = config.transmission_connection()
        _client = Client(
            host=host,
            port=port,
            username=user,
            password=password,
            timeout=config.REQUEST_TIMEOUT,
        )
    return _client


def _fmt_eta(seconds: int | None) -> str | None:
    if seconds is None or seconds < 0:
        return None
    seconds = int(seconds)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


_STATUS_NAMES = {
    "downloading": "downloading",
    "seeding": "seeding",
    "stopped": "paused",
    "check pending": "checking",
    "checking": "checking",
    "download pending": "queued",
    "seed pending": "queued",
    "idle": "idle",
}


def _status_name(t: Any) -> str:
    raw = str(getattr(t, "status", "") or "").lower().replace("status.", "")
    return _STATUS_NAMES.get(raw, raw or "unknown")


def _torrent_dict(t: Any) -> dict[str, Any]:
    eta = None
    try:
        if t.eta is not None:
            eta = int(t.eta.total_seconds())
    except (AttributeError, TypeError):
        eta = None
    return {
        "id": getattr(t, "id", None),
        "name": getattr(t, "name", "") or "",
        "status": _status_name(t),
        "progress": round(float(getattr(t, "percent_done", 0) or 0) * 100, 1),
        "eta": _fmt_eta(eta),
        "size": format_size(getattr(t, "total_size", 0)),
        "download_dir": getattr(t, "download_dir", "") or "",
    }


def _wrap_torrent_error(err: Exception) -> ToolError:
    text = str(err) or err.__class__.__name__
    if "401" in text or "403" in text or "auth" in text.lower():
        return ToolError("can't reach Transmission — check the RPC username/password in .env")
    return ToolError(f"can't reach Transmission ({text})")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

async def list_torrents() -> dict[str, Any]:
    """List all torrents with progress, ETA and status."""
    try:
        torrents = await run_sync(_get_client().get_torrents)
    except Exception as err:  # noqa: BLE001 — transmission-rpc raises several types
        raise _wrap_torrent_error(err) from err
    return {"torrents": [_torrent_dict(t) for t in torrents]}


async def add_torrent(magnet_uri: str) -> dict[str, Any]:
    """Add a torrent by magnet URI or http(s) torrent URL."""
    magnet = (magnet_uri or "").strip()
    if not (magnet.startswith("magnet:") or magnet.startswith("http://") or magnet.startswith("https://")):
        raise ToolError("that doesn't look like a magnet link or torrent URL")
    try:
        added = await run_sync(_get_client().add_torrent, magnet)
    except Exception as err:  # noqa: BLE001
        raise _wrap_torrent_error(err) from err
    if added is None:
        return {"added": True, "note": "torrent added"}
    return {"added": True, "torrent": _torrent_dict(added)}


async def torrent_status(name_substr: str) -> dict[str, Any]:
    """Find one torrent by name substring and return its details."""
    query = (name_substr or "").strip().lower()
    if not query:
        raise ToolError("tell me which torrent you mean")
    try:
        torrents = await run_sync(_get_client().get_torrents)
    except Exception as err:  # noqa: BLE001
        raise _wrap_torrent_error(err) from err
    matches = [t for t in torrents if query in (getattr(t, "name", "") or "").lower()]
    if not matches:
        raise ToolError(f"no torrent matching '{name_substr}'")
    return {"torrent": _torrent_dict(matches[0])}


async def torrent_remove(name_substr: str, delete_data: bool = False) -> dict[str, Any]:
    """Remove a torrent by name substring (optionally deleting downloaded data)."""
    query = (name_substr or "").strip().lower()
    if not query:
        raise ToolError("tell me which torrent to remove")
    try:
        client = _get_client()
        torrents = await run_sync(client.get_torrents)
        matches = [t for t in torrents if query in (getattr(t, "name", "") or "").lower()]
        if not matches:
            raise ToolError(f"no torrent matching '{name_substr}'")
        target = matches[0]
        await run_sync(client.remove_torrent, [target.id], bool(delete_data))
    except ToolError:
        raise
    except Exception as err:  # noqa: BLE001
        raise _wrap_torrent_error(err) from err
    return {"removed": True, "name": getattr(matches[0], "name", name_substr)}


async def torrent_pause(torrent_id: int) -> dict[str, Any]:
    """Pause a torrent by its numeric id."""
    if torrent_id is None:
        raise ToolError("which torrent?")
    try:
        await run_sync(_get_client().stop_torrent, [torrent_id])
    except Exception as err:  # noqa: BLE001
        raise _wrap_torrent_error(err) from err
    return {"paused": True, "id": torrent_id}


async def torrent_resume(torrent_id: int) -> dict[str, Any]:
    """Resume (start) a torrent by its numeric id."""
    if torrent_id is None:
        raise ToolError("which torrent?")
    try:
        await run_sync(_get_client().start_torrent, [torrent_id])
    except Exception as err:  # noqa: BLE001
        raise _wrap_torrent_error(err) from err
    return {"resumed": True, "id": torrent_id}


async def torrent_delete(torrent_id: int, delete_data: bool = False) -> dict[str, Any]:
    """Delete a torrent by its numeric id, optionally deleting the files too."""
    if torrent_id is None:
        raise ToolError("which torrent?")
    try:
        await run_sync(_get_client().remove_torrent, [torrent_id], bool(delete_data))
    except Exception as err:  # noqa: BLE001
        raise _wrap_torrent_error(err) from err
    return {"removed": True, "id": torrent_id}
