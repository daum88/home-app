"""Jellyfin media-library tools (self-hosted media server, Emby-compatible API).

Read-only for now: search, recent, resume, library, status. Remote "play"
needs an active Jellyfin client session, so it's a later step.
"""
from __future__ import annotations

import os
import re
import shutil
import time
from pathlib import Path
from typing import Any

import httpx

from .. import config
from .base import ToolError

_user_cache: dict[str, Any] | None = None
_library_cache: dict[str, str] = {}


async def _library_id(name: str) -> str | None:
    """Map a library display name (e.g. 'Movies') to its Jellyfin ItemId."""
    if name in _library_cache:
        return _library_cache[name] or None
    folders = await _get("/Library/VirtualFolders")
    for f in folders or []:
        _library_cache[f.get("Name") or ""] = f.get("ItemId") or ""
    return _library_cache.get(name) or None


def _enabled() -> bool:
    return bool(config.JELLYFIN_URL and config.JELLYFIN_API_KEY)


async def _get(path: str, params: dict[str, str] | None = None) -> Any:
    if not _enabled():
        raise ToolError("Jellyfin isn't configured — add JELLYFIN_URL and JELLYFIN_API_KEY to .env")
    url = config.JELLYFIN_URL + path
    try:
        async with httpx.AsyncClient(timeout=config.REQUEST_TIMEOUT) as client:
            resp = await client.get(url, headers={"Authorization": f'MediaBrowser Token="{config.JELLYFIN_API_KEY}"'}, params=params)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as err:
        raise ToolError(f"Jellyfin is unreachable ({err})") from err


async def _post(path: str, json: Any = None) -> Any:
    if not _enabled():
        raise ToolError("Jellyfin isn't configured — add JELLYFIN_URL and JELLYFIN_API_KEY to .env")
    url = config.JELLYFIN_URL + path
    try:
        async with httpx.AsyncClient(timeout=config.REQUEST_TIMEOUT) as client:
            resp = await client.post(
                url,
                headers={"Authorization": f'MediaBrowser Token="{config.JELLYFIN_API_KEY}"'},
                json=json,
            )
            resp.raise_for_status()
            return resp.json() if resp.content else {}
    except httpx.HTTPError as err:
        raise ToolError(f"Jellyfin is unreachable ({err})") from err


async def _user_id() -> str:
    global _user_cache
    if _user_cache is None:
        users = await _get("/Users")
        if not users:
            raise ToolError("no Jellyfin users found")
        _user_cache = users[0]
    return _user_cache["Id"]


def _items(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("Items") or []
    return []


async def _get_item(item_id: str, fields: str = "MediaSources") -> dict[str, Any]:
    """Fetch one item via the list endpoint (the single-item endpoint 400s in v12)."""
    data = await _get("/Items", {"Ids": item_id, "Fields": fields})
    items = _items(data)
    if not items:
        raise ToolError("item not found")
    return items[0]


def _video_stream(item: dict[str, Any]) -> dict[str, Any] | None:
    for src in item.get("MediaSources") or []:
        for s in src.get("MediaStreams") or []:
            if s.get("Type") == "Video":
                return s
    return None


def _codec_badge(item: dict[str, Any]) -> dict[str, Any]:
    """Video codec + bit depth + resolution so the app can flag unplayable files."""
    v = _video_stream(item) or {}
    codec = (v.get("Codec") or "").lower()
    bit_depth = v.get("BitDepth")
    width, height = v.get("Width"), v.get("Height")
    color_transfer = (v.get("ColorTransfer") or "").lower()
    hdr = color_transfer in {"smpte2084", "arib-std-b67"}  # PQ / HLG
    resolution = None
    if width and height:
        h = int(height)
        if h >= 2160:
            resolution = "4K"
        elif h >= 1080:
            resolution = "1080p"
        elif h >= 720:
            resolution = "720p"
        elif h > 0:
            resolution = "SD"
    return {"video_codec": codec or None, "bit_depth": bit_depth, "resolution": resolution, "hdr": hdr}


def _size_mb(item: dict[str, Any]) -> float | None:
    total = sum((s.get("Size") or 0) for s in (item.get("MediaSources") or []))
    return round(total / 1_000_000) or None


def _summarize(item: dict[str, Any]) -> dict[str, Any]:
    ticks = item.get("RunTimeTicks")
    poster = (item.get("ImageTags") or {}).get("Primary")
    return {
        "id": item.get("Id"),
        "name": item.get("Name"),
        "type": item.get("Type"),
        "year": item.get("ProductionYear"),
        "series": item.get("SeriesName"),
        "season": item.get("ParentIndexNumber"),
        "episode": item.get("IndexNumber"),
        "runtime_min": round(ticks / 600_000_000) if ticks else None,
        "rating": item.get("CommunityRating"),
        "official_rating": item.get("OfficialRating"),
        "premiere_date": ((item.get("PremiereDate") or "")[:10] or None),
        "genres": item.get("Genres") or [],
        "overview": (item.get("Overview") or "")[:300],
        "image": f"/api/jellyfin/image/{item.get('Id')}" if poster else None,
        "path": item.get("Path"),
        "size_mb": _size_mb(item),
        **_codec_badge(item),
    }


async def jellyfin_status() -> dict[str, Any]:
    """Jellyfin server name + version."""
    info = await _get("/System/Info/Public")
    return {"server": info.get("ServerName"), "version": info.get("Version")}


async def jellyfin_search(query: str) -> dict[str, Any]:
    """Search the movie + series library by name."""
    q = (query or "").strip()
    if not q:
        raise ToolError("what should I search for?")
    data = await _get("/Items", {
        "Recursive": "true",
        "SearchTerm": q,
        "IncludeItemTypes": "Movie,Series",
        "Limit": "10",
    })
    return {"results": [_summarize(i) for i in _items(data)]}


async def jellyfin_recent(limit: int = 10) -> dict[str, Any]:
    """Recently added movies/episodes."""
    uid = await _user_id()
    data = await _get(f"/Users/{uid}/Items/Latest", {"Limit": str(min(int(limit or 10), 30))})
    return {"items": [_summarize(i) for i in _items(data)]}


async def jellyfin_resume(limit: int = 10) -> dict[str, Any]:
    """Items the user is part-way through watching."""
    uid = await _user_id()
    data = await _get(f"/Users/{uid}/Items/Resume", {"Limit": str(min(int(limit or 10), 30))})
    return {"items": [_summarize(i) for i in _items(data)]}


async def jellyfin_library(media_type: str = "Movie") -> dict[str, Any]:
    """List a library: 'movie'/'film' or 'series'/'tv'."""
    uid = await _user_id()
    mtype = "Series" if (media_type or "").strip().lower().startswith(("ser", "tv", "show")) else "Movie"
    lib_name = "TV Shows" if mtype == "Series" else "Movies"
    parent = await _library_id(lib_name)
    params = {
        "Recursive": "true",
        "IncludeItemTypes": mtype,
        "SortBy": "SortName",
        "SortOrder": "Ascending",
        "Fields": "MediaSources,Path,Genres",
        "Limit": "300",
    }
    if parent:
        params["ParentId"] = parent
    data = await _get(f"/Users/{uid}/Items", params)
    return {"type": mtype, "items": [_summarize(i) for i in _items(data)]}


async def jellyfin_item_detail(item_id: str) -> dict[str, Any]:
    """Full detail for one item: overview, cast, director, genres, codec."""
    if not (item_id or "").strip():
        raise ToolError("which movie?")
    item = await _get_item(item_id, "MediaSources,Path,Genres,People,Overview")
    people = item.get("People") or []
    cast = [p.get("Name") for p in people if p.get("Type") == "Actor"][:12]
    directors = [p.get("Name") for p in people if p.get("Type") == "Director"]
    return {
        **_summarize(item),
        "overview": item.get("Overview") or "",
        "cast": cast,
        "director": directors[0] if directors else None,
    }


async def fetch_image(item_id: str) -> tuple[bytes, str] | None:
    """Proxy a Jellyfin poster image (cached on disk for a week)."""
    if not _enabled():
        return None
    cache_dir = Path(config.DB_PATH).parent / "cache" / "jellyfin"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{item_id}.jpg"
    if cache_file.exists() and (time.time() - cache_file.stat().st_mtime) < 7 * 86400:
        try:
            return cache_file.read_bytes(), "image/jpeg"
        except OSError:
            pass
    url = config.JELLYFIN_URL + f"/Items/{item_id}/Images/Primary"
    try:
        async with httpx.AsyncClient(timeout=config.REQUEST_TIMEOUT) as client:
            resp = await client.get(
                url,
                headers={"Authorization": f'MediaBrowser Token="{config.JELLYFIN_API_KEY}"'},
                params={"maxWidth": 400, "quality": 85},
            )
            resp.raise_for_status()
            data = resp.content
            content_type = resp.headers.get("content-type", "image/jpeg")
    except httpx.HTTPError:
        return None
    if not data:
        return None
    try:
        cache_file.write_bytes(data)
    except OSError:
        pass
    return data, content_type


def _local_path(jellyfin_path: str) -> str:
    """Translate Jellyfin's SMB path (Mac mount) to the Pi's real path."""
    smb = config.JELLYFIN_SMB_PREFIX
    root = config.FS_ROOT.rstrip("/")
    if smb and jellyfin_path.startswith(smb):
        return root + jellyfin_path[len(smb):]
    return jellyfin_path


async def jellyfin_delete(item_id: str) -> dict[str, Any]:
    """Delete a movie or series from disk and refresh the library."""
    if not (item_id or "").strip():
        raise ToolError("which movie should I delete?")
    item = await _get_item(item_id, "MediaSources,Path")
    name = item.get("Name") or "?"
    itype = item.get("Type")
    path = item.get("Path") or ""
    if not path:
        raise ToolError(f"couldn't find a file path for '{name}'")
    if itype == "Movie":
        target = Path(_local_path(path)).parent  # delete the whole movie folder
    elif itype == "Series":
        target = Path(_local_path(path))  # the series folder itself
    else:
        raise ToolError(f"deleting '{itype}' items isn't supported — pick a movie or series")
    root = Path(config.FS_ROOT).resolve()
    resolved = target.resolve()
    if resolved != root and not str(resolved).startswith(str(root) + os.sep):
        raise ToolError("refusing to delete outside the media root")
    if not resolved.exists():
        raise ToolError(f"'{name}' isn't on disk ({resolved})")
    try:
        if resolved.is_dir():
            shutil.rmtree(resolved)
        else:
            resolved.unlink()
    except OSError as err:
        raise ToolError(f"couldn't delete '{name}': {err}") from err
    await _post("/Library/Refresh")
    return {"deleted": True, "name": name, "type": itype, "path": str(resolved)}


async def jellyfin_refresh() -> dict[str, Any]:
    """Trigger a Jellyfin library rescan."""
    await _post("/Library/Refresh")
    return {"refreshed": True}


async def jellyfin_stream_url(item_id: str) -> dict[str, Any]:
    """Return a playable HLS stream URL (adaptive, with transcoding fallback)."""
    if not (item_id or "").strip():
        raise ToolError("which movie?")
    item = await _get_item(item_id, "MediaSources")
    sources = item.get("MediaSources") or []
    if not sources:
        raise ToolError("no playable media source found")
    msid = sources[0].get("Id") or ""
    url = (
        f"{config.JELLYFIN_URL}/Videos/{item_id}/master.m3u8"
        f"?api_key={config.JELLYFIN_API_KEY}&MaxStreamingBitrate=8000000"
    )
    if msid:
        url += f"&mediaSourceId={msid}"
    return {"url": url, "name": item.get("Name"), "media_source_id": msid}


async def jellyfin_download_url(item_id: str) -> dict[str, Any]:
    """Return a direct download URL for a movie's original file."""
    if not (item_id or "").strip():
        raise ToolError("which movie?")
    item = await _get_item(item_id, "MediaSources")
    sources = item.get("MediaSources") or []
    filename = ""
    size = None
    if sources:
        filename = sources[0].get("Name") or ""
        size = sources[0].get("Size")
    url = f"{config.JELLYFIN_URL}/Items/{item_id}/Download?api_key={config.JELLYFIN_API_KEY}"
    return {"url": url, "name": item.get("Name"), "filename": filename, "size": size}


async def media_file_info(item_id: str) -> dict[str, Any]:
    """Resolve a movie to its local (Pi) file path, filename and size."""
    if not (item_id or "").strip():
        raise ToolError("which movie?")
    item = await _get_item(item_id, "MediaSources,Path")
    sources = item.get("MediaSources") or []
    if not sources:
        raise ToolError("no media source found")
    src = sources[0]
    path = _local_path(src.get("Path") or item.get("Path") or "")
    return {
        "path": path,
        "name": item.get("Name") or "Untitled",
        "filename": src.get("Name") or "",
        "size": src.get("Size") or 0,
        "container": (src.get("Container") or "").lower(),
    }


def local_path(jellyfin_path: str) -> str:
    """Public path normaliser: SMB mount path → Pi path, else as-is."""
    return _local_path(jellyfin_path)


_CATEGORY_DIRS = {
    "action & adventure", "comedy", "drama", "fantasy", "sci-fi", "superheroes",
    "thriller & crime", "estonian", "filmid", "multikad",
}


def _clean_title(stem: str, year: int | None) -> tuple[str, int | None]:
    """Derive a clean movie title from a raw filename stem (release tags stripped)."""
    if year is None:
        m = re.search(r"(19|20)\d{2}", stem)
        year = int(m.group(0)) if m else None
    m = re.search(r"(19|20)\d{2}", stem)
    if m:
        stem = stem[:m.start()]  # title is everything before the year
    stem = re.sub(r"[\[\(\{].*$", "", stem)  # strip trailing bracket groups
    stem = stem.replace(".", " ").replace("_", " ").replace("-", " ")
    stem = re.sub(r"\s+", " ", stem).strip(" .-_")
    return (stem or "Unknown"), year


async def jellyfin_episodes(series_id: str) -> dict[str, Any]:
    """List all episodes of a series with season/episode numbers and paths."""
    if not (series_id or "").strip():
        raise ToolError("which series?")
    uid = await _user_id()
    data = await _get(f"/Shows/{series_id}/Episodes", {
        "userId": uid,
        "Fields": "MediaSources,Path",
    })
    episodes: list[dict[str, Any]] = []
    for e in _items(data):
        episodes.append({
            "id": e.get("Id"),
            "name": e.get("Name"),
            "season": e.get("ParentIndexNumber"),
            "episode": e.get("IndexNumber"),
            "path": e.get("Path"),
            "size_mb": _size_mb(e),
        })
    episodes.sort(key=lambda e: ((e.get("season") or 0), (e.get("episode") or 0)))
    return {"episodes": episodes}


async def local_movies() -> dict[str, Any]:
    """Scan the films folder directly and list movies (no Jellyfin needed)."""
    root = config.FS_ROOT.rstrip("/") + "/filmid"
    items: list[dict[str, Any]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d.lower() != "subs"]
        for fn in filenames:
            if not fn.lower().endswith((".mp4", ".mkv", ".avi")):
                continue
            folder = os.path.basename(dirpath)
            folder = re.sub(r"\s*\[.*?\]\s*$", "", folder).strip()  # strip [quality]
            m = re.search(r"\((\d{4})\)", folder)
            year = int(m.group(1)) if m else None
            name = re.sub(r"\s*\(\d{4}\)\s*$", "", folder).strip()
            if not name or name.lower() in _CATEGORY_DIRS:
                name, year = _clean_title(os.path.splitext(fn)[0], year)
            elif "." in name or "_" in name:
                name, year = _clean_title(name, year)
            full = os.path.join(dirpath, fn)
            try:
                size = os.path.getsize(full)
            except OSError:
                size = 0
            items.append({
                "id": full,
                "name": name or fn,
                "type": "Movie",
                "year": year,
                "path": full,
                "size_mb": round(size / 1_000_000) or None,
                "image": None,
                "video_codec": None,
                "bit_depth": None,
                "resolution": None,
                "hdr": False,
            })
    items.sort(key=lambda m: (m["name"] or "").lower())
    return {"type": "Movie", "items": items}
