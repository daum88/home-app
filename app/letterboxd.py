"""Letterboxd watchlist → Radarr sync.

Polls the public Letterboxd watchlist page, parses "Title (Year)" entries, and
adds any new movies to Radarr (which searches indexers and downloads them via
the configured H.264-only quality profile). Skips titles already in Jellyfin so
we never download a duplicate of something already on the drive.
"""
from __future__ import annotations

import asyncio
import html as html_mod
import json
import re
from pathlib import Path
from typing import Any

import httpx

from . import config
from .tools.base import ToolError

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

_STATE_FILE = Path(config.DB_PATH).parent / "letterboxd_synced.json"

_item_re = re.compile(r'data-item-name="([^"]+)"')
_year_re = re.compile(r"^(.*?)\s*\((\d{4})\)$")


def _norm(s: str) -> str:
    return "".join(c.lower() for c in s if c.isalnum())


# ---------------------------------------------------------------------------
# State (which watchlist titles we've already handed to Radarr)
# ---------------------------------------------------------------------------

def _load_state() -> set[str]:
    try:
        return set(json.loads(_STATE_FILE.read_text()))
    except (OSError, ValueError):
        return set()


def _save_state(state: set[str]) -> None:
    try:
        _STATE_FILE.write_text(json.dumps(sorted(state)))
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Letterboxd
# ---------------------------------------------------------------------------

def _parse_watchlist(page: str) -> list[tuple[str, int | None]]:
    """Return [(title, year_or_None), ...] from a watchlist HTML page."""
    out: list[tuple[str, int | None]] = []
    for raw in _item_re.findall(page):
        raw = html_mod.unescape(raw).strip()
        m = _year_re.match(raw)
        if m:
            out.append((m.group(1).strip(), int(m.group(2))))
        else:
            out.append((raw, None))
    return out


async def _fetch_watchlist() -> list[tuple[str, int | None]]:
    user = config.LETTERBOXD_USER
    if not user:
        raise ToolError("Letterboxd username isn't set (LETTERBOXD_USER)")
    url = f"https://letterboxd.com/{user}/watchlist/"
    try:
        async with httpx.AsyncClient(timeout=30, headers={"User-Agent": USER_AGENT}, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except httpx.HTTPError as err:
        raise ToolError(f"couldn't reach Letterboxd ({err})") from err
    films = _parse_watchlist(resp.text)
    if not films:
        raise ToolError("couldn't parse the watchlist (no films found)")
    return films


# ---------------------------------------------------------------------------
# Jellyfin (already-on-disk check)
# ---------------------------------------------------------------------------

async def _existing_titles() -> set[str]:
    if not (config.JELLYFIN_URL and config.JELLYFIN_API_KEY):
        return set()
    try:
        async with httpx.AsyncClient(timeout=config.REQUEST_TIMEOUT) as client:
            resp = await client.get(
                config.JELLYFIN_URL + "/Items",
                headers={"Authorization": f'MediaBrowser Token="{config.JELLYFIN_API_KEY}"'},
                params={
                    "Recursive": "true",
                    "IncludeItemTypes": "Movie",
                    "Fields": "MediaSources",
                    "Limit": "500",
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError:
        return set()
    items = data.get("Items") or []
    return {_norm(i.get("Name") or "") for i in items}


# ---------------------------------------------------------------------------
# Radarr
# ---------------------------------------------------------------------------

async def _radarr(method: str, path: str, json_body: Any = None, params: dict | None = None) -> Any:
    if not config.RADARR_API_KEY:
        raise ToolError("Radarr isn't configured (RADARR_API_KEY missing)")
    headers = {"X-Api-Key": config.RADARR_API_KEY}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(method, config.RADARR_URL + path, json=json_body, params=params, headers=headers)
            resp.raise_for_status()
            return resp.json() if resp.content else {}
    except httpx.HTTPError as err:
        raise ToolError(f"Radarr is unreachable ({err})") from err


async def _find_and_add(title: str, year: int | None) -> dict[str, Any]:
    term = f"{title} {year}" if year else title
    results = await _radarr("GET", "/api/v3/movie/lookup", params={"term": term})
    if not results:
        return {"title": title, "year": year, "added": False, "reason": "no match"}
    best = results[0]
    if year:
        for r in results:
            if r.get("year") == year:
                best = r
                break
    payload = {
        "title": best.get("title"),
        "tmdbId": best.get("tmdbId"),
        "qualityProfileId": config.RADARR_QUALITY_PROFILE_ID,
        "rootFolderPath": config.FS_ROOT.rstrip("/") + "/filmid",
        "monitored": True,
        "addOptions": {"searchForMovie": True},
    }
    try:
        added = await _radarr("POST", "/api/v3/movie", json_body=payload)
    except ToolError as err:
        return {"title": title, "year": year, "added": False, "reason": str(err)}
    return {"title": added.get("title"), "year": added.get("year"), "added": True, "id": added.get("id")}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def sync_watchlist() -> dict[str, Any]:
    """Fetch the Letterboxd watchlist and add any new movies to Radarr."""
    films = await _fetch_watchlist()
    existing = await _existing_titles()
    synced = _load_state()

    added: list[dict[str, Any]] = []
    skipped: list[str] = []
    for title, year in films:
        key = _norm(title) + (f"({year})" if year else "")
        if key in synced:
            continue
        if _norm(title) in existing:
            skipped.append(title)
            synced.add(key)
            continue
        try:
            result = await _find_and_add(title, year)
        except ToolError as err:
            # transient — leave unmarked so we retry next poll
            added.append({"title": title, "year": year, "added": False, "reason": str(err)})
            continue
        if result.get("added"):
            added.append(result)
            synced.add(key)
        elif result.get("reason") == "no match":
            synced.add(key)  # permanent miss — don't retry forever
            added.append(result)
        await asyncio.sleep(1)

    _save_state(synced)
    return {
        "watchlist_count": len(films),
        "added": added,
        "already_on_disk": skipped,
    }
