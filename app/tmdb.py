"""TheMovieDB (TMDB) poster fetcher — a lightweight, always-on replacement for
Jellyfin poster art when the Mac is offline.

Searches TMDB by title + year, caches the poster image on the media drive, and
keeps title→poster lookups in memory so repeated loads are instant. Disabled
(no-op) until TMDB_API_KEY is set in .env.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from typing import Any

import httpx

from . import config

log = logging.getLogger("hva.tmdb")

API = "https://api.themoviedb.org/3"
IMG_BASE = "https://image.tmdb.org/t/p"
CACHE_DIR = os.path.join(config.FS_ROOT, ".tmdb")

# (kind, title, year) -> poster_path (in-memory, long-lived)
_paths: dict[tuple[str, str, int | None], str | None] = {}
_sem = asyncio.Semaphore(6)


def enabled() -> bool:
    return bool(config.TMDB_API_KEY)


async def _get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    params = {**params, "api_key": config.TMDB_API_KEY}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{API}{path}", params=params)
        resp.raise_for_status()
        return resp.json()


async def _search_path(kind: str, title: str, year: int | None) -> str | None:
    endpoint = "/search/tv" if kind == "tv" else "/search/movie"
    params: dict[str, Any] = {"query": title}
    if year:
        params["year"] = year
    try:
        async with _sem:
            data = await _get(endpoint, params)
    except httpx.HTTPError as err:
        log.warning("tmdb search failed: %s", err)
        return None
    results = data.get("results") or []
    for r in results:
        ryear = (r.get("release_date") or r.get("first_air_date") or "")[:4]
        if year and ryear == str(year):
            return r.get("poster_path")
    return results[0].get("poster_path") if results else None


async def poster_bytes(kind: str, title: str, year: int | None) -> bytes | None:
    """Return cached poster image bytes for a movie/TV title, or None."""
    if not enabled():
        return None
    key = (kind, title.strip().lower(), year)
    path = _paths.get(key, "unset")
    if path == "unset":
        path = await _search_path(kind, title, year)
        _paths[key] = path
    if not path:
        return None

    os.makedirs(CACHE_DIR, exist_ok=True)
    fname = hashlib.sha1(path.encode()).hexdigest()[:20] + ".jpg"
    fp = os.path.join(CACHE_DIR, fname)
    if os.path.isfile(fp) and os.path.getsize(fp) > 0:
        with open(fp, "rb") as fh:
            return fh.read()
    try:
        async with _sem:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(f"{IMG_BASE}/w342{path}")
                resp.raise_for_status()
                data = resp.content
    except httpx.HTTPError as err:
        log.warning("tmdb image fetch failed: %s", err)
        return None
    try:
        with open(fp, "wb") as fh:
            fh.write(data)
    except OSError:
        pass
    return data
